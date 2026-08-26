"""Per-install API authentication for the local NTerm service.

NTerm binds a credential-owning API to a local port. Without auth, any website
the operator visits can reach 127.0.0.1:8787 from their browser and read the
session inventory and stored transcripts, or issue destructive writes. CORS
alone does not stop the writes (a no-cors POST still arrives), so every route
requires a per-install token.

The token is generated once, stored 0600 in the data dir, and injected into
index.html when the SPA is served. Same-origin JS can read it; a cross-origin
page cannot read that HTML once CORS is restricted, so a malicious website
cannot learn the token.

That protects against a browser attacker, NOT against a direct network client:
"/" is not guarded, so anything that can reach the port can fetch the page and
read the token out of the meta tag. The port must therefore stay bound to
loopback — see the note in docker-compose.lab.yml.
"""
from __future__ import annotations

import hmac
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Request, WebSocket
from fastapi.responses import JSONResponse

from .config import DATA_DIR

TOKEN_PATH = DATA_DIR / ".auth_token"
AUDIT_PATH = DATA_DIR / "audit.log"
HEADER = "X-NTerm-Token"

# The token guards the data plane only: /api and /ws. The static SPA bundle is
# not sensitive (it is the client itself, and it must load before it can present
# a token), and /api/health stays open for the container probe.
GUARDED_PREFIXES = ("/api", "/ws", "/mcp")
OPEN_PATHS = ("/api/health",)


def _is_guarded(path: str) -> bool:
    if any(path == p or path.startswith(p + "/") for p in OPEN_PATHS):
        return False
    return any(path.startswith(p) for p in GUARDED_PREFIXES)


def _load_or_create_token() -> str:
    env = os.environ.get("NTERM_AUTH_TOKEN")
    if env:
        return env.strip()
    if TOKEN_PATH.exists():
        tok = TOKEN_PATH.read_text(encoding="utf-8").strip()
        if tok:
            return tok
    tok = secrets.token_urlsafe(32)
    TOKEN_PATH.write_text(tok, encoding="utf-8")
    try:
        TOKEN_PATH.chmod(0o600)
    except OSError:
        pass
    return tok


TOKEN = _load_or_create_token()

# Auth can be disabled only by explicit opt-in, and it is loud about it.
AUTH_DISABLED = os.environ.get("NTERM_DISABLE_AUTH") == "1"


def allowed_origins() -> list[str]:
    """Same-origin app, plus the Vite dev server when developing."""
    port = os.environ.get("NTERM_PORT", "8787")
    origins = [f"http://127.0.0.1:{port}", f"http://localhost:{port}"]
    if os.environ.get("NTERM_DEV") == "1":
        origins += ["http://127.0.0.1:5173", "http://localhost:5173"]
    extra = os.environ.get("NTERM_EXTRA_ORIGINS", "")
    origins += [o.strip() for o in extra.split(",") if o.strip()]
    return origins


def _valid(candidate: str | None) -> bool:
    if not candidate:
        return False
    return hmac.compare_digest(candidate, TOKEN)


def _present(request: Request) -> str | None:
    header = request.headers.get(HEADER)
    if header:
        return header
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return request.query_params.get("token")


async def auth_middleware(request: Request, call_next):
    """Guard the data plane.

    This is middleware rather than an app-level dependency on purpose. A
    dependency declared on the FastAPI app is applied to WebSocket routes too,
    and a function typed `(request: Request)` then receives a WebSocket and
    raises TypeError before the handler runs — which broke every session type.
    Middleware only ever sees HTTP; WebSockets are gated by check_ws_token().
    """
    if not AUTH_DISABLED and _is_guarded(request.url.path):
        if not _valid(_present(request)):
            audit("auth.denied", path=request.url.path,
                  ip=request.client.host if request.client else "?")
            return JSONResponse(
                {"detail": "Missing or invalid NTerm token"}, status_code=401
            )
    return await call_next(request)


async def check_ws_token(ws: WebSocket) -> bool:
    """WebSockets cannot set headers from the browser, so the token rides the
    query string. Returns False and closes the socket when it does not match."""
    if AUTH_DISABLED:
        return True
    token = ws.query_params.get("token") or ws.headers.get(HEADER)
    if _valid(token):
        return True
    audit("auth.denied_ws", path=ws.url.path)
    await ws.close(code=4401)
    return False


# ── audit log ─────────────────────────────────────────────────────────────
def audit(event: str, **fields) -> None:
    """Append-only security-relevant event log. Never contains secrets."""
    rec = {"ts": datetime.now(timezone.utc).isoformat(), "event": event}
    rec.update({k: v for k, v in fields.items() if v is not None})
    try:
        with AUDIT_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")
    except OSError:
        pass
