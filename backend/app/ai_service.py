from __future__ import annotations

from openai import OpenAI

from .device_profiles import PROFILES
from .extensions import enabled_snippets


SYSTEM = """You are NTerm, a network architect sitting next to a field engineer.
You help with Cisco IOS/XE/NX-OS/ASA, Palo Alto PAN-OS, Fortinet FortiOS, Junos, and Linux.
Rules:
- Prefer exact CLI the engineer can paste.
- Call out destructive commands (reload, clear, format, factory-reset) and wait for confirmation.
- Use the session transcript as ground truth. If it is missing, say so.
- When MCP tool results are provided, use them.
- Keep answers tight. Lead with the command or diagnosis.
"""


def build_messages(body, snippets: list[dict], mcp_notes: str = "") -> list[dict]:
    dialect = PROFILES.get(body.device_type, PROFILES["generic"])["dialect"]
    snippet_txt = "\n".join(f"- {s['name']}: {s['command']}" for s in snippets[:20])
    context = f"""Customer: {body.customer_name or "unknown"}
Device dialect: {dialect}
Saved snippets:
{snippet_txt or "(none)"}
{mcp_notes}

--- session transcript (tail) ---
{(body.transcript or "")[-12000:]}
"""
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": context},
        {"role": "user", "content": body.message},
    ]


def chat(api_key: str, model: str, messages: list[dict]) -> str:
    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(model=model, messages=messages, temperature=0.2)
    return (resp.choices[0].message.content or "").strip()


def offline_reply(body, snippets: list[dict]) -> str:
    q = (body.message or "").lower()
    hits = [s for s in snippets if any(w in s["command"].lower() or w in s["name"].lower() for w in q.split())]
    lines = [
        "No OpenAI key is configured. Paste one in Settings → AI (no code required).",
        "Built-in snippets you can send from the command bar:",
    ]
    for s in (hits or snippets)[:8]:
        lines.append(f"• {s['name']}: `{s['command']}`")
    if "interface" in q or "down" in q:
        lines.append("Also try the config analyzer on a `show run` / `show ip int brief` capture.")
    return "\n".join(lines)
