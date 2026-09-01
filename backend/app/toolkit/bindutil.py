from __future__ import annotations

import errno
import os
from pathlib import Path

# Windows WSA codes (OSError.errno on Win32).
_WSAEADDRINUSE = 10048
_WSAEACCES = 10013

IN_USE = {errno.EADDRINUSE, getattr(errno, "WSAEADDRINUSE", _WSAEADDRINUSE), 48, 98, _WSAEADDRINUSE}
DENIED = {errno.EACCES, getattr(errno, "WSAEACCES", _WSAEACCES), 13, _WSAEACCES}


def in_container() -> bool:
    return Path("/.dockerenv").exists()


def lab_ports_published() -> bool:
    return os.environ.get("NTERM_LAB_PORTS", "").strip() in {"1", "true", "yes"}


def exposure() -> dict:
    """How far a toolkit bind actually reaches. Opening the page does not bind."""
    container = in_container()
    lab = lab_ports_published()
    if container and not lab:
        return {
            "mode": "container",
            "host_ports": False,
            "note": (
                "Start listens only inside the NTerm container. This PC’s UDP 514 / 69 / 67 "
                "stay free. Gear on the LAN cannot reach these services until you recreate "
                "with docker-compose.lab.yml. If those host ports are already taken, Docker "
                "refuses to start NTerm at all — it will not steal them."
            ),
        }
    if container and lab:
        return {
            "mode": "lab",
            "host_ports": True,
            "note": (
                "Lab profile published UDP 514 / 69 / 67 on this machine when the container "
                "started. Occupied ports fail at `docker compose up`, not on the Start button. "
                "NTerm does not take a port that is already bound."
            ),
        }
    return {
        "mode": "native",
        "host_ports": True,
        "note": (
            "Start binds UDP on this PC. If another process already owns the port, Start "
            "fails with an error and that process keeps it. Ports below 1024 need root, "
            "or pick a higher port."
        ),
    }


def explain_bind_error(exc: BaseException, *, name: str, port: int) -> str:
    en = getattr(exc, "errno", None)
    if en in IN_USE:
        return (
            f"UDP {port} is already in use. {name} was not started and NTerm did not take "
            "the port. Stop the other listener or pick a different port."
        )
    if en in DENIED:
        return (
            f"Cannot bind UDP {port} (permission denied). Ports below 1024 need root, the "
            "Docker lab profile, or a higher port."
        )
    return f"{name} failed to bind UDP {port}: {exc}"
