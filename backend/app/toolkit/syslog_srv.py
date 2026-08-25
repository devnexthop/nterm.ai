from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import SyslogEvent

PRI_RE = re.compile(r"^<(\d{1,3})>")
subscribers: list[Callable[[dict], None]] = []


def subscribe(cb: Callable[[dict], None]) -> None:
    subscribers.append(cb)


def event_to_dict(ev: SyslogEvent) -> dict:
    return {
        "id": ev.id,
        "received_at": ev.received_at.isoformat() if ev.received_at else None,
        "source_ip": ev.source_ip,
        "facility": ev.facility,
        "severity": ev.severity,
        "hostname": ev.hostname,
        "app_name": ev.app_name,
        "message": ev.message,
        "raw": ev.raw,
    }


def parse_syslog(raw: str, source_ip: str) -> dict:
    facility, severity = 16, 6
    rest = raw
    m = PRI_RE.match(raw)
    if m:
        pri = int(m.group(1))
        facility, severity = divmod(pri, 8)
        rest = raw[m.end() :]
    hostname = ""
    app = ""
    msg = rest
    parts = rest.split(None, 3)
    if len(parts) >= 4 and parts[0][:3].isalpha():
        hostname = parts[3].split()[0] if len(parts) > 3 else ""
        msg = rest
    elif parts:
        hostname = parts[0]
        msg = rest[len(parts[0]) :].lstrip() if len(parts) > 1 else rest
    return {
        "source_ip": source_ip,
        "facility": facility,
        "severity": severity,
        "hostname": hostname[:200],
        "app_name": app,
        "message": msg[:8000],
        "raw": raw[:8000],
    }


def persist(parsed: dict) -> dict:
    db: Session = SessionLocal()
    try:
        ev = SyslogEvent(
            received_at=datetime.now(timezone.utc),
            **parsed,
        )
        db.add(ev)
        db.commit()
        db.refresh(ev)
        payload = event_to_dict(ev)
    finally:
        db.close()
    for cb in list(subscribers):
        try:
            cb(payload)
        except Exception:
            pass
    return payload


class _SyslogProtocol(asyncio.DatagramProtocol):
    def datagram_received(self, data: bytes, addr):
        raw = data.decode("utf-8", errors="replace").rstrip("\x00")
        parsed = parse_syslog(raw, addr[0])
        persist(parsed)


class SyslogService:
    def __init__(self):
        self.transport = None
        self.bind = "0.0.0.0"
        self.port = 514

    @property
    def running(self) -> bool:
        return self.transport is not None

    async def start(self, bind: str, port: int):
        await self.stop()
        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            lambda: _SyslogProtocol(),
            local_addr=(bind, port),
        )
        self.transport = transport
        self.bind = bind
        self.port = port

    async def stop(self):
        if self.transport:
            self.transport.close()
            self.transport = None
