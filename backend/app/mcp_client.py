from __future__ import annotations

import json
import httpx
from sqlalchemy.orm import Session

from .models import McpServer


async def list_tools(db: Session) -> list[dict]:
    tools = []
    servers = db.query(McpServer).filter(McpServer.enabled.is_(True)).all()
    for srv in servers:
        if srv.transport in ("sse", "http") and srv.url:
            try:
                fetched = await _http_tools(srv)
                tools.extend(fetched)
            except Exception as exc:
                tools.append(
                    {
                        "server": srv.name,
                        "name": "_error",
                        "description": str(exc),
                    }
                )
        else:
            tools.append(
                {
                    "server": srv.name,
                    "name": "_stdio",
                    "description": f"stdio MCP `{srv.command}` is configured. NTerm lists HTTP/SSE tools automatically; stdio servers are stored for the AI to know they exist.",
                }
            )
    return tools


async def _http_tools(srv: McpServer) -> list[dict]:
    url = srv.url.rstrip("/")
    async with httpx.AsyncClient(timeout=8.0) as client:
        for path in ("/tools/list", "/mcp/tools", "/tools"):
            try:
                r = await client.get(url + path)
                if r.status_code >= 400:
                    continue
                data = r.json()
                items = data.get("tools") or data.get("result", {}).get("tools") or data
                if isinstance(items, list):
                    return [
                        {
                            "server": srv.name,
                            "name": item.get("name"),
                            "description": item.get("description", ""),
                        }
                        for item in items
                        if isinstance(item, dict)
                    ]
            except Exception:
                continue
        r = await client.post(
            url,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        r.raise_for_status()
        data = r.json()
        items = data.get("result", {}).get("tools") or []
        return [
            {
                "server": srv.name,
                "name": item.get("name"),
                "description": item.get("description", ""),
            }
            for item in items
        ]


async def call_tool(db: Session, server_id: int, name: str, arguments: dict) -> dict:
    srv = db.get(McpServer, server_id)
    if not srv:
        raise ValueError("MCP server not found")
    if not srv.url:
        raise ValueError("stdio MCP call is not wired; use an HTTP/SSE server URL")
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(
            srv.url.rstrip("/"),
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments or {}},
            },
        )
        r.raise_for_status()
        return r.json()


def tools_as_prompt(tools: list[dict]) -> str:
    if not tools:
        return ""
    return "MCP tools available:\n" + "\n".join(
        f"- [{t.get('server')}] {t.get('name')}: {t.get('description')}" for t in tools
    )
