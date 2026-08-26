from __future__ import annotations

import json

_SKIP_SUBSTR = (
    "whisper",
    "tts-",
    "dall-e",
    "davinci",
    "babbage",
    "embedding",
    "embed-",
    "moderation",
    "sora-",
    "transcribe",
    "gpt-image",
    "omni-moderation",
    "text-similarity",
    "text-search",
    "text-embedding",
    "audio-preview",
    "realtime",
)


def guess_provider(api_key: str, base_url: str | None, hinted: str | None) -> str:
    """Recognize provider from the key (prefix) or a compatible base URL."""
    k = (api_key or "").strip()
    hinted = (hinted or "").strip().lower()
    if k.startswith("sk-ant-"):
        return "anthropic"
    if k.startswith("sk-or-") or k.startswith("gsk_"):
        return "compatible"
    if (base_url or "").strip():
        return "compatible"
    if hinted in ("openai", "anthropic", "compatible"):
        return hinted
    return "openai"


def suggest_base_url(api_key: str) -> str:
    k = (api_key or "").strip()
    if k.startswith("sk-or-"):
        return "https://openrouter.ai/api/v1"
    if k.startswith("gsk_"):
        return "https://api.groq.com/openai/v1"
    return ""


def is_chat_model(model_id: str, *, strict: bool) -> bool:
    low = (model_id or "").lower()
    if any(s in low for s in _SKIP_SUBSTR):
        return False
    if not strict:
        return True
    return low.startswith(("gpt-", "o1", "o3", "o4", "chatgpt", "ft:"))


def list_models(provider: str, api_key: str, base_url: str | None) -> list[dict]:
    """Return [{id, label}] for models this key can actually use."""
    provider = (provider or "openai").lower()
    if provider == "anthropic":
        return _list_anthropic(api_key)
    return _list_openai_compat(api_key, base_url, strict=provider != "compatible")


def _raise_http(resp) -> None:
    try:
        payload = resp.json()
        err = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(err, dict) and err.get("message"):
            raise RuntimeError(str(err["message"]))
        if isinstance(err, str) and err:
            raise RuntimeError(err)
    except RuntimeError:
        raise
    except Exception:
        pass
    raise RuntimeError(f"HTTP {resp.status_code}")


def _list_anthropic(api_key: str) -> list[dict]:
    import httpx

    resp = httpx.get(
        "https://api.anthropic.com/v1/models",
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
        timeout=20.0,
    )
    if resp.status_code >= 400:
        _raise_http(resp)
    rows = resp.json().get("data") or []
    out = []
    for row in rows:
        mid = row.get("id") or ""
        if not mid:
            continue
        out.append({"id": mid, "label": row.get("display_name") or mid})
    return out


def _list_openai_compat(api_key: str, base_url: str | None, *, strict: bool) -> list[dict]:
    import httpx

    root = (base_url or "https://api.openai.com/v1").rstrip("/")
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    resp = httpx.get(f"{root}/models", headers=headers, timeout=20.0)
    if resp.status_code >= 400:
        _raise_http(resp)
    rows = resp.json().get("data") or []
    out = []
    seen = set()
    for row in rows:
        mid = row.get("id") or ""
        if not mid or mid in seen or not is_chat_model(mid, strict=strict):
            continue
        seen.add(mid)
        label = row.get("name") or row.get("display_name") or mid
        out.append({"id": mid, "label": label})
    out.sort(key=lambda m: m["id"])
    return out


def complete(provider: str, api_key: str, model: str, base_url: str | None, messages: list[dict], tools: list[dict]) -> dict:
    """Return {tool, args, usage, raw_text}."""
    provider = (provider or "openai").lower()
    if provider == "anthropic":
        return _anthropic(api_key, model, messages, tools)
    return _openai(api_key, model, base_url, messages, tools)


def _openai(api_key: str, model: str, base_url: str | None, messages: list[dict], tools: list[dict]) -> dict:
    from openai import OpenAI

    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    client = OpenAI(**kwargs)
    resp = client.chat.completions.create(model=model, messages=messages, tools=tools, temperature=0)
    usage = {}
    if resp.usage:
        usage = {
            "prompt_tokens": resp.usage.prompt_tokens,
            "completion_tokens": resp.usage.completion_tokens,
            "total_tokens": resp.usage.total_tokens,
        }
    msg = resp.choices[0].message
    if msg.tool_calls:
        call = msg.tool_calls[0]
        args = json.loads(call.function.arguments or "{}")
        return {"tool": call.function.name, "args": args, "usage": usage, "raw_text": msg.content or ""}
    return {"tool": None, "args": {}, "usage": usage, "raw_text": msg.content or ""}


def _anthropic(api_key: str, model: str, messages: list[dict], tools: list[dict]) -> dict:
    from anthropic import Anthropic

    a_tools = []
    for t in tools:
        fn = t["function"]
        a_tools.append(
            {
                "name": fn["name"],
                "description": fn.get("description") or "",
                "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
            }
        )
    system = ""
    amsg = []
    for m in messages:
        if m["role"] == "system":
            system += m["content"] + "\n"
        else:
            amsg.append({"role": m["role"], "content": m["content"]})
    client = Anthropic(api_key=api_key)
    resp = client.messages.create(model=model, max_tokens=1024, system=system.strip(), messages=amsg, tools=a_tools)
    usage = {
        "prompt_tokens": getattr(resp.usage, "input_tokens", None),
        "completion_tokens": getattr(resp.usage, "output_tokens", None),
        "total_tokens": (getattr(resp.usage, "input_tokens", 0) or 0) + (getattr(resp.usage, "output_tokens", 0) or 0),
    }
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use":
            return {"tool": block.name, "args": dict(block.input or {}), "usage": usage, "raw_text": ""}
        if getattr(block, "type", None) == "text":
            text = block.text
            return {"tool": None, "args": {}, "usage": usage, "raw_text": text}
    return {"tool": None, "args": {}, "usage": usage, "raw_text": ""}
