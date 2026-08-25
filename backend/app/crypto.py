from cryptography.fernet import Fernet, InvalidToken
from .config import MASTER_KEY_PATH
import os


def _load_key() -> bytes:
    env = os.environ.get("RELAY_MASTER_KEY")
    if env:
        raw = env.encode()
        if len(raw) == 44 and raw.endswith(b"="):
            return raw
        from hashlib import sha256
        import base64

        return base64.urlsafe_b64encode(sha256(raw).digest())
    if MASTER_KEY_PATH.exists():
        return MASTER_KEY_PATH.read_bytes().strip()
    key = Fernet.generate_key()
    MASTER_KEY_PATH.write_bytes(key)
    try:
        MASTER_KEY_PATH.chmod(0o600)
    except OSError:
        pass
    return key


_fernet = Fernet(_load_key())


def encrypt(value: str | None) -> str | None:
    if not value:
        return None
    return _fernet.encrypt(value.encode()).decode()


def decrypt(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet.decrypt(value.encode()).decode()
    except InvalidToken:
        return None
