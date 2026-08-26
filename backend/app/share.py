"""Live read-only session sharing.

Taps LiveTab._emit() — the single funnel every byte of terminal output already
passes through, whatever the transport — and forwards frames over one outbound
WebSocket to the relay at sessions.nterm.ai. Outbound-only, so it works from any
laptop behind any firewall with no inbound rules.

The relay enforces read-only and does the secret redaction server-side, so an
old or tampered client cannot skip the filter. This module only forwards.
"""
from __future__ import annotations

import asyncio
import json
import os

RELAY_URL = os.environ.get("NTERM_RELAY_URL", "wss://sessions.nterm.ai/agent")
VIEW_BASE = os.environ.get("NTERM_RELAY_VIEW", "https://sessions.nterm.ai/v/")


class Share:
    """One active share for one tab."""

    def __init__(self, tab_id: str, title: str, token: str, ttl: int = 1800):
        self.tab_id = tab_id
        self.title = title
        self.token = token
        self.ttl = ttl
        self.share_id: str | None = None
        self.url: str | None = None
        self.error: str | None = None
        self._ws = None
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=1000)
        self._task: asyncio.Task | None = None

    @property
    def active(self) -> bool:
        return self.share_id is not None and self.error is None

    async def start(self) -> None:
        import websockets

        self._ws = await websockets.connect(RELAY_URL, open_timeout=15)
        await self._ws.send(json.dumps({
            "token": self.token,
            "client_id": _client_id(),
            "title": self.title,
            "ttl": self.ttl,
        }))
        hello = json.loads(await asyncio.wait_for(self._ws.recv(), timeout=15))
        if hello.get("type") != "ready":
            self.error = hello.get("error") or "relay refused the share"
            await self._close_ws()
            raise RuntimeError(self.error)
        self.share_id = hello["share_id"]
        self.url = VIEW_BASE + self.share_id
        self._task = asyncio.create_task(self._pump())

    async def _pump(self) -> None:
        """Drain the queue to the relay. Never let sharing stall the terminal."""
        try:
            while True:
                data = await self._queue.get()
                if data is None:
                    break
                await self._ws.send(json.dumps({"type": "output", "data": data}))
        except Exception as exc:
            self.error = str(exc)
        finally:
            await self._close_ws()

    def push(self, data: str) -> None:
        """Called from _emit. Must never raise and never block the session."""
        if not self.active:
            return
        try:
            self._queue.put_nowait(data)
        except asyncio.QueueFull:
            pass  # drop frames rather than back-pressure the terminal

    async def stop(self) -> None:
        self.share_id = None
        try:
            if self._ws:
                await self._ws.send(json.dumps({"type": "end"}))
        except Exception:
            pass
        try:
            self._queue.put_nowait(None)
        except Exception:
            pass
        await self._close_ws()

    async def _close_ws(self) -> None:
        try:
            if self._ws:
                await self._ws.close()
        except Exception:
            pass
        self._ws = None


def _client_id() -> str:
    """Stable per-install id so the relay's one-share-per-client limit works."""
    from .auth import TOKEN
    import hashlib
    return hashlib.sha256(TOKEN.encode()).hexdigest()[:32]


# tab_id -> Share
SHARES: dict[str, Share] = {}


def get(tab_id: str) -> Share | None:
    sh = SHARES.get(tab_id)
    if sh and not sh.active:
        SHARES.pop(tab_id, None)
        return None
    return sh
