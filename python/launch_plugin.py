"""Arranque usado por el complemento de Inventor. Instala dependencias solo si faltan."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "python" / "requirements.txt"


def _ready() -> bool:
    try:
        import webview  # noqa: F401
        import win32com.client  # noqa: F401
    except Exception:
        return False
    return True


def main() -> int:
    if not _ready():
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)])
    return subprocess.call(
        [sys.executable, str(ROOT / "python" / "host.py")],
        creationflags=0x08000000,
    )


if __name__ == "__main__":
    raise SystemExit(main())
