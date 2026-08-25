"""Desktop / PyInstaller entry for the NTerm engine."""

from __future__ import annotations

import os

import uvicorn

from .config import BIND_HOST, BIND_PORT
from .main import app


def main() -> None:
    os.environ.setdefault("NTERM_DESKTOP", os.environ.get("NTERM_DESKTOP", "1"))
    uvicorn.run(app, host=BIND_HOST, port=BIND_PORT, log_level="info")


if __name__ == "__main__":
    main()
