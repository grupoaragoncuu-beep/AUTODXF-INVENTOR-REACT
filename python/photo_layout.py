"""Árbol de carpetas de fotos F / B / ISO (espejo de ui/src/photo-layout.ts)."""

from __future__ import annotations

from pathlib import Path

# Espejo de Planos/cotas_dossier_registro.py → _RAMAS_DOSSIER_JPGS (PIEZAS_ACOTADAS).
DEFAULT = {
    "rootName": "PIEZAS_ACOTADAS",
    "items": {
        "root": {
            "name": "PIEZAS_ACOTADAS",
            "children": ["corte", "doblado", "estanado_busbar", "sin"],
        },
        "corte": {"name": "Corte", "children": ["plasma", "maquinado"]},
        "plasma": {"name": "Plasma y Laser", "children": ["plasma_metal", "plasma_busbar"]},
        "plasma_metal": {"name": "Corte metal", "children": []},
        "plasma_busbar": {"name": "Corte Busbar", "children": []},
        "maquinado": {
            "name": "Maquinado",
            "children": [
                "maquinados_metal",
                "corte_busbar",
                "piezas_soldadas",
                "accesorios_sueltos",
                "inspeccion_visual",
                "accesorios_por_pieza",
            ],
        },
        "maquinados_metal": {"name": "Maquinados metal", "children": []},
        "corte_busbar": {"name": "Corte Busbar", "children": []},
        "piezas_soldadas": {"name": "Piezas Soldadas", "children": []},
        "accesorios_sueltos": {"name": "Accesorios Sueltos", "children": []},
        "inspeccion_visual": {"name": "Inspeccion Visual", "children": []},
        "accesorios_por_pieza": {"name": "Accesorios Sueltos por pieza", "children": []},
        "doblado": {"name": "Doblado", "children": ["metal", "busbar"]},
        "metal": {"name": "Metal", "children": []},
        "busbar": {"name": "Busbar", "children": []},
        "estanado_busbar": {"name": "Estañado Busbar", "children": []},
        "sin": {"name": "SIN CLASIFICACION", "children": []},
    },
    "slots": {"F": "corte_busbar", "B": "busbar", "ISO": "estanado_busbar"},
}


def _safe(name: str) -> str:
    cleaned = str(name or "").translate(str.maketrans('<>:"/\\|?*', "_________")).strip().rstrip(". ")
    return cleaned or "carpeta"


def normalize(raw) -> dict:
    if not isinstance(raw, dict):
        return {**DEFAULT, "items": {k: dict(v) for k, v in DEFAULT["items"].items()}}
    items = raw.get("items") if isinstance(raw.get("items"), dict) else {}
    if not isinstance(items.get("root"), dict):
        items = {k: dict(v) for k, v in DEFAULT["items"].items()}
    slots = raw.get("slots") if isinstance(raw.get("slots"), dict) else DEFAULT["slots"]
    root_name = str(raw.get("rootName") or items["root"].get("name") or "PIEZAS_ACOTADAS").strip() or "PIEZAS_ACOTADAS"
    items = {**items, "root": {**items["root"], "name": root_name, "children": list(items["root"].get("children") or [])}}
    return {
        "rootName": root_name,
        "items": items,
        "slots": {
            "F": str(slots.get("F") or "corte_busbar"),
            "B": str(slots.get("B") or "busbar"),
            "ISO": str(slots.get("ISO") or "estanado_busbar"),
        },
    }


def _parents(items: dict) -> dict[str, str]:
    parent: dict[str, str] = {}
    for folder_id, node in items.items():
        if not isinstance(node, dict):
            continue
        for child in node.get("children") or []:
            parent[str(child)] = str(folder_id)
    return parent


def folder_rel(layout: dict, folder_id: str) -> Path:
    layout = normalize(layout)
    items = layout["items"]
    parent = _parents(items)
    parts: list[str] = []
    cur = str(folder_id or "root")
    if cur not in items:
        cur = "root"
    while cur and cur != "root":
        node = items.get(cur) or {}
        parts.insert(0, _safe(node.get("name") or cur))
        cur = parent.get(cur, "")
    return Path(_safe(layout["rootName"]), *parts)


def ensure_tree(dest_root: Path, raw) -> Path:
    layout = normalize(raw)
    items = layout["items"]

    def walk(folder_id: str, base: Path) -> None:
        node = items.get(folder_id) if isinstance(items.get(folder_id), dict) else {}
        name = _safe(node.get("name") or (layout["rootName"] if folder_id == "root" else folder_id))
        folder = base / name
        folder.mkdir(parents=True, exist_ok=True)
        for child in node.get("children") or []:
            walk(str(child), folder)

    walk("root", dest_root)
    return dest_root / _safe(layout["rootName"])


def slot_dir(dest_root: Path, raw, kind: str) -> Path:
    layout = normalize(raw)
    folder_id = str((layout.get("slots") or {}).get(kind) or "root")
    return folder_dir(dest_root, layout, folder_id)


def folder_dir(dest_root: Path, raw, folder_id: str) -> Path:
    layout = normalize(raw)
    ident = str(folder_id or "root")
    if ident not in layout["items"]:
        ident = "root"
    path = dest_root / folder_rel(layout, ident)
    path.mkdir(parents=True, exist_ok=True)
    return path
