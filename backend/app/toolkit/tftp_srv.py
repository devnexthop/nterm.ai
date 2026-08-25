from __future__ import annotations

import asyncio
from pathlib import Path

OPCODE_RRQ, OPCODE_WRQ, OPCODE_DATA, OPCODE_ACK, OPCODE_ERROR = 1, 2, 3, 4, 5
BLOCK = 512


def _u16(n: int) -> bytes:
    return n.to_bytes(2, "big")


def _read_u16(data: bytes, i: int) -> int:
    return int.from_bytes(data[i : i + 2], "big")


class TftpService:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.transport = None
        self.bind = "0.0.0.0"
        self.port = 69
        self._sessions: dict[tuple, _Xfer] = {}

    @property
    def running(self) -> bool:
        return self.transport is not None

    def safe_path(self, name: str) -> Path | None:
        cleaned = name.replace("\\", "/").lstrip("/")
        if ".." in cleaned.split("/"):
            return None
        path = (self.root / cleaned).resolve()
        try:
            path.relative_to(self.root.resolve())
        except ValueError:
            return None
        return path

    def list_files(self) -> list[dict]:
        files = []
        for p in sorted(self.root.rglob("*")):
            if p.is_file():
                files.append(
                    {
                        "name": str(p.relative_to(self.root)),
                        "size": p.stat().st_size,
                    }
                )
        return files

    async def start(self, bind: str, port: int):
        await self.stop()
        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            lambda: _TftpProtocol(self),
            local_addr=(bind, port),
        )
        self.transport = transport
        self.bind = bind
        self.port = port

    async def stop(self):
        if self.transport:
            self.transport.close()
            self.transport = None
        self._sessions.clear()


class _Xfer:
    def __init__(self, kind: str, path: Path, block: int = 0):
        self.kind = kind
        self.path = path
        self.block = block
        self.fh = None
        self.last_len = BLOCK


class _TftpProtocol(asyncio.DatagramProtocol):
    def __init__(self, svc: TftpService):
        self.svc = svc
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data: bytes, addr):
        if len(data) < 2:
            return
        op = _read_u16(data, 0)
        if op in (OPCODE_RRQ, OPCODE_WRQ):
            parts = data[2:].split(b"\x00")
            name = parts[0].decode("utf-8", errors="replace")
            path = self.svc.safe_path(name)
            if path is None:
                self._error(addr, 2, "Illegal path")
                return
            if op == OPCODE_RRQ:
                if not path.is_file():
                    self._error(addr, 1, "File not found")
                    return
                xfer = _Xfer("rrq", path, 0)
                xfer.fh = path.open("rb")
                self.svc._sessions[addr] = xfer
                self._send_data(addr, xfer)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                xfer = _Xfer("wrq", path, 0)
                xfer.fh = path.open("wb")
                self.svc._sessions[addr] = xfer
                self.transport.sendto(_u16(OPCODE_ACK) + _u16(0), addr)
        elif op == OPCODE_ACK:
            xfer = self.svc._sessions.get(addr)
            if not xfer or xfer.kind != "rrq":
                return
            acked = _read_u16(data, 2)
            if acked == xfer.block:
                if xfer.last_len < BLOCK:
                    self._close(addr)
                else:
                    self._send_data(addr, xfer)
        elif op == OPCODE_DATA:
            xfer = self.svc._sessions.get(addr)
            if not xfer or xfer.kind != "wrq":
                return
            block = _read_u16(data, 2)
            payload = data[4:]
            xfer.fh.write(payload)
            xfer.block = block
            self.transport.sendto(_u16(OPCODE_ACK) + _u16(block), addr)
            if len(payload) < BLOCK:
                self._close(addr)

    def _send_data(self, addr, xfer: _Xfer):
        chunk = xfer.fh.read(BLOCK)
        xfer.block += 1
        xfer.last_len = len(chunk)
        self.transport.sendto(_u16(OPCODE_DATA) + _u16(xfer.block) + chunk, addr)

    def _error(self, addr, code: int, msg: str):
        self.transport.sendto(
            _u16(OPCODE_ERROR) + _u16(code) + msg.encode() + b"\x00", addr
        )

    def _close(self, addr):
        xfer = self.svc._sessions.pop(addr, None)
        if xfer and xfer.fh:
            xfer.fh.close()
