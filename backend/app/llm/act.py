from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from .. import kb
from ..crypto import decrypt
from ..models import AiCache, AiEvent, SavedSession
from ..settings_store import get_anthropic_key, get_openai_key, get_value
from . import adapters, policy, providers, rehearse, shell
from .tools import SCHEMA_VERSION, TOOLS

# Tools that must NEVER apply without an explicit human Confirm, whatever
# risk the model or the classifier assigns. Shell arguments ARE the payload.
AUTO_APPLY_NEVER = {"shell_command"}


def _now():
    return datetime.now(timezone.utc)


def _cache_key(provider: str, model: str, dialect: str, prompt: str, kb_fp: str) -> str:
    raw = "|".join([provider, model, SCHEMA_VERSION, dialect, prompt.strip().lower(), kb_fp])
    return hashlib.sha256(raw.encode()).hexdigest()


def record_event(db: Session, **kwargs) -> AiEvent:
    row = AiEvent(**kwargs)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def act(
    db: Session,
    *,
    message: str,
    device_type: str,
    kind: str | None = None,
    customer_id: int | None,
    session_id: int | None,
    source: str,
    kb_hits: list[dict],
) -> dict:
    # A local shell is not a network device. Without this branch the model is
    # told to make "a SMALL device change" and the offline heuristic maps the
    # word "route" onto static_route — so "show me the route table" on Linux
    # drafts Cisco router config instead of `ip route show`.
    is_shell = (kind or "").lower() in ("local", "shell") or (device_type or "").lower() in (
        "linux", "local", "bash", "shell", "unix", "macos", "darwin",
        "windows", "powershell", "win",
    )
    dialect = shell.dialect_for(device_type, kind) if is_shell else (device_type or "cisco_ios")
    provider = get_value(db, "ai_provider", "openai")
    model = get_value(db, "openai_model", "gpt-4.1-mini")
    base_url = get_value(db, "ai_base_url", "") or None
    key = get_anthropic_key(db) if provider == "anthropic" else get_openai_key(db)
    fp = kb.fingerprint(kb_hits)
    ck = _cache_key(provider, model, dialect, message, fp)
    cache_on = get_value(db, "ai_cache_enabled", "true") == "true"
    if cache_on:
        cached = db.get(AiCache, ck)
        if cached:
            created = cached.created_at
            if created and created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if created and _now() - created > timedelta(days=7):
                db.delete(cached)
                db.commit()
                cached = None
        if cached:
            payload = json.loads(cached.payload)
            ev = record_event(
                db,
                customer_id=customer_id,
                session_id=session_id,
                source=source,
                prompt=message,
                tool_name=payload.get("tool") or "",
                tool_args=json.dumps(payload.get("args") or {}),
                commands_preview="\n".join(payload.get("commands") or []),
                decision="proposed",
                provider=provider,
                model=model,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                cache_hit=True,
            )
            payload["event_id"] = ev.id
            payload["cache_hit"] = True
            payload["offline"] = False
            payload["usage"] = {"total_tokens": 0}
            return payload

    # The network heuristic only knows network tools; on a shell it would
    # mis-map. Offline on a shell means no draft, which is the honest answer.
    preview = None if is_shell else adapters.heuristic(message, dialect)
    usage: dict = {}
    offline = False
    raw_text = ""
    if key:
        kb_txt = "\n".join(f"- {h.get('title')}: {(h.get('snippet') or '')[:400]}" for h in kb_hits[:5])
        messages = [
            {
                "role": "system",
                "content": (
                    (
                        "You are NTerm, drafting a command for " + shell.label(dialect)
                        + ". Use the shell_command tool and nothing else. Emit ONE command "
                        "line. This is a shell, NOT a network device — never emit "
                        "Cisco/PAN-OS/FortiOS syntax. Match the userland exactly: "
                        + (
                            "PowerShell cmdlets (Get-ChildItem, Set-Acl, icacls), not bash."
                            if dialect == shell.POWERSHELL else
                            "BSD flags, not GNU — `sed -i ''`, `stat -f`, `date -r`."
                            if dialect == shell.MACOS else
                            "GNU flags — `sed -i`, `stat -c`, `date -d`."
                        )
                        + " Prefer read-only commands unless the user clearly asked to "
                        "change something."
                        if is_shell else
                        "You are NTerm. Pick exactly one tool for a SMALL device change. "
                        "Never invent extra config. Dialect: " + dialect
                    )
                    + "\nKB hits:\n" + (kb_txt or "(none)")
                ),
            },
            {"role": "user", "content": message},
        ]
        try:
            result = providers.complete(provider, key, model, base_url, messages, TOOLS)
            usage = result.get("usage") or {}
            raw_text = result.get("raw_text") or ""
            if result.get("tool"):
                preview = adapters.render(result["tool"], result.get("args") or {}, dialect)
        except Exception as exc:
            if preview is None:
                raise ValueError(str(exc)) from exc
            raw_text = str(exc)
    else:
        offline = True
        if preview is None:
            raise ValueError(
                "No API key and the ask did not match a built-in small task. "
                "Paste a key in Settings or try: set Loopback0 to 1.1.1.1/24"
            )

    if preview is None:
        raise ValueError(raw_text or "Model did not pick a tool. Try a smaller ask.")

    # ── the gate ─────────────────────────────────────────────────────────────
    # Runs BELOW the human confirm, not instead of it. The point is that a weak
    # or adversarial model produces a *blocked draft* rather than a dangerous
    # one — the operator's eyesight is the last check, never the only one.
    # Shell sessions are judged by shell.classify(), which already ran inside
    # adapters.render(); this permit-list gate is for network dialects.
    if not is_shell:
        verdict, blocked, warnings = policy.evaluate(preview.get("commands") or [], dialect)
        preview["policy"] = {
            "verdict": verdict,
            "blocked": blocked,
            "warnings": warnings,
            "dialect": policy.normalize_dialect(dialect),
        }
        if verdict == "block":
            # Never silently downgrade a blocked draft into something sendable.
            preview["risk"] = "high"
            preview["summary"] = "Blocked by policy — " + (blocked[0] if blocked else "denied shape")
        elif verdict == "warn" and preview.get("risk") == "low":
            preview["risk"] = "medium"

        # ── rehearsal ────────────────────────────────────────────────────────
        # Run the draft somewhere harmless before asking a human to approve it.
        # Only when the gate did not block — rehearsing a denied draft would be
        # pointless work and could imply the block is negotiable.
        if verdict != "block" and rehearse.supported(device_type):
            try:
                run = rehearse.dry_run(preview.get("commands") or [], device_type)
                preview["rehearsal"] = run
                if run.get("ran") and not run.get("ok"):
                    preview["risk"] = "high"
            except Exception as exc:
                # A rehearsal failure must never block drafting — it is an extra
                # check, not a dependency.
                preview["rehearsal"] = {"ran": False, "reason": f"rehearsal error: {exc}"}

    if cache_on:
        db.merge(AiCache(cache_key=ck, payload=json.dumps(preview), created_at=_now()))
        db.commit()
    ev = record_event(
        db,
        customer_id=customer_id,
        session_id=session_id,
        source=source,
        prompt=message,
        tool_name=preview.get("tool") or "",
        tool_args=json.dumps(preview.get("args") or {}),
        commands_preview="\n".join(preview.get("commands") or []),
        decision="proposed",
        provider=provider if key else "heuristic",
        model=model if key else "offline",
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        total_tokens=usage.get("total_tokens") if usage else 0,
        cache_hit=False,
    )
    out = dict(preview)
    out["event_id"] = ev.id
    out["cache_hit"] = False
    out["offline"] = offline
    out["usage"] = usage
    return out


def token_totals(db: Session) -> dict:
    rows = db.query(AiEvent).all()
    now = _now()

    def aware(dt):
        if dt is None:
            return now
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    def sum_since(delta):
        start = now - delta
        tot = 0
        for r in rows:
            if aware(r.created_at) >= start:
                tot += r.total_tokens or 0
        return tot

    return {
        "today": sum_since(timedelta(days=1)),
        "days_7": sum_since(timedelta(days=7)),
        "all": sum(r.total_tokens or 0 for r in rows),
        "events": len(rows),
    }


def decrypt_session_secrets(session: SavedSession) -> tuple[str | None, str | None]:
    if session.credential:
        return decrypt(session.credential.password_enc), decrypt(session.credential.enable_password_enc)
    return decrypt(session.password_enc), decrypt(session.enable_password_enc)
