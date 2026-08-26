"""SSH host-key trust store (TOFU).

terminal_hub previously passed known_hosts=None to asyncssh, which disables host
key verification outright — every SSH connection was MITM-able, on exactly the
mgmt VLANs and jump-host paths this tool is pointed at.

This module implements trust-on-first-use with the property that actually
matters: a key that CHANGES is refused. First contact is recorded and the
fingerprint surfaced to the operator.

Known limitation, stated plainly: first contact is auto-accepted rather than
prompted, so a MITM present at the very first connection is not caught. An
interactive accept/reject prompt is the follow-up. Refusing changed keys is the
control that stops the common attack.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from .config import DATA_DIR

STORE = DATA_DIR / "known_hosts.json"


class HostKeyChanged(Exception):
    """Raised when a host presents a key different from the pinned one."""

    def __init__(self, host: str, port: int, old_fp: str, new_fp: str):
        self.host, self.port, self.old_fp, self.new_fp = host, port, old_fp, new_fp
        super().__init__(
            f"Host key for {host}:{port} has CHANGED.\r\n"
            f"  pinned:    {old_fp}\r\n"
            f"  presented: {new_fp}\r\n"
            "Refusing to connect. If this change is expected (device rebuilt, "
            "key rotated), remove the entry from Settings > Known hosts."
        )


def fingerprint(key_data: bytes) -> str:
    """OpenSSH-style SHA256 fingerprint."""
    digest = hashlib.sha256(key_data).digest()
    return "SHA256:" + base64.b64encode(digest).decode().rstrip("=")


def _load() -> dict:
    if not STORE.exists():
        return {}
    try:
        return json.loads(STORE.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def _save(data: dict) -> None:
    STORE.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    try:
        STORE.chmod(0o600)
    except OSError:
        pass


def entry_key(host: str, port: int) -> str:
    return f"{host}:{port}"


def get(host: str, port: int) -> dict | None:
    return _load().get(entry_key(host, port))


def list_all() -> list[dict]:
    return [{"host_port": k, **v} for k, v in sorted(_load().items())]


def forget(host_port: str) -> bool:
    data = _load()
    if host_port in data:
        data.pop(host_port)
        _save(data)
        return True
    return False


def check_and_record(host: str, port: int, key_data: bytes, key_type: str) -> tuple[str, bool]:
    """Verify a presented host key against the store.

    Returns (fingerprint, first_seen). Raises HostKeyChanged on mismatch.
    """
    fp = fingerprint(key_data)
    data = _load()
    k = entry_key(host, port)
    existing = data.get(k)

    if existing:
        if existing.get("fingerprint") != fp:
            raise HostKeyChanged(host, port, existing.get("fingerprint", "?"), fp)
        return fp, False

    from datetime import datetime, timezone
    data[k] = {
        "fingerprint": fp,
        "key_type": key_type,
        "first_seen": datetime.now(timezone.utc).isoformat(),
    }
    _save(data)
    return fp, True
