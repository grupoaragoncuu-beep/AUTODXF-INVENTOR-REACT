"""Lanza ColorimetriaInstancia.iLogicVb en el ensamble abierto. No usa el módulo AutoDXF."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULE = ROOT / "ColorimetriaInstancia.iLogicVb"
PICK_STOP = ROOT / "config" / "pick_stop.flag"
ILOGIC = "{3BDD8D79-2179-4B11-8A5A-257B1C0263AC}"


def main() -> int:
    PICK_STOP.parent.mkdir(parents=True, exist_ok=True)
    PICK_STOP.write_text("1", encoding="utf-8")
    if not RULE.is_file():
        print("No está ColorimetriaInstancia.iLogicVb")
        return 1
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from inventor_session import _active_assembly, _inventor, _name, _run_external_rule

    inv = _inventor()
    assembly = _active_assembly(inv)
    if assembly is None:
        print("Abre un ensamble (.iam) en Inventor.")
        return 1
    print(f"Prueba Colorimetría en {_name(assembly)}", flush=True)
    print("En Inventor: elige la clase, clic en cada pieza, Esc para cambiar o salir.", flush=True)
    try:
        _run_external_rule(inv, assembly, str(RULE))
    except Exception as ex:
        print(
            "No pude lanzar iLogic desde aquí (Inventor ocupado u otra regla abierta).\n"
            "En Inventor: iLogic, agregar regla externa:\n"
            f"  {RULE}\n"
            f"Detalle: {ex}",
            flush=True,
        )
        return 1
    print("Regla cerrada.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
