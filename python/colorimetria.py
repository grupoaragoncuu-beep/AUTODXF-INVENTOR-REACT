"""Paleta de Colorimetría: nombre de clasificación + color, editables."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "colorimetria.json"

# Nombres de Autodesk Biblioteca de aspecto (Colorimetria Sub Assembly + Norman).
LIBRARY_LOOKS = {
    "almacén": ["Dark Green", "Verde oscuro"],
    "almacen": ["Dark Green", "Verde oscuro"],
    "corte": ["Rojo naranja"],
    "doblado": ["Violeta"],
    "maquinado": ["Blue - Wall Paint - Glossy", "Azul - Pintura mural - Brillante"],
    "maquinados": ["Blue - Wall Paint - Glossy", "Azul - Pintura mural - Brillante"],
    "maquinados tank": ["Blue - Wall Paint - Glossy", "Azul - Pintura mural - Brillante"],
    "maq_tank": ["Blue - Wall Paint - Glossy", "Azul - Pintura mural - Brillante"],
    "maquinados accesorios sueltos": ["Cyan", "Cian", "Turquoise", "Turquesa", "Teal"],
    "maq_accesorios": ["Cyan", "Cian", "Turquoise", "Turquesa", "Teal"],
    "accesorios sueltos": ["Orange", "Naranja", "Orange - Wall Paint - Glossy", "Naranja - Pintura mural - Brillante"],
    "accesorios": ["Orange", "Naranja", "Orange - Wall Paint - Glossy", "Naranja - Pintura mural - Brillante"],
    "assy tanks": ["Pine", "Pine Green", "Verde pino"],
    "assy_tanks": ["Pine", "Pine Green", "Verde pino"],
    "assy loose accesories": ["Gold", "Amarillo oro", "Yellow", "Amarillo"],
    "assy loose accessories": ["Gold", "Amarillo oro", "Yellow", "Amarillo"],
    "assy_loose": ["Gold", "Amarillo oro", "Yellow", "Amarillo"],
}

# Procesamiento por bloques: orden fijo, un iProperty Sí/No por bloque.
# El nombre es el valor que se escribe en Clasificación y lo leen Corte/Doblado/Armado.
BLOCKS = (
    {"id": "almacen", "name": "Almacén", "prop": "AutoDXF Almacén", "level": "part"},
    {"id": "corte", "name": "Corte", "prop": "AutoDXF Corte", "level": "part"},
    {"id": "doblado", "name": "Doblado", "prop": "AutoDXF Doblado", "level": "part"},
    {"id": "maquinados", "name": "Maquinados", "prop": "AutoDXF Maquinados", "level": "part"},
    {"id": "accesorios", "name": "Accesorios Sueltos", "prop": "AutoDXF Accesorios Sueltos", "level": "part"},
    {"id": "assy_loose", "name": "Assy Loose Accesories", "prop": "AutoDXF Assy Loose", "level": "assembly"},
    {"id": "assy_tanks", "name": "Assy Tanks", "prop": "AutoDXF Assy Tanks", "level": "assembly"},
)

# Una pieza va a uno solo de estos procesos: no se combinan entre sí.
EXCLUSIVE = ("almacen", "corte", "doblado")

DEFAULT_CLASSES = [
    {"id": "almacen", "name": "Almacén", "color": "#166534", "appearances": LIBRARY_LOOKS["almacén"]},
    {"id": "corte", "name": "Corte", "color": "#EA580C", "appearances": LIBRARY_LOOKS["corte"]},
    {"id": "doblado", "name": "Doblado", "color": "#7C3AED", "appearances": LIBRARY_LOOKS["doblado"]},
    {"id": "maquinados", "name": "Maquinados", "color": "#2563EB", "appearances": LIBRARY_LOOKS["maquinados"]},
    {"id": "accesorios", "name": "Accesorios Sueltos", "color": "#F97316", "appearances": LIBRARY_LOOKS["accesorios"]},
    {
        "id": "assy_loose",
        "name": "Assy Loose Accesories",
        "color": "#A16207",
        "appearances": LIBRARY_LOOKS["assy loose accesories"],
    },
    {"id": "assy_tanks", "name": "Assy Tanks", "color": "#0F766E", "appearances": LIBRARY_LOOKS["assy tanks"]},
]


def block_by_id(block_id: str) -> dict | None:
    wanted = str(block_id or "").strip().casefold()
    for block in BLOCKS:
        if block["id"] == wanted:
            return block
    return None


def default_catalog() -> dict:
    return {"classes": [dict(item) for item in DEFAULT_CLASSES]}


def load_colorimetria() -> dict:
    if not CONFIG.is_file():
        save_colorimetria(default_catalog())
        return default_catalog()
    try:
        raw = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return default_catalog()
    return normalize_catalog(raw if isinstance(raw, dict) else {})


def save_colorimetria(payload: dict) -> dict:
    catalog = normalize_catalog(payload if isinstance(payload, dict) else {})
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "message": f"{len(catalog['classes'])} clasificaciones guardadas.", "catalog": catalog}


def normalize_catalog(payload: dict) -> dict:
    """Siempre los bloques fijos, en orden; del archivo solo se toma color y apariencias."""
    rows = payload.get("classes") if isinstance(payload.get("classes"), list) else []
    saved = {_slug(str(item.get("id") or "")): item for item in rows if isinstance(item, dict)}
    classes: list[dict] = []
    for default in DEFAULT_CLASSES:
        item = saved.get(default["id"]) or {}
        looks = item.get("appearances")
        names = [str(x).strip() for x in looks if str(x).strip()] if isinstance(looks, list) else []
        block = block_by_id(default["id"]) or {}
        classes.append(
            {
                "id": default["id"],
                "name": default["name"],
                "color": _hex(item.get("color") or default["color"]),
                "appearances": names or list(default["appearances"]),
                "prop": block.get("prop", ""),
                "level": block.get("level", "part"),
            }
        )
    return {"classes": classes}


def library_names(name: str) -> list[str]:
    key = str(name or "").strip().casefold()
    if key in LIBRARY_LOOKS:
        return list(LIBRARY_LOOKS[key])
    return list(LIBRARY_LOOKS.get(key.replace("_", " "), []))


def class_by_name(name: str, catalog: dict | None = None) -> dict | None:
    wanted = str(name or "").strip().casefold()
    if not wanted:
        return None
    cfg = catalog or load_colorimetria()
    for item in cfg.get("classes") or []:
        if str(item.get("name") or "").strip().casefold() == wanted:
            return item
        if str(item.get("id") or "").strip().casefold() == wanted:
            return item
    return None


def _slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().casefold())
    return text.strip("_")[:40]


def _hex(value) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"#?[0-9A-Fa-f]{3}", text):
        digits = text.lstrip("#")
        text = "".join(ch * 2 for ch in digits)
    if re.fullmatch(r"#?[0-9A-Fa-f]{6}", text):
        return "#" + text.lstrip("#").upper()
    return "#0891B2"
