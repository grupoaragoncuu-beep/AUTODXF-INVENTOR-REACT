"""Sesión de Inventor abierta. La exportación DXF sigue en la regla iLogic."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULE_PATH = ROOT / "AutoDXF 2.0.iLogicVb"
PICK_RULE = ROOT / "SelectorComponentes.iLogicVb"
PICK_JOB = ROOT / "config" / "pick_job.txt"
PICK_STOP = ROOT / "config" / "pick_stop.flag"
PICK_STATUS = ROOT / "config" / "pick_status.json"
RESULT_PATH = ROOT / "autodxf_result.json"
JOB_NAME = "autodxf_job.json"

ASSEMBLY_DOC = 12291
DB_LENGTH = 11268
INCH_LENGTH = 11272
SHEET_METAL = "{9C464203-9BAE-11D3-8BAD-0060B0CE6BB4}"
ILOGIC_ADDIN = "{3BDD8D79-2179-4B11-8A5A-257B1C0263AC}"


def inventor_snapshot() -> dict:
    try:
        inv = _inventor()
    except Exception as ex:
        return _empty(str(ex))

    version = ""
    try:
        version = str(inv.SoftwareVersion.DisplayName)
    except Exception:
        version = "Inventor"

    import time

    assembly = None
    for _attempt in range(5):
        assembly = _active_assembly(inv)
        if assembly is not None:
            break
        time.sleep(0.5)
    if assembly is None:
        seen = _active_document_label(inv)
        detail = f" Documento activo: {seen}." if seen else ""
        return {
            "inventorConnected": True,
            "inventorVersion": version,
            "assemblyName": "",
            "assemblyPath": "",
            "parts": [],
            "message": "Abre un ensamble (.iam) en Inventor." + detail,
        }

    name = _name(assembly)
    path = _full_name(assembly)
    return {
        "inventorConnected": True,
        "inventorVersion": version,
        "assemblyName": name,
        "assemblyPath": path,
        "parts": [],
        "message": f"Conectado a {name}.",
    }


def inventor_parts() -> dict:
    """Lista de chapa. Va aparte del snapshot para no congelar la barra."""
    try:
        inv = _inventor()
    except Exception as ex:
        return {**_empty(str(ex)), "ok": False}

    version = ""
    try:
        version = str(inv.SoftwareVersion.DisplayName)
    except Exception:
        version = "Inventor"
    assembly = _active_assembly(inv)
    if assembly is None:
        return {
            "ok": False,
            "inventorConnected": True,
            "inventorVersion": version,
            "assemblyName": "",
            "assemblyPath": "",
            "parts": [],
            "message": "Abre un ensamble (.iam) en Inventor.",
        }
    name = _name(assembly)
    path = _full_name(assembly)
    try:
        parts = _sheet_metal_rows(assembly)
    except Exception:
        try:
            parts = _sheet_metal_from_leaves(assembly)
        except Exception as ex:
            return {
                "ok": False,
                "inventorConnected": True,
                "inventorVersion": version,
                "assemblyName": name,
                "assemblyPath": path,
                "parts": [],
                "message": f"No se pudo leer la chapa: {_short(ex)}",
            }
    return {
        "ok": True,
        "inventorConnected": True,
        "inventorVersion": version,
        "assemblyName": name,
        "assemblyPath": path,
        "parts": parts,
        "message": f"{len(parts)} piezas de chapa en {name}.",
    }


def scan_shapes() -> dict:
    from morphology import scan_assembly, stock_catalog

    try:
        inv = _inventor()
    except Exception as ex:
        return {"ok": False, "message": str(ex), "rows": [], "stock": stock_catalog()}

    import time

    assembly = None
    for _attempt in range(5):
        assembly = _active_assembly(inv)
        if assembly is not None:
            break
        time.sleep(0.5)
    if assembly is None:
        seen = _active_document_label(inv)
        detail = f" Documento activo: {seen}." if seen else ""
        return {
            "ok": False,
            "message": "Abre un ensamble (.iam) en Inventor." + detail,
            "rows": [],
            "stock": stock_catalog(),
        }
    try:
        rows = scan_assembly(inv, assembly)
    except Exception as ex:
        return {"ok": False, "message": f"No se pudo leer la morfología: {_short(ex)}", "rows": [], "stock": stock_catalog()}
    lengths = sum(1 for row in rows if row.get("included"))
    accessories = sum(1 for row in rows if row.get("accessory"))
    return {
        "ok": True,
        "message": f"{lengths} largos y {accessories} accesorios sueltos detectados en {_name(assembly)}.",
        "assemblyName": _name(assembly),
        "rows": rows,
        "stock": stock_catalog(),
    }


def run_component_pick(mode: str, extra: dict | None = None) -> dict:
    """Bloquea hasta que AutoDXF escriba pick_stop.flag. El clic ocurre dentro de Inventor."""
    from morphology import classify_picked, stock_catalog
    extra = extra if isinstance(extra, dict) else {}

    if not PICK_RULE.is_file():
        return {"ok": False, "message": "No está SelectorComponentes.iLogicVb.", "rows": [], "stock": stock_catalog()}
    try:
        inv = _inventor()
    except Exception as ex:
        return {"ok": False, "message": str(ex), "rows": [], "stock": stock_catalog()}
    assembly = _active_assembly(inv)
    if assembly is None:
        return {"ok": False, "message": "Abre un ensamble (.iam) en Inventor.", "rows": [], "stock": stock_catalog()}

    raw_mode = str(mode or "").strip().lower()
    kind = raw_mode if raw_mode in {"accessories", "roles", "lengths"} else "lengths"
    class_name = str(extra.get("className") or extra.get("classification") or "").strip()
    color = str(extra.get("color") or "").strip()
    block_id = str(extra.get("block") or "").strip() if kind == "accessories" else ""
    _write_pick_job(assembly, kind, class_name, color, block_id, smart=extra.get("smart", True) is not False)
    try:
        _run_external_rule(inv, assembly, str(PICK_RULE))
    except Exception as ex:
        return {"ok": False, "message": f"El selector no arrancó: {_short(ex)}", "rows": [], "stock": stock_catalog()}

    paths, lengths, classes = _read_pick_paths()
    if block_id:
        return {
            "ok": True,
            "message": f"Selección terminada. {len(paths)} componente(s) marcados en {class_name}.",
            "rows": [],
            "paths": paths,
            "stock": [],
        }
    if kind == "roles":
        rows = []
        for path in paths:
            key = str(path).replace("\\", "/").lower()
            rows.append({"path": path, "cara": classes.get(key, class_name)})
        removed = [str(p) for p in (read_pick_status().get("removed") or []) if p]
        for path in removed:
            rows.append({"path": path, "cara": class_name, "removed": True})
        return {
            "ok": True,
            "message": f"Selector de muros: {len(paths)} pieza(s), {len(removed)} quitada(s).",
            "rows": rows,
            "paths": paths,
            "stock": stock_catalog(),
        }
    try:
        rows = classify_picked(inv, assembly, paths, kind, lengths, class_name, classes)
    except Exception as ex:
        return {"ok": False, "message": f"No se pudo clasificar la selección: {_short(ex)}", "rows": [], "stock": stock_catalog()}
    colored = {"ok": True, "painted": 0, "message": ""}
    if paths and kind != "accessories":
        colored = paint_lengths(
            paths,
            [],
            "lengths",
            class_name=class_name,
            color=color,
        )
    label = "clasificados" if kind == "accessories" else "largos"
    message = f"Selección terminada. {len(rows)} {label}."
    if paths:
        painted = int(colored.get("painted") or 0)
        if painted:
            message += " " + str(colored.get("message") or "")
        elif not colored.get("ok"):
            message += " " + str(colored.get("message") or "No pude aplicar el marcado.")
        elif kind != "accessories":
            message += " No pude aplicar el marcado."
        if kind != "accessories":
            missing = [str(row.get("name") or "") for row in rows if not float(row.get("lengthIn") or 0)]
            if missing:
                message += " Sin largo: " + ", ".join(missing[:8]) + "."
    return {
        "ok": True,
        "message": message,
        "rows": rows,
        "stock": stock_catalog(),
        "paths": paths,
    }


def _write_pick_job(
    assembly, mode: str, class_name: str = "", color: str = "", block_id: str = "", smart: bool = True
) -> None:
    from colorimetria import BLOCKS, EXCLUSIVE, block_by_id

    PICK_JOB.parent.mkdir(parents=True, exist_ok=True)
    rgb = _hex_rgb(color)
    block = block_by_id(block_id)
    loose = block_by_id("accesorios")
    block_lines = (
        (
            f"blockProp={block['prop']}",
            f"looseProp={loose['prop'] if loose else ''}",
            "blocks=" + "|".join(f"{item['prop']}:{item['name']}" for item in BLOCKS),
            "exclusive=" + "|".join(block_by_id(item)["prop"] for item in EXCLUSIVE),
        )
        if block
        else ()
    )
    looks = ""
    try:
        from colorimetria import class_by_name, library_names

        hit = class_by_name(class_name)
        names = []
        if hit and isinstance(hit.get("appearances"), list):
            names = [str(x) for x in hit["appearances"] if x]
        if not names:
            names = library_names(class_name)
        looks = "|".join(names)
    except Exception:
        looks = ""
    body = "\n".join(
        (
            f"mode={mode}",
            f"stop={PICK_STOP}",
            f"status={PICK_STATUS}",
            f"className={class_name}",
            f"color={color}",
            f"colorR={rgb[0]}",
            f"colorG={rgb[1]}",
            f"colorB={rgb[2]}",
            f"appearances={looks}",
            f"smart={1 if smart else 0}",
            *block_lines,
            "",
        )
    )
    PICK_JOB.write_text(body, encoding="utf-8")
    try:
        folder = Path(_full_name(assembly)).parent
        if folder.is_dir():
            (folder / "pick_job.txt").write_text(body, encoding="utf-8")
    except Exception:
        pass


def update_pick_class(class_name: str, color: str = "", smart: bool | None = None) -> dict:
    """Cambia la clasificación del selector activo sin reiniciarlo."""
    if not PICK_JOB.is_file():
        return {"ok": False, "message": "No hay selector activo."}
    mode = "accessories"
    saved_smart = True
    try:
        for line in PICK_JOB.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            key = key.strip().lower()
            if key == "mode" and value.strip():
                mode = value.strip()
            if key == "smart":
                saved_smart = value.strip() != "0"
    except OSError:
        return {"ok": False, "message": "No pude leer el selector."}
    _write_pick_job(
        None,
        mode,
        str(class_name or "").strip(),
        str(color or "").strip(),
        smart=saved_smart if smart is None else bool(smart),
    )
    return {"ok": True, "message": f"Clasificación activa: {class_name}."}


def _read_pick_paths() -> tuple[list[str], dict[str, float], dict[str, str]]:
    if not PICK_STATUS.is_file():
        return [], {}, {}
    try:
        data = json.loads(PICK_STATUS.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return [], {}, {}
    paths = data.get("paths") if isinstance(data, dict) else None
    lengths = data.get("lengths") if isinstance(data, dict) else None
    classes = data.get("classes") if isinstance(data, dict) else None
    if not isinstance(paths, list):
        return [], {}, {}
    clean = [str(path) for path in paths if path]
    by_path: dict[str, float] = {}
    if isinstance(lengths, list):
        for path, value in zip(clean, lengths):
            try:
                by_path[_path_key(path)] = float(value)
            except (TypeError, ValueError):
                continue
    by_class: dict[str, str] = {}
    if isinstance(classes, list):
        for path, value in zip(clean, classes):
            text = str(value or "").strip()
            if text:
                by_class[str(path).replace("\\", "/").lower()] = text
    return clean, by_path, by_class


def read_pick_status() -> dict:
    if not PICK_STATUS.is_file():
        return {"picking": False, "count": 0, "paths": [], "names": []}
    try:
        data = json.loads(PICK_STATUS.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {"picking": False, "count": 0, "paths": [], "names": []}
    if not isinstance(data, dict):
        return {"picking": False, "count": 0, "paths": [], "names": []}
    return data


_MARKS = {
    "largo": (
        "AutoDXF Largo",
        ("Yellow", "Amarillo", "Yellow - Wall Paint - Glossy", "Amarillo - Pintura mural - Brillante"),
        (255, 220, 0),
    ),
    "accesorio": (
        "AutoDXF Accesorio",
        ("Cyan", "Cian", "Turquoise", "Turquesa"),
        (0, 176, 210),
    ),
    "ambos": (
        "AutoDXF Ambos",
        ("Orange", "Naranja", "Naranja - Pintura mural - Brillante"),
        (255, 128, 0),
    ),
}
_MARK_NAMES = {
    "ambos": {"autodxf ambos", "orange", "naranja", "naranja - pintura mural - brillante"},
    "accesorio": {"autodxf accesorio", "cyan", "cian", "turquoise", "turquesa"},
    "largo": {
        "autodxf largo",
        "yellow",
        "amarillo",
        "yellow - wall paint - glossy",
        "amarillo - pintura mural - brillante",
    },
}


def paint_lengths(
    paths: list[str],
    clear_paths: list[str] | None = None,
    role: str = "lengths",
    class_name: str = "",
    color: str = "",
) -> dict:
    """Largos: opacidad 75%. Colorimetría: color + iProperty Clasificación."""
    try:
        inv = _inventor()
    except Exception as ex:
        return {"ok": False, "message": str(ex), "painted": 0}

    assembly = _active_assembly(inv)
    if assembly is None:
        return {"ok": False, "message": "Abre un ensamble (.iam) en Inventor.", "painted": 0}

    accessory = str(role).lower() in {"accessories", "colorimetria", "colorimetría"}
    if accessory:
        paint = {_occ_token(path) for path in paths if path}
        clear = {_occ_token(path) for path in (clear_paths or []) if path} - paint
    else:
        paint = {_path_key(path) for path in paths if path}
        clear = {_path_key(path) for path in (clear_paths or []) if path} - paint
    class_name = str(class_name or "").strip()
    rgb = _hex_rgb(color)
    class_asset = None
    if accessory and paint:
        class_asset = _class_appearance(inv, assembly, class_name or "Colorimetría", rgb)
        if class_asset is None:
            return {"ok": False, "message": "No pude crear el color de clasificación en Inventor.", "painted": 0}

    painted = 0
    restored = 0
    pending = set(paint)

    def apply_occ(occ, key: str) -> None:
        nonlocal painted, restored
        if accessory:
            try:
                is_iam = int(occ.DefinitionDocumentType) == 12291
            except Exception:
                is_iam = False
            assy_class = str(class_name or "").strip().casefold().startswith("assy")
            if assy_class and not is_iam:
                return
            if is_iam and not assy_class:
                return
        if key in paint:
            if accessory:
                _clear_ancestor_overrides(occ)
                ok = _set_appearance(occ, class_asset)
            else:
                ok = _fade_occurrence(inv, assembly, occ, key, 0.75)
            if ok:
                painted += 1
                pending.discard(key)
            return
        if key not in clear:
            return
        if accessory:
            if _clear_appearance(occ):
                restored += 1
            return
        if _restore_after_fade(inv, assembly, occ):
            restored += 1

    occurrences = _all_occurrences(assembly)
    assy_class = accessory and str(class_name or "").strip().casefold().startswith("assy")
    for occ, file_key in occurrences:
        if accessory:
            key = _occ_token(file_key) if assy_class else _occ_token(_occ_key(occ))
        else:
            key = file_key
        if key in paint or key in clear:
            apply_occ(occ, key)

    if accessory and paint and _is_assy_loose(class_name):
        child_asset = _class_appearance(inv, assembly, "Accesorios Sueltos", (249, 115, 22))
        for occ, file_key in occurrences:
            if _occ_token(file_key) not in paint:
                continue
            try:
                if int(occ.DefinitionDocumentType) != 12291:
                    continue
            except Exception:
                continue
            painted += _mark_loose_children(occ, child_asset)

    if pending and not accessory:
        by_name: dict[str, list[str]] = {}
        for key in pending:
            by_name.setdefault(Path(key).name, []).append(key)
        unique = {name: hits[0] for name, hits in by_name.items() if len(hits) == 1}
        for occ, key in occurrences:
            hit = unique.get(Path(key).name)
            if hit:
                apply_occ(occ, hit)

    try:
        inv.ActiveView.Update()
    except Exception:
        pass
    if accessory:
        label = class_name or "clasificación"
        message = f"{label} en {painted} ocurrencias." if painted else "Color de la pieza restaurado."
    else:
        message = f"Opacidad 75% en {painted} ocurrencias." if painted else "Opacidad restaurada."
    return {
        "ok": True,
        "painted": painted,
        "restored": restored,
        "message": message,
    }


def _occ_key(occ) -> str:
    names: list[str] = []
    try:
        hops = occ.OccurrencePath
        for index in range(1, int(hops.Count) + 1):
            names.append(str(hops.Item(index).Name))
    except Exception:
        names = []
    if not names:
        try:
            names.append(str(occ.Name))
        except Exception:
            return ""
    return "/".join(names)


def _occ_token(value: str) -> str:
    return str(value or "").replace("\\", "/").strip().lower()


def _all_occurrences(assembly) -> list[tuple[object, str]]:
    found: list[tuple[object, str]] = []
    seen: set[str] = set()

    def add(occ) -> None:
        try:
            if bool(occ.Suppressed):
                return
            key = _path_key(_full_name(occ.Definition.Document))
            hops = _occ_key(occ)
            try:
                rb = occ.RangeBox
                pos = f"{rb.MinPoint.X:.3f},{rb.MinPoint.Y:.3f},{rb.MinPoint.Z:.3f}"
            except Exception:
                pos = ""
            token = f"{key}|{hops}|{pos}"
        except Exception:
            return
        if not key or token in seen:
            return
        seen.add(token)
        found.append((occ, key))

    def walk(occurrences) -> None:
        try:
            count = int(occurrences.Count)
        except Exception:
            return
        for index in range(1, count + 1):
            try:
                occ = occurrences.Item(index)
            except Exception:
                continue
            add(occ)
            try:
                if int(occ.DefinitionDocumentType) == 12291:
                    walk(occ.SubOccurrences)
            except Exception:
                continue

    try:
        walk(assembly.ComponentDefinition.Occurrences)
    except Exception:
        pass
    try:
        leaves = assembly.ComponentDefinition.Occurrences.AllLeafOccurrences
        count = int(leaves.Count)
    except Exception:
        return found
    for index in range(1, count + 1):
        try:
            add(leaves.Item(index))
        except Exception:
            continue
    return found


def _current_mark(occ) -> str:
    try:
        if int(occ.AppearanceSourceType) != 100609:
            return ""
        asset = occ.Appearance
        if asset is None:
            return ""
        name = str(asset.DisplayName or "").strip().lower()
    except Exception:
        return ""
    for mark, names in _MARK_NAMES.items():
        if name in names:
            return mark
    return ""


def _clear_ancestor_overrides(occ) -> None:
    try:
        parent = occ.ParentOccurrence
    except Exception:
        return
    while parent is not None:
        _clear_appearance(parent)
        try:
            parent = parent.ParentOccurrence
        except Exception:
            return


def _set_appearance(occ, asset) -> bool:
    if asset is None:
        return False
    try:
        occ.AppearanceSourceType = 100609
        occ.Appearance = asset
        return True
    except Exception:
        try:
            occ.Appearance = asset
            return True
        except Exception:
            return False


def _clear_appearance(occ) -> bool:
    try:
        occ.AppearanceSourceType = 100612
    except Exception:
        pass
    try:
        occ.Appearance = None
        return True
    except Exception:
        return False


def _hex_rgb(value: str) -> tuple[int, int, int]:
    text = str(value or "").strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6:
        return (8, 145, 178)
    try:
        return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
    except ValueError:
        return (8, 145, 178)


def _fade_name(key: str) -> str:
    token = re.sub(r"[^a-zA-Z0-9]+", "", Path(key).stem)[:18] or "pieza"
    return f"AutoDXF Fade {token}"


def _fade_occurrence(inv, assembly, occ, key: str, opacity: float) -> bool:
    source = None
    try:
        source = occ.Appearance
    except Exception:
        source = None
    if source is None:
        try:
            source = occ.Definition.Document.ActiveAppearance
        except Exception:
            source = None
    display = _fade_name(key)
    clone = _clone_appearance(inv, assembly, source, display)
    if clone is None:
        return False
    _set_asset_opacity(clone, opacity)
    return _set_appearance(occ, clone)


def _restore_after_fade(inv, assembly, occ) -> bool:
    try:
        name = str(occ.Appearance.DisplayName or "")
    except Exception:
        name = ""
    clase = ""
    try:
        clase = _classification(occ.Definition.Document)
    except Exception:
        clase = ""
    if clase:
        from colorimetria import class_by_name

        hit = class_by_name(clase)
        if hit:
            asset = _class_appearance(inv, assembly, str(hit.get("name") or clase), _hex_rgb(str(hit.get("color") or "")))
            if asset is not None and _set_appearance(occ, asset):
                return True
    if name.lower().startswith("autodxf fade"):
        return _clear_appearance(occ)
    return _clear_appearance(occ)


def _class_appearance(inv, document, name: str, rgb: tuple[int, int, int]):
    from colorimetria import class_by_name, library_names

    hit = class_by_name(name)
    names: list[str] = []
    if hit and isinstance(hit.get("appearances"), list):
        names = [str(x) for x in hit["appearances"] if x]
    if not names:
        names = library_names(name)
    asset = _aspecto_biblioteca(inv, document, names)
    if asset is not None:
        return asset
    r, g, b = (max(0, min(255, int(rgb[0]))), max(0, min(255, int(rgb[1]))), max(0, min(255, int(rgb[2]))))
    display = f"AutoDXF {name} {r}-{g}-{b}".strip()
    asset = _appearance_in_document(document, display)
    if asset is None:
        asset = _copy_library_appearance(inv, document, tuple(names) if names else ("Generic", "Genérico"))
    if asset is None:
        return None
    try:
        asset.DisplayName = display
    except Exception:
        pass
    return asset


def _aspecto_biblioteca(inv, document, names: list[str]):
    for name in names:
        found = _appearance_in_document(document, name)
        if found is not None:
            return found
    for lib_name in ("Autodesk Biblioteca de aspecto", "Autodesk Appearance Library"):
        try:
            library = inv.AssetLibraries.Item(lib_name)
        except Exception:
            continue
        for name in names:
            try:
                source = library.AppearanceAssets.Item(name)
                return source.CopyTo(document)
            except Exception:
                continue
    return None


def _clone_appearance(inv, document, source, display: str):
    existing = _appearance_in_document(document, display)
    if existing is not None:
        return existing
    clone = _copy_library_appearance(inv, document, ("Generic", "Genérico"))
    if clone is None:
        return None
    try:
        clone.DisplayName = display
    except Exception:
        pass
    if source is not None:
        _copy_appearance_color(source, clone)
    return clone


def _copy_appearance_color(source, dest) -> None:
    import win32com.client

    chosen = None
    try:
        total = int(source.Count)
    except Exception:
        return
    for index in range(1, total + 1):
        try:
            item = source.Item(index)
            tint = win32com.client.CastTo(item, "ColorAssetValue")
            color = tint.Value
            label = str(getattr(item, "Name", "") or "").lower()
        except Exception:
            continue
        if "tint" in label or "bump" in label or "self_illum" in label:
            continue
        chosen = color
        if "diffuse" in label or label in {"metal_color", "generic_color"}:
            break
    if chosen is None:
        return
    for key in ("generic_diffuse", "Generic_Diffuse"):
        try:
            slot = win32com.client.CastTo(dest.Item(key), "ColorAssetValue")
            slot.Value = chosen
            return
        except Exception:
            continue


def _tint_appearance(inv, asset, rgb: tuple[int, int, int]) -> None:
    import win32com.client

    r, g, b = (max(0, min(255, int(rgb[0]))), max(0, min(255, int(rgb[1]))), max(0, min(255, int(rgb[2]))))
    shade = inv.TransientObjects.CreateColor(r, g, b)
    try:
        toggle = win32com.client.CastTo(asset.Item("common_Tint_toggle"), "BooleanAssetValue")
        toggle.Value = True
    except Exception:
        pass
    try:
        n = int(asset.Count)
    except Exception:
        n = 0
    for index in range(1, n + 1):
        try:
            item = asset.Item(index)
            label = str(getattr(item, "Name", "") or "").lower()
        except Exception:
            continue
        if "colorspace" in label or "bump" in label or "image" in label:
            continue
        if "tint" not in label and "diff" not in label and "color" not in label:
            continue
        try:
            slot = win32com.client.CastTo(item, "ColorAssetValue")
            slot.Value = shade
        except Exception:
            continue


def _set_asset_opacity(asset, opacity: float) -> bool:
    if asset is None:
        return False
    import win32com.client

    opacity = max(0.05, min(1.0, float(opacity)))
    try:
        slot = win32com.client.CastTo(asset.Item("generic_transparency"), "FloatAssetValue")
        slot.Value = 1.0 - opacity
        return True
    except Exception:
        return False


def _is_assy_loose(name: str) -> bool:
    return "assy loose" in str(name or "").casefold()


def _mark_loose_children(kit_occ, asset) -> int:
    from bloques import set_block

    count = 0
    seen: set[str] = set()

    def walk(occurrences) -> None:
        nonlocal count
        try:
            total = int(occurrences.Count)
        except Exception:
            return
        for index in range(1, total + 1):
            try:
                child = occurrences.Item(index)
                if bool(child.Suppressed):
                    continue
                kind = int(child.DefinitionDocumentType)
            except Exception:
                continue
            if kind == 12291:
                try:
                    walk(child.SubOccurrences)
                except Exception:
                    continue
                continue
            if kind != 12290:
                continue
            try:
                doc = child.Definition.Document
                key = str(doc.FullFileName or "").replace("\\", "/").lower()
            except Exception:
                continue
            if key and key not in seen:
                seen.add(key)
                set_block(doc, "accesorios", True)
                count += 1
            if asset is not None:
                _set_appearance(child, asset)

    try:
        walk(kit_occ.SubOccurrences)
    except Exception:
        pass
    return count


def _mark_appearance(inv, document, mark: str):
    display, candidates, color = _MARKS[mark]
    existing = _appearance_in_document(document, display)
    if existing is not None:
        return existing
    asset = _copy_library_appearance(inv, document, candidates) or _copy_library_appearance(
        inv, document, ("Generic", "Genérico")
    )
    if asset is None:
        return None
    try:
        asset.DisplayName = display
    except Exception:
        pass
    try:
        tint = asset.Item("generic_diffuse")
        tint.Value = inv.TransientObjects.CreateColor(int(color[0]), int(color[1]), int(color[2]))
    except Exception:
        pass
    return asset


def _copy_library_appearance(inv, document, names: tuple[str, ...]):
    try:
        libraries = inv.AssetLibraries
        total = int(libraries.Count)
    except Exception:
        return None
    for name in names:
        for index in range(1, total + 1):
            try:
                source = libraries.Item(index).AppearanceAssets.Item(name)
                return source.CopyTo(document)
            except Exception:
                continue
    return None


def _appearance_in_document(document, name: str):
    try:
        assets = document.AppearanceAssets
        total = int(assets.Count)
    except Exception:
        return None
    for index in range(1, total + 1):
        try:
            asset = assets.Item(index)
            display = str(asset.DisplayName or "")
            internal = str(asset.Name or "")
        except Exception:
            continue
        if display.lower() == name.lower() or internal.lower() == name.lower():
            return asset
    return None


def _path_key(path: str) -> str:
    return str(path or "").replace("\\", "/").lower()


def export_dxf(
    export_root: str,
    set_a_side: bool,
    write_csv: bool,
    close_opened: bool,
    use_part_plan: bool = False,
    parts: list | None = None,
    board: str = "B1",
    job_name: str = "",
) -> dict:
    if not export_root.strip():
        return {"ok": False, "exported": 0, "csvPath": "", "message": "Elige la carpeta destino."}
    if not RULE_PATH.exists():
        return {"ok": False, "exported": 0, "csvPath": "", "message": f"No está la regla {RULE_PATH.name}."}

    try:
        inv = _inventor()
    except Exception as ex:
        return {"ok": False, "exported": 0, "csvPath": "", "message": str(ex)}

    assembly = _active_assembly(inv)
    if assembly is None:
        return {"ok": False, "exported": 0, "csvPath": "", "message": "No hay un ensamble activo."}

    from job_id import resolve_job

    asm_dir = Path(_full_name(assembly)).parent
    job = {
        "exportRoot": export_root,
        "resultPath": str(RESULT_PATH),
        "setASide": bool(set_a_side),
        "writeCsv": bool(write_csv),
        "closeOpened": bool(close_opened),
        "board": _board_code(board),
        "usePartPlan": bool(use_part_plan),
        "partPlan": _part_plan(parts or []),
        "jobName": resolve_job(job_name, _name(assembly), _full_name(assembly)),
    }
    if RESULT_PATH.exists():
        RESULT_PATH.unlink()
    for folder in {ROOT, asm_dir}:
        _write_job(folder / JOB_NAME, job)

    try:
        _run_external_rule(inv, assembly, str(RULE_PATH))
    except Exception as ex:
        return {
            "ok": False,
            "exported": 0,
            "csvPath": "",
            "message": f"iLogic no terminó la exportación: {_short(ex)}",
        }

    if not RESULT_PATH.exists():
        return {
            "ok": False,
            "exported": 0,
            "csvPath": "",
            "message": "La regla terminó sin escribir autodxf_result.json.",
        }
    try:
        return json.loads(RESULT_PATH.read_text(encoding="utf-8-sig"))
    except Exception as ex:
        return {"ok": False, "exported": 0, "csvPath": "", "message": f"Resultado ilegible: {_short(ex)}"}


def _inventor():
    import time

    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    last: Exception | None = None
    for attempt in range(3):
        try:
            unknown = pythoncom.GetActiveObject("Inventor.Application")
            dispatch = unknown.QueryInterface(pythoncom.IID_IDispatch)
            return win32com.client.dynamic.Dispatch(dispatch)
        except Exception as ex:
            last = ex
            if attempt < 2:
                time.sleep(0.35)
    raise RuntimeError(f"No se pudo conectar con Inventor: {_connect_message(last)}") from last


def _inventor_process_running() -> bool:
    import subprocess

    try:
        completed = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Inventor.exe", "/NH"],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=0x08000000,
        )
    except Exception:
        return False
    return "Inventor.exe" in (completed.stdout or "")


def _connect_message(ex: Exception | None) -> str:
    text = _short(ex) if ex else "sin detalle"
    if "-2147221021" in text or "800401E3" in text.upper():
        return (
            "Inventor está abierto, pero esta ventana no tiene permiso para verlo. "
            "Ciérrala y ábrela con doble clic, sin 'Ejecutar como administrador'."
        )
    return text


def _active_assembly(inv):
    """El ensamble de la ventana activa, no un subensamble cargado de fondo."""
    for getter in (_view_document, _raw_active_document):
        assembly = _as_assembly(_call(getter, inv))
        if assembly is not None and _full_name(assembly):
            return assembly

    active = _call(_raw_active_document, inv)
    opened = _assemblies_on_screen(inv)
    if not opened:
        return None
    if len(opened) == 1:
        return opened[0]

    active_path = _full_name(active).lower()
    if active_path:
        for candidate in opened:
            if _document_references(candidate, active_path):
                return candidate
    return opened[0]


def _assemblies_on_screen(inv) -> list:
    opened = []
    try:
        documents = inv.Documents
        count = int(documents.Count)
    except Exception:
        return opened
    for index in range(1, count + 1):
        try:
            candidate = _as_assembly(documents.Item(index))
        except Exception:
            continue
        if candidate is None or not _full_name(candidate):
            continue
        try:
            if int(candidate.Views.Count) > 0:
                opened.append(candidate)
        except Exception:
            continue
    return opened


def _view_document(inv):
    view = inv.ActiveView
    return None if view is None else view.Document


def _raw_active_document(inv):
    return inv.ActiveDocument


def _call(getter, inv):
    try:
        return getter(inv)
    except Exception:
        return None


def _active_document_label(inv) -> str:
    for getter in (_view_document, _raw_active_document):
        doc = _call(getter, inv)
        name = _name(doc) if doc is not None else ""
        if name:
            return name
    return ""


def _document_references(assembly, full_path: str) -> bool:
    try:
        refs = assembly.ReferencedDocuments
        for index in range(1, int(refs.Count) + 1):
            if _full_name(refs.Item(index)).lower() == full_path:
                return True
    except Exception:
        return False
    return False


def _as_assembly(doc):
    import win32com.client

    if doc is None:
        return None
    try:
        if int(doc.DocumentType) != ASSEMBLY_DOC:
            return None
    except Exception:
        return None
    try:
        return win32com.client.CastTo(doc, "AssemblyDocument")
    except Exception:
        return doc


def _sheet_metal_rows(assembly) -> list[dict]:
    try:
        bom = assembly.ComponentDefinition.BOM
        bom.PartsOnlyViewEnabled = True
        view = bom.BOMViews.Item(bom.BOMViews.Count)
        rows = view.BOMRows
        total = int(rows.Count)
    except Exception:
        return _sheet_metal_from_leaves(assembly)
    seen: set[str] = set()
    parts: list[dict] = []
    for index in range(1, total + 1):
        row = rows.Item(index)
        try:
            definition = row.ComponentDefinitions.Item(1)
            part = definition.Document
        except Exception:
            continue
        rec = _part_row(part, _qty(row))
        if rec is None:
            continue
        key = rec["path"] or rec["name"]
        if key in seen:
            continue
        seen.add(key)
        parts.append(rec)
    parts.sort(key=lambda item: item["name"].lower())
    return parts


def _sheet_metal_from_leaves(assembly) -> list[dict]:
    grouped: dict[str, list] = {}
    try:
        leaves = assembly.ComponentDefinition.Occurrences.AllLeafOccurrences
        total = int(leaves.Count)
    except Exception:
        return []
    for index in range(1, total + 1):
        try:
            occ = leaves.Item(index)
            if bool(occ.Suppressed):
                continue
            part = occ.Definition.Document
        except Exception:
            continue
        rec = _part_row(part, 1)
        if rec is None:
            continue
        key = rec["path"] or rec["name"]
        grouped.setdefault(key, []).append(rec)
    parts = []
    for items in grouped.values():
        row = dict(items[0])
        row["qty"] = len(items)
        parts.append(row)
    parts.sort(key=lambda item: item["name"].lower())
    return parts


def _part_row(part, qty: int) -> dict | None:
    if not _is_sheet_metal(part):
        return None
    if _is_hardware(_name(part)):
        return None
    material = _material_name(part)
    copper, form, why = _copper_busbar(part)
    canonical = _canonical(material)
    if not copper and _is_generic_material(canonical):
        canonical = "A 36"
    return {
        "name": Path(_name(part)).stem,
        "material": material,
        "canonical": canonical,
        "thickness": _thickness_inches(part),
        "qty": qty,
        "flat": _has_flat(part),
        "classification": _classification(part),
        "path": _full_name(part),
        "copper": copper,
        "form": form,
        "copperWhy": why,
    }


def _run_external_rule(inv, document, rule_path: str) -> None:
    addin = inv.ApplicationAddIns.ItemById(ILOGIC_ADDIN)
    try:
        if not bool(addin.Activated):
            addin.Activate()
    except Exception:
        addin.Activate()
    automation = addin.Automation
    automation.RunExternalRule(document, rule_path)


_HARDWARE_NAME = re.compile(
    r"(?i)(?:^|[^A-Z0-9])(?:"
    r"washers?|arandelas?|nuts?|tuercas?|bolts?|screws?|tornillos?|pernos?"
    r"|hex|handles?|manijas?|asas?|jaladeras?|manerales?|hw"
    r")(?:[^A-Z0-9]|$)"
)


def _is_hardware(name: str) -> bool:
    return _HARDWARE_NAME.search(name or "") is not None


SOLERA_MAX_WIDTH_IN = 12.0
_NAME_CODES = ("GENE", "ABB", "BCK")


def _copper_busbar(part) -> tuple[bool, str, str]:
    """Cobre solo con las dos pautas: morfología de solera y nombre de busbar."""
    import win32com.client

    name = Path(_name(part)).stem
    try:
        sheet = win32com.client.CastTo(part.ComponentDefinition, "SheetMetalComponentDefinition")
        bends = int(sheet.Bends.Count)
        width, length = _blank_size(part, sheet)
    except Exception:
        return False, "", "Sin lectura de chapa"
    return decide_copper(name, _material_name(part), width, length, bends)


def decide_copper(name: str, material: str, width: float, length: float, bends: int) -> tuple[bool, str, str]:
    """Sí solo si la pieza es solera y el nombre es de busbar. Un A36 no entra."""
    blocked = _steel_grade(material)
    if blocked:
        return False, "", blocked
    solera = width > 0 and length >= width and width <= SOLERA_MAX_WIDTH_IN
    if not solera:
        return False, "", "No es solera"
    marks = _copper_name_marks(name)
    if not marks:
        return False, "", "Sin nomenclatura de cobre"
    form = "B" if bends >= 1 else "F"
    marks.append("solera doblada" if form == "B" else "solera")
    return True, form, " + ".join(marks)


def _copper_name_marks(name: str) -> list[str]:
    upper = Path(name or "").stem.upper()
    marks = [code for code in _NAME_CODES if re.search(rf"(^|[^A-Z0-9]){code}([^A-Z0-9]|$)", upper)]
    found = re.search(r"(^|[^A-Z0-9])(COBRE|COPPER|CU)([^A-Z0-9]|$)", upper)
    if found and found.group(2) not in marks:
        marks.append(found.group(2))
    return marks


def _is_generic_material(name: str) -> bool:
    import unicodedata

    text = unicodedata.normalize("NFD", name or "")
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    key = re.sub(r"[^a-z0-9]", "", text.casefold())
    return key in {"", "generic", "generico"}


def _steel_grade(material: str) -> str:
    """Grado de acero o aluminio ya asignado. Genérico no cuenta: no bloquea ni es cobre."""
    canonical = _canonical(material)
    if canonical in {"A 36", "A 36 GALV", "SSTL 304", "Aluminio"}:
        return canonical
    return ""


def _blank_size(part, sheet) -> tuple[float, float]:
    body = None
    try:
        if bool(sheet.HasFlatPattern):
            body = sheet.FlatPattern.Body
    except Exception:
        body = None
    if body is None:
        try:
            body = part.ComponentDefinition.SurfaceBodies.Item(1)
        except Exception:
            return 0.0, 0.0
    box = body.RangeBox
    dims = sorted(
        abs(_inches(part, getattr(box.MaxPoint, axis) - getattr(box.MinPoint, axis)))
        for axis in ("X", "Y", "Z")
    )
    usable = [value for value in dims if value > 0.01]
    if len(usable) < 2:
        return 0.0, 0.0
    width, length = usable[-2], usable[-1]
    return width, length


def _inches(part, value: float) -> float:
    return float(part.UnitsOfMeasure.ConvertUnits(float(value), DB_LENGTH, INCH_LENGTH))


def _is_sheet_metal(part) -> bool:
    try:
        return str(part.SubType).lower() == SHEET_METAL.lower()
    except Exception:
        return False


def _has_flat(part) -> bool:
    import win32com.client

    try:
        sheet = win32com.client.CastTo(part.ComponentDefinition, "SheetMetalComponentDefinition")
        return bool(sheet.HasFlatPattern)
    except Exception:
        return False


def _material_name(part) -> str:
    import win32com.client

    try:
        sheet = win32com.client.CastTo(part.ComponentDefinition, "SheetMetalComponentDefinition")
        return str(sheet.Material.Name).strip()
    except Exception:
        pass
    try:
        return str(part.PropertySets.Item("Design Tracking Properties").Item("Material").Value).strip()
    except Exception:
        return ""


def _classification(part) -> str:
    try:
        value = part.PropertySets.Item("Inventor User Defined Properties").Item("Clasificación").Value
        return "" if value is None else str(value).strip()
    except Exception:
        return ""


def _classes(part) -> set[str]:
    """Clasificación puede traer varios bloques ("Corte; Doblado"): conjunto en minúsculas."""
    from bloques import split_classes

    return {token.casefold() for token in split_classes(_classification(part))}


def _thickness_inches(part) -> str:
    import win32com.client

    try:
        sheet = win32com.client.CastTo(part.ComponentDefinition, "SheetMetalComponentDefinition")
        inches = _inches(part, sheet.Thickness.Value)
    except Exception:
        return ""
    text = f"{inches:.6f}".rstrip("0").rstrip(".")
    return text or "0"


def _qty(row) -> int:
    try:
        return int(round(float(row.ItemQuantity)))
    except Exception:
        return 0


def _canonical(material: str) -> str:
    from catalog import normalize_material

    return normalize_material(material) or material


def _name(doc) -> str:
    try:
        return str(doc.DisplayName)
    except Exception:
        return ""


def _full_name(doc) -> str:
    try:
        return str(doc.FullFileName or "")
    except Exception:
        return ""


def _write_job(path: Path, job: dict) -> None:
    lines = ["{"]
    items = list(job.items())
    for index, (key, value) in enumerate(items):
        comma = "," if index < len(items) - 1 else ""
        lines.append(f'  "{key}": {_json_token(value)}{comma}')
    lines.append("}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _board_code(value: str) -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip().rstrip(". ")
    if not text:
        return "B1"
    return text[:48].strip() or "B1"


def _part_plan(parts: list) -> str:
    rows: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        path = str(part.get("path") or "").replace("\\", "/").replace(";", "").replace("^", "")
        material = str(part.get("material") or "").replace(";", " ").replace("^", " ").strip()
        dxf_name = str(part.get("dxfName") or "").replace(";", "").replace("^", "").strip()
        if path and material:
            rows.append(f"{path}^{material}^{dxf_name}")
    return ";".join(rows)


def _json_token(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).replace("\\", "/").replace('"', "")
    return f'"{text}"'


def _empty(message: str) -> dict:
    return {
        "inventorConnected": False,
        "inventorVersion": "",
        "assemblyName": "",
        "assemblyPath": "",
        "parts": [],
        "message": message,
    }


def _short(ex: Exception) -> str:
    return " ".join(str(ex).split())[:300]
