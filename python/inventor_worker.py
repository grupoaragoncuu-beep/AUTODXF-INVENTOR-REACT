"""Lee Inventor en un proceso aparte.

La ventana de AutoDXF carga WebView2, y ese componente deja inutilizable
GetActiveObject dentro del mismo proceso (MK_E_UNAVAILABLE).
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdin.reconfigure(encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")

from acotacion_progress import write_progress
from acotacion_run import run_acotacion
from inventor_session import (
    export_dxf,
    inventor_parts,
    inventor_snapshot,
    paint_lengths,
    run_component_pick,
    scan_shapes,
)


def _emit(payload: dict) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.stdout.write(json.dumps(payload, ensure_ascii=True))
    sys.stdout.flush()


def _arm_watchdog(seconds: int) -> None:
    def _boom() -> None:
        time.sleep(seconds)
        os._exit(3)

    threading.Thread(target=_boom, daemon=True).start()


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "snapshot"
    if command in {"snapshot", "paint"}:
        _arm_watchdog(12)
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        payload = {}

    if command == "parts":
        result = inventor_parts()
    elif command == "shapes":
        result = scan_shapes()
    elif command == "pick":
        result = run_component_pick(str(payload.get("mode") or "lengths"), payload)
    elif command == "paint":
        result = paint_lengths(
            payload.get("paths") if isinstance(payload.get("paths"), list) else [],
            payload.get("clear") if isinstance(payload.get("clear"), list) else [],
            str(payload.get("role") or "lengths"),
            class_name=str(payload.get("className") or payload.get("classification") or ""),
            color=str(payload.get("color") or ""),
        )
    elif command == "roles":
        from roles_inventor import run_roles_action

        result = run_roles_action(payload)
    elif command == "blocks":
        from bloques import run_blocks

        result = run_blocks(payload)
    elif command == "acotacion":
        result = run_acotacion(payload)
    elif command == "weld":
        from weld_anotation import run_weld_anotation

        result = run_weld_anotation(payload)
    elif command == "weld_nom":
        from weld_nomenclatura import run_inventor

        result = run_inventor(payload)
    elif command == "multibody":
        from multibody import run_multibody

        result = run_multibody()
    elif command == "export":
        result = export_dxf(
            str(payload.get("exportRoot") or ""),
            bool(payload.get("setASide", True)),
            bool(payload.get("writeCsv", True)),
            bool(payload.get("closeOpened", True)),
            bool(payload.get("usePartPlan", False)),
            payload.get("parts") if isinstance(payload.get("parts"), list) else [],
            str(payload.get("board") or "B1"),
            str(payload.get("job") or payload.get("jobName") or ""),
        )
        result["session"] = inventor_snapshot()
    else:
        result = inventor_snapshot()

    _emit(result)


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "snapshot"
    try:
        main()
    except Exception as ex:
        fail = {
            "inventorConnected": False,
            "inventorVersion": "",
            "assemblyName": "",
            "assemblyPath": "",
            "parts": [],
            "ok": False,
            "exported": 0,
            "csvPath": "",
            "message": str(ex),
        }
        try:
            if command == "weld":
                from weld_anotation import write_weld_progress

                write_weld_progress(
                    current=1,
                    total=1,
                    piece="Error",
                    phase="listo",
                    done=True,
                    result=fail,
                    message=str(ex),
                )
            else:
                write_progress(
                    current=1,
                    total=1,
                    piece="Error",
                    phase="listo",
                    done=True,
                    result=fail,
                    message=str(ex),
                )
        except Exception:
            pass
        _emit(fail)
