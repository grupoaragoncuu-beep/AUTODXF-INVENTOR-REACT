"""Progreso de exportar JPG (espejo de pick_status: archivo + sondeo)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROGRESS_PATH = ROOT / "config" / "acotacion_progress.json"

_started = 0.0


def reset_progress(total: int = 0, piece: str = "Preparando…") -> None:
    global _started
    _started = time.time()
    write_progress(
        current=0,
        total=max(0, int(total)),
        piece=piece,
        marca="",
        photos=0,
        phase="inicio",
        done=False,
        result=None,
        message="",
    )


def write_progress(
    *,
    current: int,
    total: int,
    piece: str,
    marca: str = "",
    photos: int = 0,
    phase: str = "piezas",
    done: bool = False,
    result: dict | None = None,
    message: str = "",
) -> None:
    elapsed = max(0.0, time.time() - (_started or time.time()))
    cur = max(0, int(current))
    tot = max(0, int(total))
    eta = 0.0
    if cur > 0 and tot > cur:
        eta = (elapsed / cur) * (tot - cur)
    elif done:
        eta = 0.0
    payload = {
        "running": not done,
        "done": done,
        "current": cur,
        "total": tot,
        "piece": str(piece or ""),
        "marca": str(marca or ""),
        "photos": int(photos),
        "phase": phase,
        "elapsed": round(elapsed, 1),
        "eta": round(eta, 1),
        "percent": 100 if done else 99 if phase == "bd" else (int(100 * cur / tot) if tot else 0),
        "message": message,
        "result": result,
    }
    PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False)
    tmp = PROGRESS_PATH.with_name(f"acotacion_progress.{os.getpid()}.tmp")
    try:
        tmp.write_text(data, encoding="utf-8")
        for attempt in range(12):
            try:
                os.replace(str(tmp), str(PROGRESS_PATH))
                return
            except OSError:
                time.sleep(0.05 * (attempt + 1))
        PROGRESS_PATH.write_text(data, encoding="utf-8")
    except OSError:
        pass
    try:
        if tmp.exists():
            tmp.unlink()
    except OSError:
        pass


def read_progress() -> dict:
    if not PROGRESS_PATH.is_file():
        return {
            "running": False,
            "done": False,
            "current": 0,
            "total": 0,
            "piece": "",
            "marca": "",
            "photos": 0,
            "phase": "",
            "elapsed": 0,
            "eta": 0,
            "percent": 0,
            "message": "",
            "result": None,
        }
    try:
        data = json.loads(PROGRESS_PATH.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}
