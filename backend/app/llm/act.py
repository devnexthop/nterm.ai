from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from .. import kb
from ..crypto import decrypt
from ..models import AiCache, AiEvent, SavedSession
from ..settings_store import get_anthropic_key, get_openai_key, get_value
from . import adapters, providers
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
    customer_id: int | None,
    session_id: int | None,
    source: str,
    kb_hits: list[dict],
) -> dict:
    dialect = device_type or "cisco_ios"
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

    preview = adapters.heuristic(message, dialect)
    usage: dict = {}
    offline = False
    raw_text = ""
    if key:
        kb_txt = "\n".join(f"- {h.get('title')}: {(h.get('snippet') or '')[:400]}" for h in kb_hits[:5])
        messages = [
            {
                "role": "system",
                "content": (
                    "You are NTerm. Pick exactly one tool for a SMALL device change. "
                    "Never invent extra config. Dialect: " + dialect + "\nKB hits:\n" + (kb_txt or "(none)")
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
