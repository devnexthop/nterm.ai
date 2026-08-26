from pathlib import Path
import os
import sys

APP_NAME = "NTerm"
APP_DOMAIN = "nterm.ai"

def _bundle_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def _read_version() -> str:
    """Single source of truth: the VERSION file at the repo root.

    Falls back to the baked-in default when running from an installed bundle
    where the repo layout is gone.
    """
    for base in (Path(__file__).resolve().parents[2], _bundle_dir()):
        f = base / "VERSION"
        if f.exists():
            v = f.read_text(encoding="utf-8").strip()
            if v:
                return v
    return "0.1.0"


APP_VERSION = _read_version()

# Stamped at image build time (docker build --build-arg GIT_SHA=$(git rev-parse --short HEAD)).
# Without it you cannot tell which commit produced a running container.
BUILD_SHA = os.environ.get("NTERM_BUILD_SHA", "dev")


def _default_data_dir() -> Path:
    env = os.environ.get("NTERM_DATA_DIR") or os.environ.get("RELAY_DATA_DIR")
    if env:
        return Path(env)
    if os.environ.get("NTERM_DESKTOP") == "1":
        home = Path.home()
        if sys.platform == "darwin":
            return home / "Library" / "Application Support" / "NTerm"
        if sys.platform == "win32":
            return Path(os.environ.get("APPDATA", home / "AppData" / "Roaming")) / "NTerm"
        return home / ".nterm"
    return Path(__file__).resolve().parents[2] / "data"


DATA_DIR = _default_data_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)
for _name in ("logs", "extensions", "configs", "tftp", "syslog"):
    (DATA_DIR / _name).mkdir(parents=True, exist_ok=True)

DEFAULT_SYSLOG_PORT = int(os.environ.get("NTERM_SYSLOG_PORT") or os.environ.get("RELAY_SYSLOG_PORT", "514"))
DEFAULT_TFTP_PORT = int(os.environ.get("NTERM_TFTP_PORT") or os.environ.get("RELAY_TFTP_PORT", "69"))
DEFAULT_DHCP_PORT = int(os.environ.get("NTERM_DHCP_PORT") or os.environ.get("RELAY_DHCP_PORT", "67"))
BIND_HOST = os.environ.get("NTERM_HOST", "127.0.0.1" if os.environ.get("NTERM_DESKTOP") == "1" else "0.0.0.0")
BIND_PORT = int(os.environ.get("NTERM_PORT", "8787"))

DB_PATH = DATA_DIR / "nterm.db"
MASTER_KEY_PATH = DATA_DIR / ".master_key"
STATIC_DIR = _bundle_dir() / "static"
BUILTIN_EXT_DIR = _bundle_dir() / "builtin_extensions"
