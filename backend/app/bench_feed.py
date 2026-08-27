"""Pull Engineer Bench content from the customer's server (nexthopllc.com, nterm.ai, …)."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from .architect import COOKBOOK, LOOKUPS, RUNBOOKS
from .crypto import decrypt, encrypt
from .settings_store import get_json, get_value, set_json, set_value

CACHE_KEY = "bench_feed_cache"
META_KEY = "bench_feed_meta"
VALIDATOR_KEY = "bench_feed_validator"   # ETag / Last-Modified from the last 200


def _user_agent() -> str:
    """Real version in the UA. With a large installed base the server logs are the
    only way to see which versions are actually out there."""
    try:
        from pathlib import Path

        v = (Path(__file__).resolve().parents[2] / "VERSION").read_text().strip()
    except Exception:
        v = "0"
    return f"NTerm/{v} (+https://nterm.ai)"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def local_feed() -> dict:
    return {
        "version": 1,
        "source": "nterm-builtin",
        "updated_at": None,
        "cookbook": COOKBOOK,
        "runbooks": RUNBOOKS,
        "lookups": LOOKUPS,
    }


def _normalize(raw: dict, source: str) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("Bench feed must be a JSON object")
    cookbook = raw.get("cookbook") or raw.get("cookbooks") or {}
    runbooks = raw.get("runbooks") or []
    lookups = raw.get("lookups") or {}
    if not isinstance(cookbook, dict) or not isinstance(runbooks, list) or not isinstance(lookups, dict):
        raise ValueError("Invalid feed shape: need cookbook object, runbooks list, lookups object")
    return {
        "version": int(raw.get("version") or 1),
        "source": raw.get("source") or source,
        "updated_at": raw.get("updated_at"),
        "cookbook": cookbook,
        "runbooks": runbooks,
        "lookups": lookups,
        "snippets": raw.get("snippets") or [],
    }


def _merge(local: dict, remote: dict) -> dict:
    cook = {**local.get("cookbook", {}), **remote.get("cookbook", {})}
    local_rb = {r.get("id"): r for r in local.get("runbooks", []) if isinstance(r, dict)}
    for r in remote.get("runbooks", []):
        if isinstance(r, dict) and r.get("id"):
            local_rb[r["id"]] = r
    looks = {**local.get("lookups", {})}
    for k, v in (remote.get("lookups") or {}).items():
        looks[k] = v
    return {
        "version": remote.get("version") or 1,
        "source": remote.get("source") or "merged",
        "updated_at": remote.get("updated_at"),
        "cookbook": cook,
        "runbooks": list(local_rb.values()),
        "lookups": looks,
        "snippets": remote.get("snippets") or [],
    }


def bench_url(db: Session) -> str:
    return (get_value(db, "bench_api_url") or "").strip()


def bench_mode(db: Session) -> str:
    mode = (get_value(db, "bench_mode") or "merge").strip().lower()
    return mode if mode in ("remote", "local", "merge") else "merge"


def bench_key(db: Session) -> str | None:
    return decrypt(get_value(db, "bench_api_key_enc"))


def meta(db: Session) -> dict:
    m = get_json(db, META_KEY, {}) or {}
    m.setdefault("url", bench_url(db))
    m.setdefault("mode", bench_mode(db))
    m.setdefault("source", "nterm-builtin")
    m.setdefault("ok", True)
    return m


def cached(db: Session) -> dict | None:
    data = get_json(db, CACHE_KEY, None)
    return data if isinstance(data, dict) and data.get("cookbook") is not None else None


def resolve(db: Session) -> dict:
    mode = bench_mode(db)
    builtin = local_feed()
    remote = cached(db)
    if mode == "local" or not bench_url(db):
        return {**builtin, "source": "nterm-builtin"}
    if not remote:
        return builtin
    if mode == "remote":
        return remote
    return _merge(builtin, remote)


async def pull(db: Session) -> dict:
    url = bench_url(db)
    if not url:
        raise ValueError("Set a Bench API URL in Settings")
    headers = {"Accept": "application/json", "User-Agent": _user_agent()}
    # Conditional request: if the feed has not changed the server answers 304 with
    # no body. Cheap for us, and much cheaper for whoever is hosting the feed.
    validator = get_json(db, VALIDATOR_KEY) or {}
    if validator.get("etag"):
        headers["If-None-Match"] = validator["etag"]
    if validator.get("last_modified"):
        headers["If-Modified-Since"] = validator["last_modified"]
    key = bench_key(db)
    if key:
        headers["Authorization"] = f"Bearer {key}"
        headers["X-NTerm-Key"] = key
    urls = [url]
    if not url.rstrip("/").endswith((".json", "/feed", "/bench")):
        urls += [url.rstrip("/") + "/feed", url.rstrip("/") + "/bench.json"]
    last_err = "unreachable"
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        for candidate in urls:
            try:
                r = await client.get(candidate, headers=headers)
                if r.status_code == 304:
                    # Unchanged. Keep the cache, just restamp the metadata.
                    set_json(
                        db,
                        META_KEY,
                        {
                            "url": candidate,
                            "mode": bench_mode(db),
                            "source": (cached(db) or {}).get("source") or "nterm-builtin",
                            "fetched_at": _now(),
                            "ok": True,
                            "error": "",
                            "not_modified": True,
                        },
                    )
                    return {"ok": True, "feed": resolve(db), "meta": meta(db)}
                if r.status_code in (429, 503):
                    # Being asked to back off is not the same as being broken, and
                    # trying the next candidate URL would only add load.
                    retry = r.headers.get("Retry-After", "")
                    last_err = (
                        f"feed is rate limiting (HTTP {r.status_code})"
                        + (f", retry after {retry}s" if retry else "")
                        + " — using cache"
                    )
                    break
                if r.status_code >= 400:
                    last_err = f"{candidate} → HTTP {r.status_code}"
                    continue
                feed = _normalize(r.json(), candidate)
                set_json(db, CACHE_KEY, feed)
                set_json(
                    db,
                    VALIDATOR_KEY,
                    {
                        "etag": r.headers.get("ETag", ""),
                        "last_modified": r.headers.get("Last-Modified", ""),
                    },
                )
                set_json(
                    db,
                    META_KEY,
                    {
                        "url": candidate,
                        "mode": bench_mode(db),
                        "source": feed.get("source"),
                        "fetched_at": _now(),
                        "ok": True,
                        "error": "",
                    },
                )
                return {"ok": True, "feed": resolve(db), "meta": meta(db)}
            except Exception as exc:
                last_err = f"{candidate}: {exc}"
    set_json(
        db,
        META_KEY,
        {
            "url": url,
            "mode": bench_mode(db),
            "source": (cached(db) or {}).get("source") or "nterm-builtin",
            "fetched_at": _now(),
            "ok": False,
            "error": last_err,
        },
    )
    return {"ok": False, "error": last_err, "feed": resolve(db), "meta": meta(db)}


def save_config(db: Session, url: str | None, mode: str | None, api_key: str | None) -> None:
    if url is not None:
        set_value(db, "bench_api_url", url.strip())
    if mode is not None:
        set_value(db, "bench_mode", mode)
    if api_key:
        set_value(db, "bench_api_key_enc", encrypt(api_key) or "")
