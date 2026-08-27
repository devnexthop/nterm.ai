from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from . import mcp_client, updates
from .ai_service import build_messages, chat, offline_reply
from .analyzers import run_analyzers
from .architect import acl_lines, config_diff, summarize, translate_rule, type7_decode, type7_encode
from . import bench_feed, kb, mcp_client
from .auth import TOKEN, allowed_origins, audit, auth_middleware, check_ws_token
from . import hostkeys, share
from .config import APP_DOMAIN, APP_NAME, APP_VERSION, BUILD_SHA, DATA_DIR, STATIC_DIR
from .crypto import decrypt, encrypt
from .db import Base, SessionLocal, engine, get_db, migrate_schema
from .device_profiles import PROFILES
from .extensions import USER_PACK, enabled_snippets, ensure_user_pack, sync_builtin
from . import importers
from . import exporters
from .llm import act as ai_act
from .llm.providers import guess_provider, list_models, suggest_base_url
from .mcp_server import router as mcp_router
from .models import AiCache, AiEvent, Credential, Customer, DhcpLease, Extension, McpServer, SavedSession, SessionLog, SyslogEvent
from .schemas import (
    AclIn,
    AiActIn,
    AiChatIn,
    AiDecisionIn,
    AiModelsIn,
    AnalyzeRequest,
    BroadcastIn,
    CredentialIn,
    CustomerIn,
    DiffIn,
    ExtensionInstall,
    ExtensionToggle,
    KbIn,
    McpIn,
    NameIn,
    SessionIn,
    SessionUpdate,
    SettingsIn,
    SnippetIn,
    SubnetIn,
    SummarizeIn,
    ToolkitServiceIn,
    TranslateIn,
    Type7In,
)
from .seed import seed
from .settings_store import get_anthropic_key, get_openai_key, get_value, set_anthropic_key, set_openai_key, set_value
from .terminal_hub import hub
from .toolkit import manager as toolkit
from .toolkit.calculator import analyze_cidr
from .toolkit.syslog_srv import event_to_dict

Base.metadata.create_all(bind=engine)
migrate_schema()
with SessionLocal() as db:
    seed(db)

app = FastAPI(title=APP_NAME, version=APP_VERSION)
# Restricted to this app's own origin (plus the Vite dev server when NTERM_DEV=1).
# A credential-owning service on a local port must not accept arbitrary origins:
# with allow_origins=["*"] any site the operator visits could read the session
# inventory and stored transcripts straight out of the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-NTerm-Token"],
)
app.middleware("http")(auth_middleware)
app.include_router(mcp_router, prefix="/mcp")


def session_out(row: SavedSession) -> dict:
    cred = row.credential
    return {
        "id": row.id,
        "customer_id": row.customer_id,
        "name": row.name,
        "kind": row.kind,
        "device_type": row.device_type,
        "host": row.host,
        "port": row.port,
        "username": (cred.username if cred and cred.username else row.username),
        "has_password": bool((cred and cred.password_enc) or row.password_enc),
        "has_enable_password": bool((cred and cred.enable_password_enc) or row.enable_password_enc),
        "has_private_key": bool(row.private_key_enc),
        "jump_host": row.jump_host,
        "notes": row.notes,
        "logging_enabled": row.logging_enabled,
        "post_login": row.post_login,
        "folder": row.folder or "",
        "credential_id": row.credential_id,
        "baud": row.baud or 9600,
        "created_at": row.created_at,
    }


def cred_out(row: Credential) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "username": row.username,
        "device_type": row.device_type,
        "notes": row.notes,
        "has_password": bool(row.password_enc),
        "has_enable_password": bool(row.enable_password_enc),
        "created_at": row.created_at,
    }


def maybe_save_cred(db: Session, name: str | None, username: str, password: str | None, enable: str | None, device_type: str) -> int | None:
    if not name:
        return None
    row = Credential(
        name=name,
        username=username,
        password_enc=encrypt(password),
        enable_password_enc=encrypt(enable),
        device_type=device_type,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row.id


@app.get("/api/health")
def health():
    return {"ok": True, "name": APP_NAME, "domain": APP_DOMAIN,
            "version": APP_VERSION, "build": BUILD_SHA}


@app.get("/api/meta")
def meta(db: Session = Depends(get_db)):
    sync_builtin(db)
    packs = [
        {"id": e.id, "name": e.name}
        for e in db.query(Extension).filter(Extension.kind == "snippets", Extension.enabled.is_(True)).all()
    ]
    return {
        "profiles": PROFILES,
        "snippets": enabled_snippets(db),
        "snippet_packs": packs,
        "themes": [
            "nexthop_dark",
            "nexthop_light",
            "relay",
            "warp",
            "crt_amber",
            "putty",
            "nord",
            "solarized",
            "high_contrast",
        ],
    }


@app.get("/api/customers")
def list_customers(db: Session = Depends(get_db)):
    rows = db.query(Customer).order_by(Customer.name).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "color": c.color,
            "notes": c.notes,
            "created_at": c.created_at,
            "session_count": len(c.sessions),
            "sessions": [session_out(s) for s in c.sessions],
        }
        for c in rows
    ]


@app.post("/api/customers")
def create_customer(body: CustomerIn, db: Session = Depends(get_db)):
    row = Customer(name=body.name, color=body.color, notes=body.notes)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, **body.model_dump(), "created_at": row.created_at, "session_count": 0, "sessions": []}


@app.put("/api/customers/{cid}")
def update_customer(cid: int, body: CustomerIn, db: Session = Depends(get_db)):
    row = db.get(Customer, cid)
    if not row:
        raise HTTPException(404, "Customer not found")
    row.name, row.color, row.notes = body.name, body.color, body.notes
    db.commit()
    return {"ok": True}


@app.delete("/api/customers/{cid}")
def delete_customer(cid: int, db: Session = Depends(get_db)):
    row = db.get(Customer, cid)
    if not row:
        raise HTTPException(404, "Customer not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


@app.post("/api/sessions")
def create_session(body: SessionIn, db: Session = Depends(get_db)):
    if not db.get(Customer, body.customer_id):
        raise HTTPException(404, "Customer not found")
    cid = body.credential_id
    if body.save_as_credential:
        cid = maybe_save_cred(db, body.save_as_credential, body.username, body.password, body.enable_password, body.device_type)
    if cid:
        cred = db.get(Credential, cid)
        if cred and not body.username:
            body.username = cred.username
    row = SavedSession(
        customer_id=body.customer_id,
        name=body.name,
        kind=body.kind,
        device_type=body.device_type,
        host=body.host,
        port=body.port,
        username=body.username,
        password_enc=encrypt(body.password),
        enable_password_enc=encrypt(body.enable_password),
        private_key_enc=encrypt(body.private_key),
        jump_host=body.jump_host,
        notes=body.notes,
        logging_enabled=body.logging_enabled,
        post_login=body.post_login,
        folder=(body.folder or "").strip()[:400],
        credential_id=cid,
        baud=body.baud or 9600,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return session_out(row)


@app.put("/api/sessions/{sid}")
def update_session(sid: int, body: SessionUpdate, db: Session = Depends(get_db)):
    row = db.get(SavedSession, sid)
    if not row:
        raise HTTPException(404, "Session not found")
    data = body.model_dump(exclude_unset=True)
    password = data.pop("password", None)
    enable = data.pop("enable_password", None)
    key = data.pop("private_key", None)
    extra = data.pop("save_as_credential", None)
    for k, v in data.items():
        setattr(row, k, v)
    if password:
        row.password_enc = encrypt(password)
    if enable:
        row.enable_password_enc = encrypt(enable)
    if key:
        row.private_key_enc = encrypt(key)
    if extra:
        row.credential_id = maybe_save_cred(db, extra, row.username, password, enable, row.device_type)
    db.commit()
    return session_out(row)


@app.delete("/api/sessions/{sid}")
def delete_session(sid: int, db: Session = Depends(get_db)):
    row = db.get(SavedSession, sid)
    if not row:
        raise HTTPException(404, "Session not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


@app.post("/api/sessions/{sid}/duplicate")
def duplicate_session(sid: int, db: Session = Depends(get_db)):
    row = db.get(SavedSession, sid)
    if not row:
        raise HTTPException(404, "Session not found")
    copy = SavedSession(
        customer_id=row.customer_id,
        name=f"{row.name} copy",
        kind=row.kind,
        device_type=row.device_type,
        host=row.host,
        port=row.port,
        username=row.username,
        password_enc=row.password_enc,
        enable_password_enc=row.enable_password_enc,
        private_key_enc=row.private_key_enc,
        jump_host=row.jump_host,
        notes=row.notes,
        logging_enabled=row.logging_enabled,
        post_login=row.post_login,
        folder=row.folder or "",
        credential_id=row.credential_id,
        baud=row.baud or 9600,
    )
    db.add(copy)
    db.commit()
    db.refresh(copy)
    return session_out(copy)


@app.post("/api/sessions/{sid}/vault")
def session_to_vault(sid: int, body: NameIn, db: Session = Depends(get_db)):
    row = db.get(SavedSession, sid)
    if not row:
        raise HTTPException(404, "Session not found")
    cred = Credential(
        name=body.name or f"{row.name} vault",
        username=row.username,
        password_enc=row.password_enc,
        enable_password_enc=row.enable_password_enc,
        device_type=row.device_type,
    )
    db.add(cred)
    db.commit()
    db.refresh(cred)
    row.credential_id = cred.id
    db.commit()
    return cred_out(cred)


@app.get("/api/sessions/{sid}/logs")
def session_logs(sid: int, db: Session = Depends(get_db)):
    rows = (
        db.query(SessionLog)
        .filter(SessionLog.session_id == sid)
        .order_by(SessionLog.started_at.desc())
        .all()
    )
    return [
        {
            "id": r.id,
            "path": r.path,
            "started_at": r.started_at,
            "ended_at": r.ended_at,
            "bytes_written": r.bytes_written,
        }
        for r in rows
    ]


@app.get("/api/logs/{lid}")
def read_log(lid: int, db: Session = Depends(get_db)):
    row = db.get(SessionLog, lid)
    if not row or not Path(row.path).exists():
        raise HTTPException(404, "Log not found")
    return PlainTextResponse(Path(row.path).read_text(encoding="utf-8", errors="replace"))


@app.get("/api/logs/{lid}/download")
def download_log(lid: int, db: Session = Depends(get_db)):
    row = db.get(SessionLog, lid)
    if not row or not Path(row.path).exists():
        raise HTTPException(404, "Log not found")
    return FileResponse(row.path, filename=Path(row.path).name, media_type="text/plain")


@app.get("/api/settings")
def get_settings(db: Session = Depends(get_db)):
    return {
        "openai_configured": bool(get_openai_key(db)),
        "anthropic_configured": bool(get_anthropic_key(db)),
        "openai_model": get_value(db, "openai_model", "gpt-4.1-mini"),
        "ai_provider": get_value(db, "ai_provider", "openai"),
        "ai_base_url": get_value(db, "ai_base_url", ""),
        "ai_cache_enabled": get_value(db, "ai_cache_enabled", "true") == "true",
        "theme": get_value(db, "theme", "valeron"),
        "relay_configured": bool(get_value(db, "relay_token", "") or os.environ.get("NTERM_RELAY_TOKEN")),
        "version": APP_VERSION,
        "build": BUILD_SHA,
        "font_size": int(get_value(db, "font_size", "14")),
        "font_family": get_value(db, "font_family", "IBM Plex Mono"),
        "log_sessions": get_value(db, "log_sessions", "true") == "true",
        "log_redact": get_value(db, "log_redact", "true") == "true",
        "ai_auto_context": get_value(db, "ai_auto_context", "true") == "true",
        "bench_api_url": bench_feed.bench_url(db),
        "bench_mode": bench_feed.bench_mode(db),
        "bench_key_configured": bool(bench_feed.bench_key(db)),
    }


@app.put("/api/settings")
def put_settings(body: SettingsIn, db: Session = Depends(get_db)):
    if body.openai_api_key:
        set_openai_key(db, body.openai_api_key.strip())
    if body.anthropic_api_key:
        set_anthropic_key(db, body.anthropic_api_key.strip())
    if body.openai_model:
        set_value(db, "openai_model", body.openai_model)
    if body.ai_provider:
        set_value(db, "ai_provider", body.ai_provider)
    if body.ai_base_url is not None:
        set_value(db, "ai_base_url", body.ai_base_url)
    if body.ai_cache_enabled is not None:
        set_value(db, "ai_cache_enabled", "true" if body.ai_cache_enabled else "false")
    if body.theme:
        set_value(db, "theme", body.theme)
    if body.font_size:
        set_value(db, "font_size", str(body.font_size))
    if body.font_family:
        set_value(db, "font_family", body.font_family)
    if body.log_sessions is not None:
        set_value(db, "log_sessions", "true" if body.log_sessions else "false")
    if body.log_redact is not None:
        set_value(db, "log_redact", "true" if body.log_redact else "false")
    if body.ai_auto_context is not None:
        set_value(db, "ai_auto_context", "true" if body.ai_auto_context else "false")
    if body.relay_token is not None:
        set_value(db, "relay_token", body.relay_token.strip())
    bench_feed.save_config(db, body.bench_api_url, body.bench_mode, body.bench_api_key)
    return get_settings(db)


@app.post("/api/version/check")
async def version_check(force: bool = False):
    """Ask GitHub what the newest published version is.

    Manual only — see updates.py. Nothing calls this on a timer, which is what
    lets us keep saying NTerm does not phone home.
    """
    return await updates.check(APP_VERSION, BUILD_SHA, force=force)


@app.get("/api/mcp")
def list_mcp(db: Session = Depends(get_db)):
    return [
        {
            "id": m.id,
            "name": m.name,
            "enabled": m.enabled,
            "transport": m.transport,
            "url": m.url,
            "command": m.command,
            "args": m.args,
            "notes": m.notes,
        }
        for m in db.query(McpServer).all()
    ]


@app.post("/api/mcp")
def add_mcp(body: McpIn, db: Session = Depends(get_db)):
    row = McpServer(**body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, **body.model_dump()}


@app.delete("/api/mcp/{mid}")
def delete_mcp(mid: int, db: Session = Depends(get_db)):
    row = db.get(McpServer, mid)
    if not row:
        raise HTTPException(404)
    db.delete(row)
    db.commit()
    return {"ok": True}


@app.get("/api/mcp/tools")
async def mcp_tools(db: Session = Depends(get_db)):
    return await mcp_client.list_tools(db)


@app.post("/api/ai/models")
def ai_models(body: AiModelsIn, db: Session = Depends(get_db)):
    pasted = (body.api_key or "").strip()
    hinted = (body.provider or get_value(db, "ai_provider", "openai")).strip().lower()
    stored_base = get_value(db, "ai_base_url", "")
    base = (body.base_url if body.base_url is not None else stored_base).strip()
    provider = guess_provider(pasted, base, hinted)
    key = pasted
    if not key:
        key = (get_anthropic_key(db) if provider == "anthropic" else get_openai_key(db)) or ""
    if provider == "compatible":
        base = base or suggest_base_url(pasted or key) or stored_base
    if not key and provider != "compatible":
        raise HTTPException(400, "Paste an API key first.")
    if provider == "compatible" and not base:
        raise HTTPException(400, "Set a base URL for a compatible provider (OpenRouter, Groq, Ollama…).")
    try:
        models = list_models(provider, key, base or None)
        return {"provider": provider, "base_url": base, "models": models, "error": None}
    except Exception as exc:
        return {"provider": provider, "base_url": base, "models": [], "error": str(exc)}


@app.post("/api/ai/chat")
async def ai_chat(body: AiChatIn, db: Session = Depends(get_db)):
    snippets = enabled_snippets(db, body.device_type)
    key = get_openai_key(db)
    tools = await mcp_client.list_tools(db) if body.allow_tools else []
    notes = mcp_client.tools_as_prompt(tools)
    if not key:
        return {"reply": offline_reply(body, snippets), "offline": True, "snippets": snippets}
    messages = build_messages(body, snippets, notes)
    try:
        reply = chat(key, get_value(db, "openai_model", "gpt-4.1-mini"), messages)
    except Exception as exc:
        raise HTTPException(400, f"OpenAI error: {exc}")
    return {"reply": reply, "offline": False, "snippets": snippets}


@app.post("/api/analyze")
def analyze(body: AnalyzeRequest, db: Session = Depends(get_db)):
    text = body.text
    if body.log_id:
        log = db.get(SessionLog, body.log_id)
        if log and Path(log.path).exists():
            text = Path(log.path).read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        raise HTTPException(400, "Nothing to analyze")
    findings = run_analyzers(body.device_type, text)
    return {"findings": findings, "chars": len(text)}


@app.get("/api/extensions")
def list_extensions(db: Session = Depends(get_db)):
    sync_builtin(db)
    return [
        {
            "id": e.id,
            "name": e.name,
            "kind": e.kind,
            "enabled": e.enabled,
            "builtin": e.builtin,
            "description": e.description,
            "manifest": e.manifest,
        }
        for e in db.query(Extension).all()
    ]


@app.post("/api/extensions/{eid}/toggle")
def toggle_extension(eid: str, body: ExtensionToggle, db: Session = Depends(get_db)):
    row = db.get(Extension, eid)
    if not row:
        raise HTTPException(404)
    row.enabled = body.enabled
    db.commit()
    return {"ok": True, "enabled": row.enabled}


@app.post("/api/extensions")
def install_extension(body: ExtensionInstall, db: Session = Depends(get_db)):
    man = body.manifest
    eid = man.get("id")
    if not eid:
        raise HTTPException(400, "manifest.id required")
    row = db.get(Extension, eid)
    if row:
        row.name = man.get("name", row.name)
        row.kind = man.get("kind", row.kind)
        row.description = man.get("description", row.description)
        row.manifest = man
    else:
        row = Extension(
            id=eid,
            name=man.get("name", eid),
            kind=man.get("kind", "snippets"),
            enabled=True,
            builtin=False,
            description=man.get("description", ""),
            manifest=man,
        )
        db.add(row)
    db.commit()
    return {"ok": True, "id": eid}


@app.get("/api/snippets")
def list_snippets(device_type: str | None = None, pack: str | None = None, db: Session = Depends(get_db)):
    sync_builtin(db)
    return enabled_snippets(db, device_type, pack)


@app.post("/api/snippets")
def add_snippet(body: SnippetIn, db: Session = Depends(get_db)):
    row = ensure_user_pack(db)
    man = dict(row.manifest or {})
    snips = list(man.get("snippets") or [])
    item = {
        "id": body.id or uuid.uuid4().hex[:10],
        "name": body.name.strip(),
        "command": body.command,
        "device_types": body.device_types,
    }
    snips.append(item)
    man["snippets"] = snips
    row.manifest = man
    flag_modified(row, "manifest")
    db.commit()
    return {**item, "extension": USER_PACK, "editable": True}


@app.put("/api/snippets/{sid}")
def update_snippet(sid: str, body: SnippetIn, db: Session = Depends(get_db)):
    row = ensure_user_pack(db)
    man = dict(row.manifest or {})
    snips = list(man.get("snippets") or [])
    found = False
    for i, s in enumerate(snips):
        if s.get("id") == sid:
            snips[i] = {
                "id": sid,
                "name": body.name.strip(),
                "command": body.command,
                "device_types": body.device_types,
            }
            found = True
            break
    if not found:
        raise HTTPException(404, "Snippet not found")
    man["snippets"] = snips
    row.manifest = man
    flag_modified(row, "manifest")
    db.commit()
    return {"ok": True}


@app.delete("/api/snippets/{sid}")
def delete_snippet(sid: str, db: Session = Depends(get_db)):
    row = ensure_user_pack(db)
    man = dict(row.manifest or {})
    man["snippets"] = [s for s in (man.get("snippets") or []) if s.get("id") != sid]
    row.manifest = man
    flag_modified(row, "manifest")
    db.commit()
    return {"ok": True}


@app.get("/api/toolkit")
def toolkit_status(db: Session = Depends(get_db)):
    st = toolkit.status()
    st["dhcp"]["leases"] = [
        {
            "id": l.id,
            "mac": l.mac,
            "ip": l.ip,
            "hostname": l.hostname,
            "state": l.state,
            "issued_at": l.issued_at,
            "expires_at": l.expires_at,
        }
        for l in db.query(DhcpLease).order_by(DhcpLease.issued_at.desc()).limit(200)
    ]
    return st


@app.post("/api/toolkit/{name}")
async def toolkit_update(name: str, body: ToolkitServiceIn):
    spec = body.model_dump(exclude_none=True)
    try:
        return await toolkit.apply(name, spec)
    except Exception as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/toolkit/syslog/events")
def syslog_events(limit: int = 200, db: Session = Depends(get_db)):
    rows = db.query(SyslogEvent).order_by(SyslogEvent.id.desc()).limit(limit).all()
    return [event_to_dict(r) for r in reversed(rows)]


@app.delete("/api/toolkit/syslog/events")
def clear_syslog(db: Session = Depends(get_db)):
    db.query(SyslogEvent).delete()
    db.commit()
    return {"ok": True}


@app.get("/api/toolkit/tftp/files")
def tftp_files():
    return toolkit.tftp.list_files()


@app.post("/api/toolkit/tftp/files")
async def tftp_upload(file: UploadFile = File(...)):
    name = Path(file.filename or "upload.bin").name
    dest = toolkit.tftp.safe_path(name)
    if not dest:
        raise HTTPException(400, "Illegal name")
    dest.write_bytes(await file.read())
    with SessionLocal() as db:
        kb.ingest(db, title=name, body=dest.read_text(encoding="utf-8", errors="replace")[:200000], source="tftp")
    return {"ok": True, "name": name}


@app.delete("/api/toolkit/tftp/files/{name:path}")
def tftp_delete(name: str):
    dest = toolkit.tftp.safe_path(name)
    if not dest or not dest.exists():
        raise HTTPException(404)
    dest.unlink()
    return {"ok": True}


@app.post("/api/calc/subnet")
def subnet(body: SubnetIn):
    try:
        return analyze_cidr(body.cidr, body.split)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/architect/lookups")
def architect_lookups(db: Session = Depends(get_db)):
    return bench_feed.resolve(db).get("lookups") or {}


@app.get("/api/architect/cookbook")
def architect_cookbook(db: Session = Depends(get_db)):
    return bench_feed.resolve(db).get("cookbook") or {}


@app.get("/api/architect/runbooks")
def architect_runbooks(db: Session = Depends(get_db)):
    return bench_feed.resolve(db).get("runbooks") or []


@app.get("/api/architect/status")
def architect_status(db: Session = Depends(get_db)):
    feed = bench_feed.resolve(db)
    return {
        "meta": bench_feed.meta(db),
        "tracks": list((feed.get("cookbook") or {}).keys()),
        "runbook_count": len(feed.get("runbooks") or []),
    }


@app.get("/api/architect/example-feed")
def architect_example_feed():
    """Contract nterm.ai/bench-feed.json should return."""
    return bench_feed.local_feed()


@app.post("/api/architect/refresh")
async def architect_refresh(db: Session = Depends(get_db)):
    try:
        return await bench_feed.pull(db)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/architect/type7")
def architect_type7(body: Type7In):
    try:
        if body.mode == "encode":
            return {"result": type7_encode(body.text, body.seed)}
        return {"result": type7_decode(body.text)}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/architect/diff")
def architect_diff(body: DiffIn):
    return config_diff(body.before, body.after)


@app.post("/api/architect/acl")
def architect_acl(body: AclIn):
    try:
        return acl_lines(body.cidr, body.proto, body.dest, body.action)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/architect/summarize")
def architect_summarize(body: SummarizeIn):
    try:
        return summarize(body.cidrs.splitlines())
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/architect/translate")
def architect_translate(body: TranslateIn):
    try:
        return translate_rule(body.line, body.target)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/broadcast")
async def broadcast(body: BroadcastIn):
    await hub.broadcast(body.tab_ids, body.command, body.newline)
    return {"ok": True, "count": len(body.tab_ids)}


@app.get("/api/credentials")
def list_credentials(db: Session = Depends(get_db)):
    return [cred_out(r) for r in db.query(Credential).order_by(Credential.name).all()]


@app.post("/api/credentials")
def create_credential(body: CredentialIn, db: Session = Depends(get_db)):
    row = Credential(
        name=body.name,
        username=body.username,
        password_enc=encrypt(body.password),
        enable_password_enc=encrypt(body.enable_password),
        device_type=body.device_type,
        notes=body.notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return cred_out(row)


@app.put("/api/credentials/{cid}")
def update_credential(cid: int, body: CredentialIn, db: Session = Depends(get_db)):
    row = db.get(Credential, cid)
    if not row:
        raise HTTPException(404)
    row.name, row.username, row.device_type, row.notes = body.name, body.username, body.device_type, body.notes
    if body.password:
        row.password_enc = encrypt(body.password)
    if body.enable_password:
        row.enable_password_enc = encrypt(body.enable_password)
    db.commit()
    return cred_out(row)


@app.delete("/api/credentials/{cid}")
def delete_credential(cid: int, db: Session = Depends(get_db)):
    row = db.get(Credential, cid)
    if not row:
        raise HTTPException(404)
    for s in db.query(SavedSession).filter(SavedSession.credential_id == cid).all():
        if not s.password_enc:
            s.password_enc = row.password_enc
        if not s.enable_password_enc:
            s.enable_password_enc = row.enable_password_enc
        if not s.username:
            s.username = row.username
        s.credential_id = None
    db.delete(row)
    db.commit()
    return {"ok": True}


@app.post("/api/ai/act")
def ai_act_ep(body: AiActIn, db: Session = Depends(get_db)):
    session = db.get(SavedSession, body.session_id) if body.session_id else None
    dtype = body.device_type or (session.device_type if session else "cisco_ios")
    cid = body.customer_id or (session.customer_id if session else None)
    hits = kb.search(db, body.message)
    try:
        return ai_act.act(
            db,
            message=body.message,
            device_type=dtype,
            kind=(session.kind if session else None),
            customer_id=cid,
            session_id=body.session_id,
            source="do_bar",
            kb_hits=hits,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/ai/decision")
def ai_decision(body: AiDecisionIn, db: Session = Depends(get_db)):
    row = db.get(AiEvent, body.event_id)
    if not row:
        raise HTTPException(404)
    row.decision = body.decision
    db.commit()
    return {"ok": True, "decision": row.decision}


@app.get("/api/ai/events")
def ai_events(customer_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(AiEvent).order_by(AiEvent.id.desc())
    if customer_id:
        q = q.filter(AiEvent.customer_id == customer_id)
    rows = q.limit(200).all()
    return [
        {
            "id": r.id,
            "created_at": r.created_at,
            "customer_id": r.customer_id,
            "session_id": r.session_id,
            "source": r.source,
            "prompt": r.prompt,
            "tool_name": r.tool_name,
            "commands_preview": r.commands_preview,
            "decision": r.decision,
            "provider": r.provider,
            "model": r.model,
            "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens,
            "total_tokens": r.total_tokens,
            "cache_hit": r.cache_hit,
        }
        for r in rows
    ]


@app.get("/api/ai/usage")
def ai_usage(db: Session = Depends(get_db)):
    return ai_act.token_totals(db)


@app.delete("/api/ai/cache")
def ai_cache_clear(db: Session = Depends(get_db)):
    db.query(AiCache).delete()
    db.commit()
    return {"ok": True}


@app.get("/api/kb")
def kb_search(q: str = "", db: Session = Depends(get_db)):
    return kb.search(db, q)


@app.post("/api/kb")
def kb_add(body: KbIn, db: Session = Depends(get_db)):
    row = kb.ingest(db, title=body.title, body=body.body, source=body.source, vendor=body.vendor, customer_id=body.customer_id)
    return {"id": row.id}


@app.get("/api/serial/ports")
def serial_ports():
    try:
        from serial.tools import list_ports

        return [{"device": p.device, "description": p.description} for p in list_ports.comports()]
    except Exception:
        return []


@app.websocket("/ws/term/{tab_id}")
async def terminal_ws(ws: WebSocket, tab_id: str, session_id: int):
    if not await check_ws_token(ws):
        return
    await ws.accept()
    db = SessionLocal()
    try:
        session = db.get(SavedSession, session_id)
        if not session:
            await ws.send_json({"type": "status", "state": "error", "message": "Unknown session"})
            await ws.close()
            return
        await hub.attach(ws, tab_id, session, db)
    except WebSocketDisconnect:
        await hub.close(tab_id, db)
    finally:
        db.close()


@app.post("/api/share/{tab_id}")
async def start_share(tab_id: str, db: Session = Depends(get_db)):
    """Begin sharing a live tab read-only at sessions.nterm.ai."""
    if share.get(tab_id):
        sh = share.SHARES[tab_id]
        return {"share_id": sh.share_id, "url": sh.url}
    token = get_value(db, "relay_token", "") or os.environ.get("NTERM_RELAY_TOKEN", "")
    if not token:
        raise HTTPException(400, "Set the relay token in Settings first")
    tab = hub.get(tab_id)
    if not tab:
        raise HTTPException(404, "No live session on that tab")
    row = db.get(SavedSession, tab.session_id)
    sh = share.Share(tab_id, (row.name if row else "session"), token)
    try:
        await sh.start()
    except Exception as exc:
        raise HTTPException(502, f"Relay refused: {exc}")
    share.SHARES[tab_id] = sh
    audit("share.started", tab_id=tab_id, share_id=sh.share_id)
    return {"share_id": sh.share_id, "url": sh.url}


@app.delete("/api/share/{tab_id}")
async def stop_share(tab_id: str):
    sh = share.SHARES.pop(tab_id, None)
    if sh:
        await sh.stop()
        audit("share.stopped", tab_id=tab_id)
    return {"ok": True}


@app.get("/api/share/{tab_id}")
def share_status(tab_id: str):
    sh = share.get(tab_id)
    return {"active": bool(sh), "url": sh.url if sh else None,
            "share_id": sh.share_id if sh else None}


@app.get("/api/hostkeys")
def list_hostkeys():
    """Pinned SSH host keys, so an operator can see and manage what is trusted."""
    return hostkeys.list_all()


@app.delete("/api/hostkeys/{host_port}")
def forget_hostkey(host_port: str):
    if not hostkeys.forget(host_port):
        raise HTTPException(404, "No pinned key for that host")
    audit("ssh.hostkey_forgotten", host_port=host_port)
    return {"ok": True}


class ImportPreviewIn(BaseModel):
    content: str = ""
    format: str = "auto"
    filename: str = ""
    passphrase: str = ""


class ImportedSessionIn(BaseModel):
    name: str = ""
    host: str = ""
    port: int = 22
    kind: str = "ssh"
    username: str = ""
    device_type: str = "generic"
    group: str = ""
    folder: str = ""
    customer_name: str = ""
    customer_color: str = ""
    baud: int = 9600
    jump_host: str = ""
    notes: str = ""
    post_login: str = ""
    logging_enabled: bool = True
    password: str = ""
    enable_password: str = ""
    private_key: str = ""


class ImportCommitIn(BaseModel):
    sessions: list[ImportedSessionIn] = Field(default_factory=list)
    customer_name: str = ""
    include_secrets: bool = False


class ExportVaultIn(BaseModel):
    passphrase: str


class FolderRenameIn(BaseModel):
    customer_id: int
    from_folder: str
    to_folder: str


@app.get("/api/export/sessions")
def export_sessions(db: Session = Depends(get_db)):
    """Download the customer + folder tree. Structure only — no secrets."""
    customers = db.query(Customer).order_by(Customer.name).all()
    return exporters.build_tree(customers, vault=False)


@app.post("/api/export/sessions/vault")
def export_sessions_vault(body: ExportVaultIn, db: Session = Depends(get_db)):
    """Passphrase-wrapped backup including decrypted session secrets."""
    customers = db.query(Customer).order_by(Customer.name).all()
    tree = exporters.build_tree(customers, vault=True)
    try:
        return exporters.wrap_vault(tree, body.passphrase)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/folders/rename")
def rename_folder(body: FolderRenameIn, db: Session = Depends(get_db)):
    """Rename a site folder under one customer. Nested children keep the new prefix."""
    src = (body.from_folder or "").strip().strip("/")
    dst = (body.to_folder or "").strip().strip("/")
    if not src:
        raise HTTPException(400, "from_folder is required")
    rows = db.query(SavedSession).filter(SavedSession.customer_id == body.customer_id).all()
    n = 0
    for row in rows:
        folder = (row.folder or "").strip().strip("/")
        if folder == src or folder.startswith(src + "/"):
            row.folder = (dst + folder[len(src):]).strip("/") if dst else folder[len(src):].lstrip("/")
            n += 1
    db.commit()
    audit("folder.renamed", customer_id=body.customer_id, from_folder=src, to_folder=dst, sessions=n)
    return {"ok": True, "updated": n}


@app.post("/api/import/preview")
def import_preview(body: ImportPreviewIn):
    """Parse a SecureCRT / PuTTY / ssh_config / CSV / NTerm export without saving it.

    The preview step is not a nicety. An import writes hundreds of rows into a
    credential vault, and the operator has to see what the parser made of their
    file before any of it lands.
    """
    if len(body.content.encode("utf-8", "ignore")) > importers.MAX_CONTENT_BYTES:
        raise HTTPException(413, "That file is too large to import")
    native = exporters.parse_json(body.content)
    if native and exporters.is_wrapped(native):
        if not body.passphrase:
            raise HTTPException(400, "Encrypted backup — enter the passphrase, then preview again")
        try:
            native = exporters.unwrap_vault(native, body.passphrase)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        rows = exporters.tree_to_rows(native)
        return {"format": "nterm", "kind": native.get("kind"), "count": len(rows), "sessions": rows, "has_secrets": native.get("kind") == "vault"}
    fmt = importers.normalize_format(body.format) or "auto"
    if fmt == "auto":
        fmt = importers.detect(body.filename, body.content)
    try:
        rows = importers.parse(body.content, fmt, body.filename)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if len(rows) > importers.MAX_SESSIONS:
        raise HTTPException(400, f"Import is limited to {importers.MAX_SESSIONS} sessions at a time")
    return {"format": fmt, "count": len(rows), "sessions": rows, "has_secrets": fmt == "nterm" and any(r.get("password") for r in rows)}


@app.post("/api/import/commit")
def import_commit(body: ImportCommitIn, db: Session = Depends(get_db)):
    """Save a previewed import as customers and sessions.

    Foreign-tool imports never send secrets. Native NTerm vault backups may,
    and only when include_secrets is true — the operator opted in at export
    and again at import.
    """
    if not body.sessions:
        raise HTTPException(400, "Nothing to import")
    if len(body.sessions) > importers.MAX_SESSIONS:
        raise HTTPException(400, f"Import is limited to {importers.MAX_SESSIONS} sessions at a time")
    chosen = body.customer_name.strip()
    known = {c.name.strip().lower(): c for c in db.query(Customer).all()}
    # Read the existing (customer, name, host) keys once rather than querying
    # per row: a real import is hundreds of rows, and the set also catches
    # duplicates inside the batch itself, which a query could not see before
    # the commit.
    seen = {
        (s.customer_id, s.name.strip().lower(), s.host.strip().lower())
        for s in db.query(SavedSession).all()
    }
    created: list[SavedSession] = []
    skipped = 0
    for item in body.sessions:
        host = item.host.strip()[:255]
        kind = item.kind if item.kind in ("ssh", "telnet", "serial", "local", "simulator") else "ssh"
        if kind in ("ssh", "telnet") and not host:
            skipped += 1
            continue
        group = item.group.strip()
        folder = (item.folder or "").strip().strip("/")[:400]
        if not folder and group:
            parts = [p.strip() for p in group.split("/") if p.strip()]
            folder = "/".join(parts if chosen else parts[1:])[:400]
        # An explicitly chosen customer wins. Otherwise native exports name the
        # customer; SecureCRT-style groups use the top folder as the customer
        # and keep the rest as the site folder.
        cname = (
            chosen
            or (item.customer_name or "").strip()
            or (group.split("/")[0].strip() if group else "")
            or "Imported"
        )[:200]
        customer = known.get(cname.lower())
        if customer is None:
            customer = Customer(
                name=cname,
                color=(item.customer_color or "#ffb020")[:20],
                notes="Created by session import.",
            )
            db.add(customer)
            db.flush()
            known[cname.lower()] = customer
        name = (item.name.strip() or host or "session")[:200]
        key = (customer.id, name.lower(), host.lower())
        if key in seen:
            skipped += 1
            continue
        seen.add(key)
        row = SavedSession(
            customer_id=customer.id,
            name=name,
            kind=kind,
            device_type=item.device_type if item.device_type in PROFILES else "generic",
            host=host,
            port=item.port if 1 <= item.port <= 65535 else 22,
            username=item.username.strip()[:200],
            jump_host=(item.jump_host or "")[:255],
            notes=(item.notes or (f"Imported from {group}" if group and group != cname else "Imported"))[:4000],
            post_login=item.post_login or "",
            logging_enabled=item.logging_enabled,
            folder=folder,
            baud=item.baud if 50 <= item.baud <= 4_000_000 else 9600,
        )
        if body.include_secrets:
            row.password_enc = encrypt(item.password or None)
            row.enable_password_enc = encrypt(item.enable_password or None)
            row.private_key_enc = encrypt(item.private_key or None)
        db.add(row)
        created.append(row)
    db.commit()
    for row in created:
        db.refresh(row)
    audit("import.committed", created=len(created), skipped=skipped)
    return {
        "created": len(created),
        "skipped": skipped,
        "customer_ids": sorted({r.customer_id for r in created}),
        "sessions": [session_out(r) for r in created],
    }


if STATIC_DIR.exists():
    _INDEX = STATIC_DIR / "index.html"

    @app.get("/", include_in_schema=False)
    def spa_index():
        """Serve the SPA with the install token injected.

        Same-origin JS reads this; a cross-origin page cannot read the response
        body now that CORS is restricted, so it cannot learn the token.
        """
        html = _INDEX.read_text(encoding="utf-8")
        tag = f'<meta name="nterm-token" content="{TOKEN}">'
        if "nterm-token" not in html:
            html = html.replace("<head>", "<head>\n    " + tag, 1)
        return HTMLResponse(html)

    app.mount("/", StaticFiles(directory=STATIC_DIR, html=False), name="static")
