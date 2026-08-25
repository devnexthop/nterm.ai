from sqlalchemy.orm import Session
from .models import AppSetting
from .crypto import encrypt, decrypt
import json

DEFAULTS = {
    "openai_model": "gpt-4.1-mini",
    "theme": "nexthop_dark",
    "font_size": "14",
    "ai_auto_context": "true",
}


def get_value(db: Session, key: str, default: str = "") -> str:
    row = db.get(AppSetting, key)
    if row:
        return row.value
    return DEFAULTS.get(key, default)


def set_value(db: Session, key: str, value: str) -> None:
    row = db.get(AppSetting, key)
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))
    db.commit()


def get_json(db: Session, key: str, default=None):
    raw = get_value(db, key, "")
    if not raw:
        return default if default is not None else {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default if default is not None else {}


def set_json(db: Session, key: str, value) -> None:
    set_value(db, key, json.dumps(value))


def get_openai_key(db: Session) -> str | None:
    return decrypt(get_value(db, "openai_api_key_enc"))


def set_openai_key(db: Session, key: str) -> None:
    set_value(db, "openai_api_key_enc", encrypt(key) or "")
