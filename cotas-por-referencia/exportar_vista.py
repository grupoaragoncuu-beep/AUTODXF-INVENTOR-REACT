"""Exporta COTAS_POR_REFERENCIA del tanque activo con el motor de control.json.

    python cotas-por-referencia/exportar_vista.py            # Inventor abierto: captura + JPG
    python cotas-por-referencia/exportar_vista.py snap.gz    # sin Inventor: JPG desde un snapshot
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from caras_referencia import _control_referencia


def _geometria(dest: Path, ctrl: dict, snap_path: str | None) -> int:
    import referencia_geo

    caras = [str(x).upper() for x in (ctrl.get("caras") or [])] or None
    t0 = time.time()
    if snap_path:
        snap = referencia_geo.leer_snapshot(snap_path)
    else:
        import referencia_snapshot
        from inventor_session import _active_assembly, _inventor

        assy = _active_assembly(_inventor())
        if assy is None:
            print("Abre el tanque (.iam) en Inventor.")
            return 1
        snap = referencia_snapshot.capturar(assy)
        referencia_snapshot.guardar(snap, dest / "_geometria.json.gz")
        print(f"captura {snap.get('stats')}", flush=True)
    job = Path(str(snap.get("assembly") or "JOB")).stem or "JOB"
    files: list[str] = []
    errors: list[str] = []
    res = referencia_geo.exportar(snap, dest, job, "in", files, errors, caras=caras)
    print(json.dumps({"ok": bool(files), "caras": res, "jpgs": len(files), "segundos": round(time.time() - t0, 1), "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if files else 1


def _inventor_8711(dest: Path, ctrl: dict) -> int:
    from caras_referencia import collect_caras, exportar_cara
    from inventor_session import _active_assembly, _inventor, _name

    caras_ok = {str(x).upper() for x in (ctrl.get("caras") or ["SEGM1"])}
    assy = _active_assembly(_inventor())
    if assy is None:
        print("Abre el tanque (.iam) en Inventor.")
        return 1
    job = _name(assy) or "JOB"
    files: list[str] = []
    errors: list[str] = []
    n = 0
    for row in collect_caras(assy, None):
        cara = str(row[0]).upper()
        if cara not in caras_ok:
            continue
        print(f"  {cara}…", flush=True)
        n += exportar_cara(files, errors, row[1], cara, row[2], job, "in", dest, ancla_occ=row[3] if len(row) > 3 else None)
    print(json.dumps({"ok": n > 0, "jpgs": n, "files": files, "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if n > 0 else 1


def main() -> int:
    ctrl = _control_referencia()
    dest = Path(__file__).resolve().parent / "salidas"
    dest.mkdir(parents=True, exist_ok=True)
    if str(ctrl.get("motor_vista") or "geometria").lower() == "inventor_8711":
        return _inventor_8711(dest, ctrl)
    return _geometria(dest, ctrl, sys.argv[1] if len(sys.argv) > 1 else None)


if __name__ == "__main__":
    raise SystemExit(main())
