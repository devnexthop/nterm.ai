from __future__ import annotations

from ..config import DATA_DIR, DEFAULT_DHCP_PORT, DEFAULT_SYSLOG_PORT, DEFAULT_TFTP_PORT
from .dhcp_srv import DhcpService, default_dhcp_config
from .syslog_srv import SyslogService
from .tftp_srv import TftpService

syslog = SyslogService()
tftp = TftpService(DATA_DIR / "tftp")
dhcp = DhcpService()

DEFAULTS = {
    "syslog": {"enabled": False, "bind": "0.0.0.0", "port": DEFAULT_SYSLOG_PORT, "config": {}},
    "tftp": {"enabled": False, "bind": "0.0.0.0", "port": DEFAULT_TFTP_PORT, "config": {}},
    "dhcp": {
        "enabled": False,
        "bind": "0.0.0.0",
        "port": DEFAULT_DHCP_PORT,
        "config": default_dhcp_config(),
    },
}


def status() -> dict:
    return {
        "syslog": {
            **DEFAULTS["syslog"],
            "enabled": syslog.running,
            "running": syslog.running,
            "bind": syslog.bind,
            "port": syslog.port,
        },
        "tftp": {
            **DEFAULTS["tftp"],
            "enabled": tftp.running,
            "running": tftp.running,
            "bind": tftp.bind,
            "port": tftp.port,
            "files": tftp.list_files(),
            "root": str(tftp.root),
        },
        "dhcp": {
            **DEFAULTS["dhcp"],
            "enabled": dhcp.running,
            "running": dhcp.running,
            "bind": dhcp.bind,
            "port": dhcp.port,
            "config": dhcp.config,
        },
    }


async def apply(name: str, spec: dict):
    bind = spec.get("bind") or "0.0.0.0"
    if name == "syslog":
        port = int(spec.get("port") or DEFAULT_SYSLOG_PORT)
        if spec.get("enabled"):
            await syslog.start(bind, port)
        else:
            await syslog.stop()
    elif name == "tftp":
        port = int(spec.get("port") or DEFAULT_TFTP_PORT)
        if spec.get("enabled"):
            await tftp.start(bind, port)
        else:
            await tftp.stop()
    elif name == "dhcp":
        port = int(spec.get("port") or DEFAULT_DHCP_PORT)
        if spec.get("enabled"):
            await dhcp.start(bind, port, spec.get("config") or {})
        else:
            await dhcp.stop()
    else:
        raise ValueError(f"Unknown toolkit service {name}")
    return status()[name]
