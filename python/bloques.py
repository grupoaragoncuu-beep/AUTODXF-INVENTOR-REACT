"""Procesamiento por bloques: Almacén → Corte → Doblado → Maquinados →
Accesorios Sueltos → Assy Loose Accesories → Assy Tanks.

Cada bloque tiene su iProperty Sí/No en la pieza (o el .iam). Clasificación guarda
la lista de bloques de la pieza, en orden y separada por "; ", porque Corte, Doblado
y Armado la leen. Almacén, Corte y Doblado no se combinan en una misma pieza.
Mientras se avanza solo se colorea un bloque; al final, todo el ensamble.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from colorimetria import BLOCKS, EXCLUSIVE, block_by_id, load_colorimetria

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "config" / "bloques_estado.json"
USER_PROPS = "Inventor User Defined Properties"
CLASS_PROP = "Clasificación"
# En el .iam principal: bloques confirmados, para que el avance viaje con el archivo.
FLOW_PROP = "AutoDXF Bloques"
DONE, EMPTY = "hecho", "no_aplica"

_SPLIT = re.compile(r"[;|]")
_TRUE = {"true", "sí", "si", "yes", "1", "-1", "verdadero"}
_PART, _ASSEMBLY = 12290, 12291
_OVERRIDE = 100609
_ALIASES = {"almacen": "almacen", "maquinado": "maquinados", "assy loose accessories": "assy_loose"}


def split_classes(text) -> list[str]:
    return [token.strip() for token in _SPLIT.split(str(text or "")) if token.strip()]


def raw_classification(doc) -> str:
    props = _user_props(doc)
    value = _prop_value(props, CLASS_PROP) if props is not None else None
    return "" if value is None else str(value).strip()


def doc_class_names(doc) -> set[str]:
    """Clasificaciones de la pieza en minúsculas (incluye valores antiguos como Maquinados Tank)."""
    return {token.casefold() for token in split_classes(raw_classification(doc))}


def doc_block_ids(doc) -> list[str]:
    flags = _flags(doc)
    if flags is None:
        legacy = set(_legacy_ids(doc))
        return [block["id"] for block in BLOCKS if block["id"] in legacy]
    return [block["id"] for block in BLOCKS if flags[block["id"]]]


def set_block(doc, block_id: str, on: bool) -> bool:
    block = block_by_id(block_id)
    props = _user_props(doc, create=True)
    if block is None or props is None:
        return False
    if _flags(doc) is None:
        for legacy in _legacy_ids(doc):
            _write_prop(props, block_by_id(legacy)["prop"], True)
    if not _write_prop(props, block["prop"], bool(on)):
        return False
    _rebuild_classification(doc, props)
    return True


def _user_props(doc, create: bool = False):
    try:
        return doc.PropertySets.Item(USER_PROPS)
    except Exception:
        if not create:
            return None
    try:
        return doc.PropertySets.Add(USER_PROPS)
    except Exception:
        return None


def _prop_value(props, name: str):
    try:
        return props.Item(name).Value
    except Exception:
        return None


def _write_prop(props, name: str, value) -> bool:
    try:
        props.Item(name).Value = value
        return True
    except Exception:
        pass
    try:
        props.Add(value, name)
        return True
    except Exception:
        return False


def _is_true(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() in _TRUE


def _flags(doc) -> dict[str, bool] | None:
    """None si la pieza todavía no tiene ningún iProperty de bloque (modelo anterior)."""
    props = _user_props(doc)
    if props is None:
        return None
    found: dict[str, bool] = {}
    for block in BLOCKS:
        value = _prop_value(props, block["prop"])
        if value is not None:
            found[block["id"]] = _is_true(value)
    if not found:
        return None
    return {block["id"]: found.get(block["id"], False) for block in BLOCKS}


def _known_names() -> dict[str, str]:
    names = {block["name"].casefold(): block["id"] for block in BLOCKS}
    names.update(_ALIASES)
    return names


def _legacy_ids(doc) -> list[str]:
    names = _known_names()
    return [names[token.casefold()] for token in split_classes(raw_classification(doc)) if token.casefold() in names]


def _rebuild_classification(doc, props) -> None:
    flags = _flags(doc) or {}
    known = _known_names()
    keep = [token for token in split_classes(raw_classification(doc)) if token.casefold() not in known]
    names = [block["name"] for block in BLOCKS if flags.get(block["id"])] + keep
    _write_prop(props, CLASS_PROP, "; ".join(names))


def scan_documents(assembly) -> dict[str, dict]:
    """Piezas y subensambles únicos del ensamble activo, con todas sus ocurrencias."""
    found: dict[str, dict] = {}

    def walk(occurrences) -> None:
        try:
            total = int(occurrences.Count)
        except Exception:
            return
        for index in range(1, total + 1):
            try:
                occ = occurrences.Item(index)
                if bool(occ.Suppressed):
                    continue
                kind = int(occ.DefinitionDocumentType)
                if kind not in (_PART, _ASSEMBLY):
                    continue
                doc = occ.Definition.Document
                path = str(doc.FullFileName or "")
            except Exception:
                continue
            if not path:
                continue
            key = _key(path)
            entry = found.get(key)
            if entry is None:
                entry = found[key] = {
                    "doc": doc,
                    "path": path,
                    "kind": "assembly" if kind == _ASSEMBLY else "part",
                    "occs": [],
                }
            entry["occs"].append(occ)
            if kind == _ASSEMBLY:
                try:
                    walk(occ.SubOccurrences)
                except Exception:
                    continue

    try:
        walk(assembly.ComponentDefinition.Occurrences)
    except Exception:
        return found
    return found


def _key(path: str) -> str:
    return str(path or "").replace("\\", "/").strip().lower()


def clear_colors(docs: dict[str, dict]) -> int:
    from inventor_session import _clear_appearance

    cleared = 0
    for entry in docs.values():
        for occ in entry["occs"]:
            try:
                if int(occ.AppearanceSourceType) != _OVERRIDE:
                    continue
            except Exception:
                continue
            if _clear_appearance(occ):
                cleared += 1
    return cleared


def paint_block(inv, assembly, docs: dict[str, dict], block_id: str) -> int:
    """Limpia todo el color del modelo y pinta solo lo marcado en este bloque."""
    from inventor_session import _class_appearance, _hex_rgb, _set_appearance

    block = block_by_id(block_id)
    if block is None:
        return 0
    clear_colors(docs)
    color = _palette().get(block["id"], {}).get("color", "")
    asset = _class_appearance(inv, assembly, block["name"], _hex_rgb(color))
    painted = 0
    for entry in docs.values():
        if entry["kind"] != block["level"]:
            continue
        if block["id"] not in doc_block_ids(entry["doc"]):
            continue
        for occ in entry["occs"]:
            if _set_appearance(occ, asset):
                painted += 1
    try:
        inv.ActiveView.Update()
    except Exception:
        pass
    return painted


def _leaf_parts(occ) -> list:
    found = []
    try:
        subs = occ.SubOccurrences
        total = int(subs.Count)
    except Exception:
        return found
    for index in range(1, total + 1):
        try:
            child = subs.Item(index)
            if bool(child.Suppressed):
                continue
            kind = int(child.DefinitionDocumentType)
        except Exception:
            continue
        if kind == _ASSEMBLY:
            found.extend(_leaf_parts(child))
        elif kind == _PART:
            found.append(child)
    return found


def paint_final(inv, assembly, docs: dict[str, dict]) -> dict[str, int]:
    """Todo el ensamble a color: cada pieza con su proceso (si no, Maquinados o Accesorios Sueltos);
    las piezas de un kit Assy sin proceso propio toman el color del kit."""
    from inventor_session import _class_appearance, _full_name, _hex_rgb, _set_appearance

    clear_colors(docs)
    palette = _palette()
    assets: dict[str, object] = {}

    def asset(block_id: str):
        if block_id not in assets:
            block = block_by_id(block_id)
            color = palette.get(block_id, {}).get("color", "")
            assets[block_id] = _class_appearance(inv, assembly, block["name"], _hex_rgb(color))
        return assets[block_id]

    counts = {block["id"]: 0 for block in BLOCKS}
    colored: set[str] = set()
    for key, entry in docs.items():
        if entry["kind"] != "part":
            continue
        ids = doc_block_ids(entry["doc"])
        chosen = next((block_id for block_id in (*EXCLUSIVE, "maquinados", "accesorios") if block_id in ids), "")
        if not chosen:
            continue
        colored.add(key)
        counts[chosen] += 1
        for occ in entry["occs"]:
            _set_appearance(occ, asset(chosen))
    for kit in ("assy_tanks", "assy_loose"):
        for entry in docs.values():
            if entry["kind"] != "assembly" or kit not in doc_block_ids(entry["doc"]):
                continue
            counts[kit] += 1
            for occ in entry["occs"]:
                for leaf in _leaf_parts(occ):
                    try:
                        leaf_key = _key(_full_name(leaf.Definition.Document))
                    except Exception:
                        continue
                    if leaf_key not in colored:
                        _set_appearance(leaf, asset(kit))
    try:
        inv.ActiveView.Update()
    except Exception:
        pass
    return counts


def _diagnostic(docs: dict[str, dict]) -> dict:
    unclassified = []
    conflicts = []
    for entry in docs.values():
        ids = [
            block_id
            for block_id in doc_block_ids(entry["doc"])
            if (block_by_id(block_id) or {}).get("level") == entry["kind"]
        ]
        row = {
            "path": entry["path"],
            "name": Path(entry["path"]).stem,
            "kind": entry["kind"],
            "qty": len(entry["occs"]),
            "legacy": raw_classification(entry["doc"]),
        }
        if not ids:
            unclassified.append(row)
        clash = [block_id for block_id in ids if block_id in EXCLUSIVE]
        if len(clash) > 1:
            conflicts.append({**row, "blocks": clash})
    unclassified.sort(key=lambda item: (item["kind"] != "part", item["name"].lower()))
    conflicts.sort(key=lambda item: item["name"].lower())
    return {"unclassified": unclassified, "conflicts": conflicts}


def _palette() -> dict[str, dict]:
    return {item["id"]: item for item in load_colorimetria().get("classes") or []}


def _load_state() -> dict:
    if not STATE_PATH.is_file():
        return {}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_state(data: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_flow(assembly) -> dict | None:
    props = _user_props(assembly)
    value = _prop_value(props, FLOW_PROP) if props is not None else None
    if value is None:
        return None
    flow = {}
    for piece in str(value).split(";"):
        block_id, _, state = piece.partition("=")
        if block_by_id(block_id.strip()) and state.strip() in {DONE, EMPTY}:
            flow[block_id.strip()] = state.strip()
    return flow


def _write_flow(assembly, saved: dict) -> None:
    text = ";".join(f"{block['id']}={saved[block['id']]}" for block in BLOCKS if block["id"] in saved)
    props = _user_props(assembly, create=bool(text))
    if props is None:
        return
    current = _prop_value(props, FLOW_PROP)
    if (current is None and not text) or str(current or "") == text:
        return
    _write_prop(props, FLOW_PROP, text)


def _block_items(docs: dict[str, dict]) -> list[dict]:
    items = []
    for entry in docs.values():
        ids = [
            block_id
            for block_id in doc_block_ids(entry["doc"])
            if (block_by_id(block_id) or {}).get("level") == entry["kind"]
        ]
        if not ids:
            continue
        items.append(
            {
                "path": entry["path"],
                "name": Path(entry["path"]).stem,
                "kind": entry["kind"],
                "qty": len(entry["occs"]),
                "blocks": ids,
            }
        )
    items.sort(key=lambda item: item["name"].lower())
    return items


def _flow(items: list[dict], saved: dict) -> tuple[list[dict], str]:
    """Un bloque solo se abre cuando todos los anteriores están confirmados."""
    palette = _palette()
    rows = []
    current = ""
    unlocked = True
    for block in BLOCKS:
        count = sum(1 for item in items if block["id"] in item["blocks"])
        state = str(saved.get(block["id"]) or "")
        done = (state == DONE and count > 0) or (state == EMPTY and count == 0)
        rows.append(
            {
                "id": block["id"],
                "name": block["name"],
                "prop": block["prop"],
                "level": block["level"],
                "color": palette.get(block["id"], {}).get("color", "#64748B"),
                "count": count,
                "state": state if done else "",
                "unlocked": unlocked,
            }
        )
        if not done and unlocked:
            current = block["id"]
            unlocked = False
    return rows, current


def _export(folder: str, job: str, items: list[dict]) -> dict:
    dest = Path(folder) if folder else None
    if dest is None or not dest.exists():
        return {"ok": False, "message": "Elige la carpeta destino antes de exportar."}
    if dest.name.lower() != "autodxf":
        dest = dest / "AutoDXF"
    if str(job or "").strip():
        dest = dest / str(job).strip()
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / "Clasificacion_Bloques.csv"
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Nombre", "Tipo", "Cantidad", *[block["name"] for block in BLOCKS], "Clasificación"])
        for item in items:
            marks = ["Sí" if block["id"] in item["blocks"] else "" for block in BLOCKS]
            names = [block["name"] for block in BLOCKS if block["id"] in item["blocks"]]
            kind = "Ensamble" if item["kind"] == "assembly" else "Pieza"
            writer.writerow([item["name"], kind, item["qty"], *marks, "; ".join(names)])
    return {"ok": True, "message": f"{len(items)} componentes clasificados en {target}"}


def run_blocks(payload: dict | None = None) -> dict:
    from inventor_session import _active_assembly, _full_name, _inventor, _name, _short

    payload = payload if isinstance(payload, dict) else {}
    action = str(payload.get("action") or "status").strip().lower()
    block = block_by_id(str(payload.get("block") or ""))
    try:
        inv = _inventor()
    except Exception as ex:
        return {"ok": False, "message": str(ex)}
    assembly = _active_assembly(inv)
    if assembly is None:
        return {"ok": False, "message": "Abre un ensamble (.iam) en Inventor."}
    if action not in {"status", "clear", "export", "final"} and block is None:
        return {"ok": False, "message": "Bloque desconocido."}

    assembly_key = _key(_full_name(assembly))
    state = _load_state()
    saved = state.setdefault(assembly_key, {})
    from_model = _read_flow(assembly)
    if from_model is not None:
        saved.clear()
        saved.update(from_model)
    docs = scan_documents(assembly)
    ok = True
    message = ""

    try:
        if action == "unmark":
            wanted = {_key(path) for path in payload.get("paths") or [] if path}
            removed = 0
            for key in wanted:
                entry = docs.get(key)
                if entry and set_block(entry["doc"], block["id"], False):
                    removed += 1
            saved.pop(block["id"], None)
            painted = paint_block(inv, assembly, docs, block["id"])
            message = f"{removed} quitado(s) de {block['name']}. {painted} ocurrencias en color."
        elif action == "verify":
            painted = paint_block(inv, assembly, docs, block["id"])
            message = (
                f"Verificando {block['name']}: {painted} ocurrencias en color. El resto quedó sin color."
                if painted
                else f"{block['name']} no tiene componentes marcados."
            )
        elif action == "clear":
            cleared = clear_colors(docs)
            try:
                inv.ActiveView.Update()
            except Exception:
                pass
            message = f"Colores quitados en {cleared} ocurrencias."
    except Exception as ex:
        ok = False
        message = f"Inventor no aplicó el cambio: {_short(ex)}"

    items = _block_items(docs)
    blocks, current = _flow(items, saved)
    by_id = {row["id"]: row for row in blocks}

    if block is not None and action in {"confirm", "empty", "reopen"}:
        row = by_id[block["id"]]
        if action == "reopen":
            saved.pop(block["id"], None)
            message = f"{block['name']} reabierto. Corrige y vuelve a confirmar; los bloques siguientes esperan."
        elif not row["unlocked"]:
            ok = False
            message = f"Primero confirma los bloques anteriores a {block['name']}."
        elif action == "confirm" and row["count"] == 0:
            ok = False
            message = f"{block['name']} no tiene componentes. Si no aplica, usa «Este bloque no aplica»."
        elif action == "confirm" and _mixed(items, block["id"]):
            ok = False
            shown = ", ".join(_mixed(items, block["id"])[:8])
            message = (
                f"Almacén, Corte y Doblado no se combinan. Estas piezas de {block['name']} "
                f"también están en otro de esos bloques: {shown}. Quítalas de uno."
            )
        elif action == "empty" and row["count"] > 0:
            ok = False
            message = f"{block['name']} tiene {row['count']} componente(s). Quítalos o confirma el bloque."
        else:
            saved[block["id"]] = DONE if action == "confirm" else EMPTY
            message = (
                f"{block['name']} confirmado con {row['count']} componente(s). "
                "Guarda el ensamble en Inventor para conservar los iProperties."
                if action == "confirm"
                else f"{block['name']} marcado como «no aplica»."
            )
        blocks, current = _flow(items, saved)

    if action == "export":
        result = _export(str(payload.get("folder") or ""), str(payload.get("job") or ""), items)
        ok, message = bool(result["ok"]), str(result["message"])

    diagnostic = None
    if action == "final":
        if current:
            ok = False
            message = f"Falta confirmar {(block_by_id(current) or {}).get('name', current)} antes de ver el ensamble final."
        else:
            try:
                counts = paint_final(inv, assembly, docs)
                diagnostic = _diagnostic(docs)
                parts = ", ".join(f"{row['name']} {counts[row['id']]}" for row in blocks if counts.get(row["id"]))
                pending = len(diagnostic["unclassified"])
                message = f"Ensamble final a color: {parts or 'sin componentes'}. " + (
                    f"{pending} componente(s) sin clasificación (quedan sin color)."
                    if pending
                    else "Todos los componentes tienen clasificación."
                )
            except Exception as ex:
                ok = False
                message = f"Inventor no aplicó el color final: {_short(ex)}"

    for block_id in list(saved):
        if block_id not in {row["id"] for row in blocks if row["state"]}:
            saved.pop(block_id, None)
    _write_flow(assembly, saved)
    if not saved:
        state.pop(assembly_key, None)
    _save_state(state)

    if not message:
        done = sum(1 for row in blocks if row["state"])
        message = (
            f"{_name(assembly)}: {len(items)} componente(s) con clasificación detectados en el modelo; "
            f"{done} de {len(blocks)} bloques confirmados."
        )
    return {
        "ok": ok,
        "message": message,
        "assembly": _name(assembly),
        "blocks": blocks,
        "items": items,
        "current": current,
        "complete": current == "",
        "diagnostic": diagnostic,
    }


def _mixed(items: list[dict], block_id: str) -> list[str]:
    """Piezas del bloque que también están en otro de Almacén/Corte/Doblado."""
    if block_id not in EXCLUSIVE:
        return []
    return [
        item["name"]
        for item in items
        if block_id in item["blocks"] and any(other in item["blocks"] for other in EXCLUSIVE if other != block_id)
    ]
