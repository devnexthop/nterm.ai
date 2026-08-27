"""Native NTerm session-tree export and vault wrapping.

Structure files never contain secrets. Vault backups wrap decrypted secrets with
a passphrase (PBKDF2 + Fernet) so the file can move between machines — not the
install master key.
"""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from .crypto import decrypt
from .models import Customer, SavedSession

EXPORT_VERSION = 1
KDF_ITERS = 390_000


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _session_struct(row: SavedSession) -> dict:
    return {
        "name": row.name,
        "kind": row.kind,
        "device_type": row.device_type,
        "host": row.host,
        "port": row.port,
        "username": row.username,
        "jump_host": row.jump_host,
        "notes": row.notes,
        "logging_enabled": row.logging_enabled,
        "post_login": row.post_login,
        "folder": (row.folder or "").strip(),
        "baud": row.baud or 9600,
    }


def _session_vault(row: SavedSession) -> dict:
    body = _session_struct(row)
    body["password"] = decrypt(row.password_enc) or ""
    body["enable_password"] = decrypt(row.enable_password_enc) or ""
    body["private_key"] = decrypt(row.private_key_enc) or ""
    return body


def build_tree(customers: list[Customer], *, vault: bool) -> dict:
    out = []
    for c in customers:
        sessions = [_session_vault(s) if vault else _session_struct(s) for s in c.sessions]
        out.append({
            "name": c.name,
            "color": c.color,
            "notes": c.notes,
            "sessions": sessions,
        })
    return {
        "nterm_export": EXPORT_VERSION,
        "kind": "vault" if vault else "structure",
        "exported_at": _now(),
        "customers": out,
    }


def _fernet_from_passphrase(passphrase: str, salt: bytes, iterations: int) -> Fernet:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
    )
    key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))
    return Fernet(key)


def wrap_vault(tree: dict, passphrase: str) -> dict:
    if not passphrase or len(passphrase) < 8:
        raise ValueError("Passphrase must be at least 8 characters")
    salt = os.urandom(16)
    f = _fernet_from_passphrase(passphrase, salt, KDF_ITERS)
    blob = f.encrypt(json.dumps(tree, separators=(",", ":")).encode("utf-8")).decode("ascii")
    return {
        "nterm_export": EXPORT_VERSION,
        "kind": "vault-wrapped",
        "exported_at": _now(),
        "kdf": {
            "name": "pbkdf2-sha256",
            "iterations": KDF_ITERS,
            "salt": base64.b64encode(salt).decode("ascii"),
        },
        "wrapped": blob,
    }


def unwrap_vault(doc: dict, passphrase: str) -> dict:
    kdf = doc.get("kdf") or {}
    try:
        salt = base64.b64decode(kdf["salt"])
        iterations = int(kdf.get("iterations") or KDF_ITERS)
    except Exception as exc:
        raise ValueError("That file is not a valid NTerm vault backup") from exc
    try:
        f = _fernet_from_passphrase(passphrase, salt, iterations)
        raw = f.decrypt(doc["wrapped"].encode("ascii"))
    except (InvalidToken, KeyError, TypeError) as exc:
        raise ValueError("Wrong passphrase, or the file is damaged") from exc
    tree = json.loads(raw.decode("utf-8"))
    if not is_nterm_tree(tree):
        raise ValueError("Decrypted backup was not an NTerm tree")
    return tree


def is_nterm_doc(obj: object) -> bool:
    return isinstance(obj, dict) and obj.get("nterm_export") == EXPORT_VERSION


def is_nterm_tree(obj: object) -> bool:
    return is_nterm_doc(obj) and obj.get("kind") in ("structure", "vault")


def is_wrapped(obj: object) -> bool:
    return is_nterm_doc(obj) and obj.get("kind") == "vault-wrapped"


def parse_json(content: str) -> dict | None:
    text = (content or "").lstrip()
    if not text.startswith("{"):
        return None
    try:
        obj = json.loads(content)
    except json.JSONDecodeError:
        return None
    return obj if is_nterm_doc(obj) else None


def tree_to_rows(tree: dict) -> list[dict]:
    """Flatten a native tree into the same row shape as other importers."""
    rows: list[dict] = []
    for cust in tree.get("customers") or []:
        cname = (cust.get("name") or "Imported").strip()[:200]
        for s in cust.get("sessions") or []:
            folder = (s.get("folder") or "").strip()
            rows.append({
                "name": (s.get("name") or s.get("host") or "session")[:200],
                "kind": s.get("kind") or "ssh",
                "device_type": s.get("device_type") or "generic",
                "host": (s.get("host") or "")[:255],
                "port": int(s.get("port") or 22),
                "username": (s.get("username") or "")[:200],
                "jump_host": (s.get("jump_host") or "")[:255],
                "notes": (s.get("notes") or "")[:4000],
                "post_login": s.get("post_login") or "",
                "logging_enabled": bool(s.get("logging_enabled", True)),
                "folder": folder[:400],
                "baud": int(s.get("baud") or 9600),
                "group": folder or cname,
                "customer_name": cname,
                "customer_color": cust.get("color") or "#ffb020",
                "password": s.get("password") or "",
                "enable_password": s.get("enable_password") or "",
                "private_key": s.get("private_key") or "",
            })
    return rows
