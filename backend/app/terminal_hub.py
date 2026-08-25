from __future__ import annotations

import asyncio
import os
import pty
import struct
import termios
import fcntl
from datetime import datetime, timezone
from pathlib import Path

import asyncssh
from fastapi import WebSocket
from sqlalchemy.orm import Session

from .config import DATA_DIR
from .crypto import decrypt
from .device_profiles import PROFILES, SSH_ALGORITHMS
from .models import SavedSession, SessionLog
from .simulators import DeviceSimulator


class LiveTab:
    def __init__(self, tab_id: str, session: SavedSession):
        self.tab_id = tab_id
        self.session_id = session.id
        self.kind = session.kind
        self.ws: WebSocket | None = None
        self.log_path: Path | None = None
        self.log_id: int | None = None
        self.bytes_written = 0
        self.closed = False
        self.conn = None
        self.process = None
        self.master_fd = None
        self.simulator: DeviceSimulator | None = None
        self.reader_task: asyncio.Task | None = None

    async def send_json(self, payload: dict):
        if self.ws:
            try:
                await self.ws.send_json(payload)
            except Exception:
                pass

    def write_log(self, data: str):
        if not self.log_path:
            return
        with self.log_path.open("a", encoding="utf-8", errors="replace") as fh:
            fh.write(data)
        self.bytes_written += len(data.encode("utf-8", errors="replace"))


class TerminalHub:
    def __init__(self):
        self.tabs: dict[str, LiveTab] = {}

    def get(self, tab_id: str) -> LiveTab | None:
        return self.tabs.get(tab_id)

    async def attach(self, ws: WebSocket, tab_id: str, session: SavedSession, db: Session):
        tab = LiveTab(tab_id, session)
        tab.ws = ws
        if session.logging_enabled:
            self._open_log(tab, session, db)
        self.tabs[tab_id] = tab
        await tab.send_json({"type": "status", "state": "connecting", "session_id": session.id})
        try:
            if session.kind == "simulator":
                await self._run_simulator(tab, session)
            elif session.kind == "local":
                await self._run_local(tab, session)
            else:
                await self._run_ssh(tab, session)
        except Exception as exc:
            await tab.send_json({"type": "status", "state": "error", "message": str(exc)})
        finally:
            await self.close(tab_id, db)

    def _open_log(self, tab: LiveTab, session: SavedSession, db: Session):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        folder = DATA_DIR / "logs" / f"session-{session.id}"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{stamp}-{tab.tab_id[:8]}.log"
        header = (
            f"=== NTerm session log ===\n"
            f"session={session.name} id={session.id} kind={session.kind}\n"
            f"host={session.host}:{session.port} user={session.username}\n"
            f"started={stamp}\n"
            f"=========================\n"
        )
        path.write_text(header, encoding="utf-8")
        row = SessionLog(session_id=session.id, path=str(path), bytes_written=len(header))
        db.add(row)
        db.commit()
        db.refresh(row)
        tab.log_path = path
        tab.log_id = row.id
        tab.bytes_written = len(header)

    async def _run_simulator(self, tab: LiveTab, session: SavedSession):
        sim = DeviceSimulator(session.device_type, session.name.replace(" ", "-")[:16] or "R1")
        tab.simulator = sim
        await tab.send_json({"type": "status", "state": "connected"})
        await self._emit(tab, sim.banner)
        while not tab.closed and tab.ws:
            try:
                msg = await asyncio.wait_for(tab.ws.receive_json(), timeout=30)
            except asyncio.TimeoutError:
                continue
            except Exception:
                break
            await self._handle_client(tab, msg)

    async def _run_local(self, tab: LiveTab, session: SavedSession):
        master, slave = pty.openpty()
        tab.master_fd = master
        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        proc = await asyncio.create_subprocess_exec(
            os.environ.get("SHELL", "/bin/bash"),
            "-l",
            stdin=slave,
            stdout=slave,
            stderr=slave,
            start_new_session=True,
            env=env,
        )
        os.close(slave)
        tab.process = proc
        loop = asyncio.get_running_loop()
        await tab.send_json({"type": "status", "state": "connected"})

        def _on_read():
            try:
                data = os.read(master, 4096)
            except OSError:
                data = b""
            if data:
                asyncio.create_task(self._emit(tab, data.decode("utf-8", errors="replace")))

        loop.add_reader(master, _on_read)
        try:
            while not tab.closed and tab.ws and proc.returncode is None:
                try:
                    msg = await asyncio.wait_for(tab.ws.receive_json(), timeout=1)
                except asyncio.TimeoutError:
                    continue
                except Exception:
                    break
                await self._handle_client(tab, msg)
        finally:
            loop.remove_reader(master)
            if proc.returncode is None:
                proc.terminate()

    async def _run_ssh(self, tab: LiveTab, session: SavedSession):
        password = decrypt(session.password_enc)
        enable = decrypt(session.enable_password_enc)
        key_text = decrypt(session.private_key_enc)
        client_keys = []
        if key_text:
            client_keys.append(asyncssh.import_private_key(key_text, passphrase=password))
        opts = dict(
            host=session.host,
            port=session.port or 22,
            username=session.username or None,
            password=password,
            client_keys=client_keys or None,
            known_hosts=None,
            login_timeout=20,
            keepalive_interval=30,
        )
        try:
            conn = await asyncssh.connect(**opts, **SSH_ALGORITHMS)
        except (ValueError, TypeError, asyncssh.Error):
            conn = await asyncssh.connect(**opts)
        tab.conn = conn
        proc = await conn.create_process(term_type="xterm-256color", encoding="utf-8")
        tab.process = proc
        await tab.send_json({"type": "status", "state": "connected"})

        async def pump():
            try:
                while True:
                    data = await proc.stdout.read(4096)
                    if not data:
                        break
                    await self._emit(tab, data)
            except Exception:
                pass

        pump_task = asyncio.create_task(pump())
        profile = PROFILES.get(session.device_type, PROFILES["generic"])
        commands = list(profile.get("paging") or [])
        if session.post_login:
            commands.extend([ln for ln in session.post_login.splitlines() if ln.strip()])
        if commands:
            await asyncio.sleep(0.6)
            for cmd in commands:
                proc.stdin.write(cmd + "\n")
        if enable and session.device_type.startswith("cisco"):
            await asyncio.sleep(0.3)
            proc.stdin.write("enable\n")
            await asyncio.sleep(0.3)
            proc.stdin.write(enable + "\n")
        try:
            while not tab.closed and tab.ws:
                try:
                    msg = await asyncio.wait_for(tab.ws.receive_json(), timeout=1)
                except asyncio.TimeoutError:
                    continue
                except Exception:
                    break
                await self._handle_client(tab, msg)
        finally:
            pump_task.cancel()
            conn.close()

    async def _handle_client(self, tab: LiveTab, msg: dict):
        kind = msg.get("type")
        if kind == "input":
            await self.send_input(tab.tab_id, msg.get("data") or "")
        elif kind == "resize":
            await self.resize(tab.tab_id, int(msg.get("cols") or 80), int(msg.get("rows") or 24))

    async def send_input(self, tab_id: str, data: str):
        tab = self.tabs.get(tab_id)
        if not tab or not data:
            return
        if tab.simulator:
            out = tab.simulator.feed(data)
            await self._emit(tab, out)
            return
        if tab.kind == "local" and tab.master_fd is not None:
            os.write(tab.master_fd, data.encode())
            return
        proc = tab.process
        if proc is not None and getattr(proc, "stdin", None):
            proc.stdin.write(data)

    async def resize(self, tab_id: str, cols: int, rows: int):
        tab = self.tabs.get(tab_id)
        if not tab:
            return
        if tab.kind == "local" and tab.master_fd is not None:
            winsz = struct.pack("HHHH", rows, cols, 0, 0)
            try:
                fcntl.ioctl(tab.master_fd, termios.TIOCSWINSZ, winsz)
            except OSError:
                pass
        proc = tab.process
        if proc is not None and hasattr(proc, "change_terminal_size"):
            try:
                proc.change_terminal_size(cols, rows)
            except Exception:
                pass

    async def broadcast(self, tab_ids: list[str], command: str, newline: bool = True):
        payload = command + ("\n" if newline and not command.endswith("\n") else "")
        for tab_id in tab_ids:
            await self.send_input(tab_id, payload)

    async def _emit(self, tab: LiveTab, data: str):
        if not data:
            return
        tab.write_log(data)
        await tab.send_json({"type": "output", "data": data})

    async def close(self, tab_id: str, db: Session | None = None):
        tab = self.tabs.pop(tab_id, None)
        if not tab:
            return
        tab.closed = True
        await tab.send_json({"type": "status", "state": "closed"})
        if db and tab.log_id:
            row = db.get(SessionLog, tab.log_id)
            if row:
                row.ended_at = datetime.now(timezone.utc)
                row.bytes_written = tab.bytes_written
                db.commit()


hub = TerminalHub()
