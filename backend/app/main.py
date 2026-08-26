from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from . import mcp_client
from .ai_service import build_messages, chat, offline_reply
from .analyzers import run_analyzers
from .architect import acl_lines, config_diff, summarize, translate_rule, type7_decode, type7_encode
from . import bench_feed
from .config import APP_DOMAIN, APP_NAME, APP_VERSION, DATA_DIR, STATIC_DIR
from .crypto import encrypt
from .db import Base, SessionLocal, engine, get_db
from .device_profiles import PROFILES
from .extensions import enabled_snippets, sync_builtin
from .models import Customer, DhcpLease, Extension, McpServer, SavedSession, SessionLog, SyslogEvent
from .schemas import (
    AiChatIn,
    AnalyzeRequest,
    BroadcastIn,
    CustomerIn,
    ExtensionInstall,
    ExtensionToggle,
    McpIn,
    SessionIn,
    SessionUpdate,
    SettingsIn,
    SubnetIn,
    SummarizeIn,
    ToolkitServiceIn,
    TranslateIn,
    Type7In,
    DiffIn,
    AclIn,
)
from .seed import seed
from .settings_store import get_openai_key, get_value, set_openai_key, set_value
from .terminal_hub import hub
from .toolkit import manager as toolkit
from .toolkit.calculator import analyze_cidr
from .toolkit.syslog_srv import event_to_dict

Base.metadata.create_all(bind=engine)
with SessionLocal() as db:
    seed(db)

app = FastAPI(title=APP_NAME, version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def session_out(row: SavedSession) -> dict:
    return {
        "id": row.id,
        "customer_id": row.customer_id,
        "name": row.name,
        "kind": row.kind,
        "device_type": row.device_type,
        "host": row.host,
        "port": row.port,
        "username": row.username,
        "has_password": bool(row.password_enc),
        "has_enable_password": bool(row.enable_password_enc),
        "has_private_key": bool(row.private_key_enc),
        "jump_host": row.jump_host,
        "notes": row.notes,
        "logging_enabled": row.logging_enabled,
        "post_login": row.post_login,
        "created_at": row.created_at,
    }


@app.get("/api/health")
def health():
    return {"ok": True, "name": APP_NAME, "domain": APP_DOMAIN, "version": APP_VERSION}


@app.get("/api/meta")
def meta(db: Session = Depends(get_db)):
    return {
        "profiles": PROFILES,
        "snippets": enabled_snippets(db),
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
    for k, v in data.items():
        setattr(row, k, v)
    if password:
        row.password_enc = encrypt(password)
    if enable:
        row.enable_password_enc = encrypt(enable)
    if key:
        row.private_key_enc = encrypt(key)
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
        "openai_model": get_value(db, "openai_model", "gpt-4.1-mini"),
        "theme": get_value(db, "theme", "nexthop_dark"),
        "font_size": int(get_value(db, "font_size", "14")),
        "ai_auto_context": get_value(db, "ai_auto_context", "true") == "true",
        "bench_api_url": bench_feed.bench_url(db),
        "bench_mode": bench_feed.bench_mode(db),
        "bench_key_configured": bool(bench_feed.bench_key(db)),
    }


@app.put("/api/settings")
def put_settings(body: SettingsIn, db: Session = Depends(get_db)):
    if body.openai_api_key:
        set_openai_key(db, body.openai_api_key.strip())
    if body.openai_model:
        set_value(db, "openai_model", body.openai_model)
    if body.theme:
        set_value(db, "theme", body.theme)
    if body.font_size:
        set_value(db, "font_size", str(body.font_size))
    if body.ai_auto_context is not None:
        set_value(db, "ai_auto_context", "true" if body.ai_auto_context else "false")
    bench_feed.save_config(db, body.bench_api_url, body.bench_mode, body.bench_api_key)
    return get_settings(db)


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


@app.websocket("/ws/term/{tab_id}")
async def terminal_ws(ws: WebSocket, tab_id: str, session_id: int):
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


if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
