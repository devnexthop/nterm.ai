from __future__ import annotations

import asyncio
import ipaddress
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import DhcpLease

BOOTREQUEST, BOOTREPLY = 1, 2
MAGIC = b"\x63\x82\x53\x63"
DHCPDISCOVER, DHCPOFFER, DHCPREQUEST, DHCPACK, DHCPNAK = 1, 2, 3, 5, 6


def _ip(addr: str) -> bytes:
    return ipaddress.IPv4Address(addr).packed


def _mac_str(chaddr: bytes, hlen: int) -> str:
    return ":".join(f"{b:02x}" for b in chaddr[:hlen])


def parse_options(data: bytes) -> dict:
    opts = {}
    i = 0
    while i < len(data):
        tag = data[i]
        if tag == 0:
            i += 1
            continue
        if tag == 255:
            break
        if i + 1 >= len(data):
            break
        ln = data[i + 1]
        opts[tag] = data[i + 2 : i + 2 + ln]
        i += 2 + ln
    return opts


def build_options(pairs: list[tuple[int, bytes]]) -> bytes:
    out = bytearray()
    for tag, val in pairs:
        out.append(tag)
        out.append(len(val))
        out.extend(val)
    out.append(255)
    return bytes(out)


class DhcpService:
    def __init__(self):
        self.transport = None
        self.bind = "0.0.0.0"
        self.port = 67
        self.config = default_dhcp_config()

    @property
    def running(self) -> bool:
        return self.transport is not None

    async def start(self, bind: str, port: int, config: dict):
        await self.stop()
        self.config = {**default_dhcp_config(), **(config or {})}
        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            lambda: _DhcpProtocol(self),
            local_addr=(bind, port),
            allow_broadcast=True,
        )
        self.transport = transport
        self.bind = bind
        self.port = port

    async def stop(self):
        if self.transport:
            self.transport.close()
            self.transport = None


def default_dhcp_config() -> dict:
    return {
        "pool_start": "10.88.0.50",
        "pool_end": "10.88.0.200",
        "subnet_mask": "255.255.255.0",
        "router": "10.88.0.1",
        "dns": "10.88.0.1",
        "lease_seconds": 3600,
        "server_id": "10.88.0.1",
        "tftp_server": "10.88.0.1",
        "bootfile": "ztp/cisconet.cfg",
        "domain": "lab.relay",
    }


def _next_ip(cfg: dict, used: set[str]) -> str | None:
    start = ipaddress.IPv4Address(cfg["pool_start"])
    end = ipaddress.IPv4Address(cfg["pool_end"])
    cur = int(start)
    while cur <= int(end):
        ip = str(ipaddress.IPv4Address(cur))
        if ip not in used:
            return ip
        cur += 1
    return None


class _DhcpProtocol(asyncio.DatagramProtocol):
    def __init__(self, svc: DhcpService):
        self.svc = svc
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data: bytes, addr):
        if len(data) < 240 or data[236:240] != MAGIC:
            return
        op = data[0]
        if op != BOOTREQUEST:
            return
        hlen = data[2]
        xid = data[4:8]
        chaddr = data[28:44]
        mac = _mac_str(chaddr, hlen or 6)
        opts = parse_options(data[240:])
        msg_type = opts.get(53, b"\x01")[0]
        cfg = self.svc.config
        db: Session = SessionLocal()
        try:
            used = {row.ip for row in db.query(DhcpLease).all()}
            existing = db.query(DhcpLease).filter(DhcpLease.mac == mac).one_or_none()
            if existing:
                ip = existing.ip
            else:
                ip = _next_ip(cfg, used)
                if not ip:
                    return
                existing = DhcpLease(mac=mac, ip=ip, hostname="", state="offered")
                db.add(existing)
            existing.issued_at = datetime.now(timezone.utc)
            existing.expires_at = existing.issued_at + timedelta(
                seconds=int(cfg.get("lease_seconds", 3600))
            )
            reply_type = DHCPOFFER if msg_type == DHCPDISCOVER else DHCPACK
            if msg_type == DHCPREQUEST:
                existing.state = "bound"
            else:
                existing.state = "offered"
            db.commit()
        finally:
            db.close()

        packet = self._offer(xid, chaddr, hlen or 6, ip, cfg, reply_type)
        dest = (addr[0] if addr[0] != "0.0.0.0" else "255.255.255.255", 68)
        try:
            self.transport.sendto(packet, dest)
        except OSError:
            self.transport.sendto(packet, ("255.255.255.255", 68))

    def _offer(self, xid, chaddr, hlen, ip, cfg, msg_type) -> bytes:
        pkt = bytearray(240)
        pkt[0] = BOOTREPLY
        pkt[1] = 1
        pkt[2] = hlen
        pkt[4:8] = xid
        pkt[16:20] = _ip(ip)
        pkt[20:24] = _ip(cfg.get("server_id", "10.88.0.1"))
        pkt[28:44] = chaddr
        boot = cfg.get("bootfile", "")
        pkt[108 : 108 + min(127, len(boot))] = boot.encode()[:127]
        pkt[236:240] = MAGIC
        options = build_options(
            [
                (53, bytes([msg_type])),
                (1, _ip(cfg["subnet_mask"])),
                (3, _ip(cfg["router"])),
                (6, _ip(cfg["dns"])),
                (51, int(cfg.get("lease_seconds", 3600)).to_bytes(4, "big")),
                (54, _ip(cfg["server_id"])),
                (15, cfg.get("domain", "lab.relay").encode()),
                (66, cfg.get("tftp_server", cfg["server_id"]).encode()),
                (67, cfg.get("bootfile", "").encode()),
                (150, _ip(cfg.get("tftp_server", cfg["server_id"]))),
            ]
        )
        return bytes(pkt) + options
