"""Reglas de chapa antes del DXF.

Lanza InventorGenerativo sobre el ensamble abierto: mide el espesor, crea la
regla local sin usar el grosor de la regla y deja el flat pattern.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "sheet-rules.json"
_EMPAQUETADO = ROOT / "tools" / "InventorGenerativo" / "InventorGenerativo.exe"
CREATE_NO_WINDOW = 0x08000000

_BLANK = {
    "unfold": "deduction",
    "bendDeduction": "0 in",
    "kFactor": "0.44",
    "bendRadius": "Thickness",
    "bendReliefShape": "round",
    "bendReliefWidth": "Thickness",
    "bendReliefDepth": "Thickness / 2",
    "minimumRemnant": "Thickness * 2",
    "cornerReliefShape": "round",
    "cornerReliefSize": "Thickness",
    "gapSize": "Thickness",
    "bendTransition": "none",
    "bendTransitionArcRadius": "Thickness",
    "threeBendCornerReliefShape": "intersection",
    "threeBendCornerReliefSize": "Thickness",
}


def default_catalog() -> dict:
    def rule(name: str, low: float, high: float) -> dict:
        return {"id": name.lower().replace(" ", "-"), "name": name, "min": low, "max": high, **_BLANK}

    return {
        "unit": "in",
        "rules": [
            rule("Cal 0.125", 0.110, 0.150),
            rule("Cal 0.1875", 0.160, 0.210),
            rule("Cal 0.25", 0.220, 0.280),
            rule("Cal 0.375", 0.340, 0.410),
            rule("Cal 0.50", 0.460, 0.540),
        ],
    }


def load_rule_catalog() -> dict:
    if not CONFIG.is_file():
        save_rule_catalog(default_catalog())
    try:
        raw = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = default_catalog()
    try:
        return normalize_catalog(raw)
    except ValueError:
        return default_catalog()


def save_rule_catalog(payload: dict) -> dict:
    try:
        catalog = normalize_catalog(payload)
    except ValueError as error:
        return {"ok": False, "message": str(error), "catalog": load_rule_catalog()}
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "message": f"{len(catalog['rules'])} rangos guardados.", "catalog": catalog}


def normalize_catalog(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("El catálogo de reglas no es válido.")
    incoming = payload.get("rules")
    if not isinstance(incoming, list):
        raise ValueError("Falta la lista de rangos.")
    rules = []
    for index, raw in enumerate(incoming, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"El rango {index} no es válido.")
        name = str(raw.get("name") or "").strip()
        if not name:
            raise ValueError(f"El rango {index} no tiene nombre.")
        try:
            low = float(raw.get("min"))
            high = float(raw.get("max"))
        except (TypeError, ValueError):
            raise ValueError(f"{name}: el espesor mínimo y máximo deben ser números.") from None
        if low >= high:
            raise ValueError(f"{name}: el mínimo debe ser menor que el máximo.")
        rule = {
            "id": str(raw.get("id") or name).strip(),
            "name": name,
            "min": low,
            "max": high,
        }
        for key, fallback in _BLANK.items():
            value = raw.get(key, fallback)
            rule[key] = fallback if value is None else str(value).strip()
        rule["unfold"] = "deduction"
        rules.append(rule)
    rules.sort(key=lambda item: (item["min"], item["max"]))
    return {"unit": "in", "rules": rules}


def generativo_exe() -> Path | None:
    """El paquete lleva el exe. En desarrollo también vale la compilación local."""
    candidatos: list[Path] = []
    override = os.environ.get("AUTODXF_GENERATIVO", "").strip().strip('"')
    if override:
        candidatos.append(Path(override))
    candidatos.append(_EMPAQUETADO)
    proyecto = ROOT.parent / "BENDING MACHINE BUSBAR" / "SHEET METAL" / "InventorGenerativo" / "bin"
    for config in ("Release", "Debug"):
        candidatos.append(proyecto / config / "net10.0-windows" / "InventorGenerativo.exe")
    vistos: set[str] = set()
    for ruta in candidatos:
        clave = str(ruta).lower()
        if clave in vistos:
            continue
        vistos.add(clave)
        if ruta.is_file():
            return ruta
    return None


def run_sheet_rules() -> dict:
    generativo = generativo_exe()
    if generativo is None:
        return _result(
            False,
            "Falta el programa de chapa en esta instalación. "
            f"InventorGenerativo.exe debe ir en {_EMPAQUETADO}. "
            "Publica una versión nueva del Módulo e instálala en esta computadora.",
            "",
        )

    try:
        load_rule_catalog()
        completed = subprocess.run(
            [str(generativo), str(CONFIG)],
            capture_output=True,
            timeout=1800,
            creationflags=CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired as error:
        text = _decode(error.stdout) + _decode(error.stderr)
        return _result(False, "Las reglas de chapa superaron 30 minutos.", text)
    except OSError as error:
        return _result(False, f"No se pudo iniciar InventorGenerativo: {error}", "")

    text = _decode(completed.stdout)
    if completed.stderr:
        error_text = _decode(completed.stderr).strip()
        if error_text:
            text = f"{text}\n{error_text}".strip()
    return _result(completed.returncode == 0, "", text, completed.returncode)


def _result(ok: bool, message: str, log: str, code: int = 1) -> dict:
    ready: list[str] = []
    missing: list[str] = []
    for line in log.splitlines():
        stripped = line.strip()
        if stripped.startswith("OK "):
            ready.append(stripped[3:].strip())
        elif stripped.startswith("FALTA "):
            missing.append(stripped[6:].strip())

    if not message:
        if code == 0:
            message = f"Reglas listas. Flat en {len(ready)} piezas."
        elif missing:
            names = ", ".join(missing[:8])
            extra = f" y {len(missing) - 8} más" if len(missing) > 8 else ""
            message = f"Con flat: {len(ready)}. Sin flat: {len(missing)}. {names}{extra}"
        else:
            tail = next((line.strip() for line in reversed(log.splitlines()) if line.strip()), "")
            message = tail or "InventorGenerativo no terminó."

    return {
        "ok": ok and not missing,
        "withFlat": len(ready),
        "missing": missing,
        "message": message,
        "log": log[-6000:],
    }


def _decode(raw) -> str:
    if not raw:
        return ""
    if isinstance(raw, str):
        return raw
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")
