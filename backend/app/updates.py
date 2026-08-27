"""Compare the running build against what is published on GitHub.

Deliberately manual. The enterprise page promises "no analytics, no phone-home",
and an update check that fires on its own is a phone-home however benign the
payload — it tells us an install exists, roughly where, and how often it runs.
So nothing here happens without someone pressing the button, and the result is
cached so pressing it twice does not cost a second request.

Unauthenticated GitHub allows 60 requests an hour per IP. One manual check per
person is nowhere near that; a background poller across a large installed base
would be.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import httpx

REPO = "devnexthop/nterm.ai"
_RELEASES = f"https://api.github.com/repos/{REPO}/releases/latest"
_TAGS = f"https://api.github.com/repos/{REPO}/tags"
_COMMITS = f"https://api.github.com/repos/{REPO}/commits?per_page=1"

# Cached in-process. A restart re-checks, which is the right cadence for
# something a person triggers.
_CACHE: dict = {}
_CACHE_TTL = timedelta(minutes=30)


def _now() -> datetime:
    return datetime.now(timezone.utc)


_SEMVER = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def _parts(version: str) -> tuple[int, int, int] | None:
    m = _SEMVER.search(version or "")
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def compare(running: str, latest: str) -> str:
    """behind | current | ahead | unknown."""
    a, b = _parts(running), _parts(latest)
    if not a or not b:
        return "unknown"
    if a < b:
        return "behind"
    if a > b:
        # A local build from an unreleased commit. Saying "up to date" would be
        # a lie and "behind" would be worse.
        return "ahead"
    return "current"


async def check(running_version: str, running_build: str, force: bool = False) -> dict:
    cached = _CACHE.get("result")
    if cached and not force and _now() - _CACHE["at"] < _CACHE_TTL:
        return {**cached, "cached": True}

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"NTerm/{running_version} (+https://nterm.ai)",
    }
    result: dict = {
        "running": {"version": running_version, "build": running_build},
        "latest": None,
        "source": None,
        "url": f"https://github.com/{REPO}",
        "state": "unknown",
        "checked_at": _now().isoformat(),
        "error": "",
    }

    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
        # A release is the strongest signal; fall back to tags, then to the
        # newest commit, so a repo with no releases yet still answers usefully.
        try:
            r = await client.get(_RELEASES, headers=headers)
            if r.status_code == 200:
                data = r.json()
                result["latest"] = data.get("tag_name") or data.get("name")
                result["source"] = "release"
                result["url"] = data.get("html_url") or result["url"]
                result["notes"] = (data.get("body") or "")[:2000]
            elif r.status_code == 404:
                t = await client.get(_TAGS, headers=headers)
                if t.status_code == 200 and t.json():
                    result["latest"] = t.json()[0].get("name")
                    result["source"] = "tag"
                else:
                    c = await client.get(_COMMITS, headers=headers)
                    if c.status_code == 200 and c.json():
                        sha = (c.json()[0].get("sha") or "")[:7]
                        result["latest_commit"] = sha
                        result["source"] = "commit"
                        result["state"] = "current" if sha == running_build else "differs"
            elif r.status_code == 403:
                result["error"] = "GitHub rate limit reached — try again later"
            else:
                result["error"] = f"GitHub returned HTTP {r.status_code}"
        except Exception as exc:
            result["error"] = f"Could not reach GitHub: {exc}"

    if result["latest"]:
        result["state"] = compare(running_version, result["latest"])

    _CACHE["result"] = result
    _CACHE["at"] = _now()
    return {**result, "cached": False}


if __name__ == "__main__":
    for a, b, want in [
        ("0.1.0", "v0.2.0", "behind"),
        ("0.2.0", "v0.2.0", "current"),
        ("0.3.0", "v0.2.0", "ahead"),
        ("0.2.0", "", "unknown"),
        ("0.2.0", "nonsense", "unknown"),
    ]:
        got = compare(a, b)
        print(f"{a:8} vs {b or '(none)':10} -> {got:8} {'ok' if got == want else 'FAIL expected ' + want}")
        assert got == want
    print("version comparison ok")
