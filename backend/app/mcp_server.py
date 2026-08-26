from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from . import kb
from .db import get_db
from .llm import act as ai_act
from .models import SavedSession
from .toolkit.calculator import analyze_cidr

router = APIRouter()


def _tools():
    return [
        {"name": "search_kb", "description": "Search local config KB for ideas. Does not send to devices."},
        {"name": "list_sessions", "description": "List saved sessions (no passwords)."},
        {"name": "subnet_calc", "description": "CIDR / wildcard / VLSM."},
        {"name": "propose_cli", "description": "Preview CLI for a small NL ask. Does not send to a device."},
    ]


@router.get("")
def mcp_info():
    return {
        "name": "NTerm",
        "instructions": "Local knowledge base for config ideas. Bind only to localhost. No execute-on-device.",
        "tools": _tools(),
        "endpoint": "POST /mcp  JSON-RPC tools/list or tools/call",
    }


@router.post("")
def mcp_rpc(body: dict, db: Session = Depends(get_db)):
    method = body.get("method") or ""
    rid = body.get("id") or 1
    if method in ("tools/list", "list_tools"):
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": _tools()}}
    if method in ("tools/call", "call_tool"):
        params = body.get("params") or {}
        name = params.get("name") or params.get("tool")
        arguments = params.get("arguments") or params.get("args") or {}
        try:
            result = _call(db, name, arguments)
            return {"jsonrpc": "2.0", "id": rid, "result": result}
        except Exception as exc:
            return {"jsonrpc": "2.0", "id": rid, "error": {"message": str(exc)}}
    return {"jsonrpc": "2.0", "id": rid, "error": {"message": f"unknown method {method}"}}


def _call(db: Session, name: str, arguments: dict):
    if name == "search_kb":
        hits = kb.search(db, arguments.get("query") or arguments.get("q") or "")
        ai_act.record_event(db, source="mcp", prompt=arguments.get("query") or "", tool_name="search_kb", decision="proposed", cache_hit=False)
        return {"hits": hits}
    if name == "list_sessions":
        rows = db.query(SavedSession).all()
        return {
            "sessions": [
                {"id": s.id, "name": s.name, "kind": s.kind, "device_type": s.device_type, "host": s.host, "customer_id": s.customer_id}
                for s in rows
            ]
        }
    if name == "subnet_calc":
        return analyze_cidr(arguments.get("cidr") or "", arguments.get("split"))
    if name == "propose_cli":
        msg = arguments.get("message") or arguments.get("prompt") or ""
        dtype = arguments.get("device_type") or "cisco_ios"
        hits = kb.search(db, msg)
        return ai_act.act(db, message=msg, device_type=dtype, customer_id=None, session_id=None, source="mcp", kb_hits=hits)
    raise ValueError(f"unknown tool {name}")
