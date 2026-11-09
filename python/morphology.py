"""Largos y accesorios sueltos.

La familia sale de la morfología del sólido, no del nombre. Cada corrección
del ingeniero queda en config/morfologia.json y se aplica en el siguiente modelo.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEMORY_PATH = ROOT / "config" / "morfologia.json"

FAMILIES = ("SOLERA", "PTR", "TUBO", "VARILLA", "ANGULO", "CANAL", "VIGA")
PROCESSES = ("", "CORTE", "CORTE/MAQ", 'CORTE/MAQ, CORTAR EN 3"X3"')
ACCESSORY_CLASSES = {
    "almacén",
    "almacen",
    "ensambles individuales",
    "piezas soldadas",
    "assy tanks",
    "assy loose accesories",
    "assy loose accessories",
}
_HARDWARE = (
    "washer",
    "arandela",
    "nut",
    "tuerca",
    "bolt",
    "screw",
    "tornillo",
    "perno",
    "hex",
    "handle",
    "manija",
    "jaladera",
)

_STOCK_TSV = """
PTR051	PTR 1 x 1 x 3/16	PTR	A 36	1.0	0.169
PTR045	PTR 2 x 2 x 0.339	PTR	A 36	2.0	0.339
PTR052	PTR 2	PTR	A 36	2.0	
PTR053	PTR 2 x 2 x 0.441	PTR	A 36	2.0	0.441
PTR044	PTR 3 x 3 x 0.671	PTR	A 36	3.0	0.671
PTR018	PTR 3 x 3 x 0.354	PTR	A 36	3.0	0.354
PTR013	PTR 3 x 3 x 3/16	PTR	A 36	3.0	0.201
PTR016	PTR 4 x 4 x 1/4	PTR	A 36	4.0	0.25
PTR021	PTR 4 x 4 x 5/16	PTR	A 36	4.0	0.323
PTR027	PTR 4 x 4 x 1/2	PTR	A 36	4.0	0.495
PTR034	PTR 4	PTR	A 36	4.0	
SLC024	Solera 4 x 2	SOLERA	A 1018	4.0	2.0
SLC036	Solera 1 x 1/2	SOLERA	A 36	1.0	0.5
SLC039	Solera 2 x 3/8	SOLERA	A 36	2.0	0.375
SLC047	Solera 3 x 3/4	SOLERA	A 36	3.0	0.75
SLC046	Solera 3 x 1/2	SOLERA	A 36	3.0	0.5
SLC051	Solera 4 x 1/2	SOLERA	A 36	4.0	0.5
SCO002	Solera 2 x 1/2	SOLERA	CU	2.0	0.5
SLC041	Solera 2 x 3/16	SOLERA	CU	2.0	0.188
SCO014	Solera 4 x 1/4	SOLERA	CU	4.0	0.25
SCO003	Solera 4 x 1/8	SOLERA	CU	4.0	0.125
SCO015	Solera 5 x 1/4	SOLERA	CU	5.0	0.25
SLS006	Solera 1 x 1/2	SOLERA	SSTL 304	1.0	0.5
SLS008	Solera 2 x 1/2	SOLERA	SSTL 304	2.0	0.5
SLS011	Solera 4 x 1/2	SOLERA	SSTL 304	4.0	0.5
HR174	TUBO HR174	TUBO	A 36	1.0	
HR169	TUBO HR169	TUBO	A 36	1.0	
HR220	TUBO HR220	TUBO	A 36	1.0	
HR167	TUBO HR167	TUBO	A 36	1.0	
HR212	TUBO HR212	TUBO	SSTL 304	1.0	
RED025	Varilla RED025	VARILLA	A 36	1.0	
RED027	Varilla RED027	VARILLA	A 36	1.0	
RED028	Varilla RED028	VARILLA	A 36	1.0	
RED024	Varilla RED024	VARILLA	A 36	1.0	
RED040	Varilla RED040	VARILLA	A 36	1.0	
RED035	Varilla RED035	VARILLA	SSTL 304	1.0	
VIG047	Viga IPR	VIGA IPR	A 36	1.0	
VIG044	Viga IPR	VIGA IPR	A 36	1.0	
VIG033	Viga IPR	VIGA IPR	A 36	1.0	
""".strip()


def stock_catalog() -> list[dict]:
    rows = []
    for line in _STOCK_TSV.splitlines():
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        code, desc, family, material, width = parts[:5]
        thick = parts[5].strip() if len(parts) > 5 else ""
        perfil = family.strip()
        perfil_txt = perfil if "perfil" in perfil.lower() else f"{perfil} perfil"
        rows.append(
            {
                "code": code.strip(),
                "family": family.strip().split()[0].upper(),
                "material": material.strip(),
                "width": _float(width),
                "thick": _float(thick),
                "text": f"{code.strip()} | {perfil_txt} | {material.strip()} | {desc.strip()}",
            }
        )
    return rows


def classify_mask(mask: list[bool]) -> str:
    if len(mask) != 9:
        return ""
    if is_beam(mask):
        return "VIGA"
    if is_channel(mask):
        return "CANAL"
    if is_angle(mask):
        return "ANGULO"
    return ""


def is_angle(mask: list[bool]) -> bool:
    trues = {index for index, bit in enumerate(mask) if bit}
    if not 3 <= len(trues) <= 5:
        return False
    corners = (
        (0, {0, 1, 3, 4}),
        (2, {1, 2, 4, 5}),
        (6, {3, 4, 6, 7}),
        (8, {4, 5, 7, 8}),
    )
    return any(corner in trues and trues <= region for corner, region in corners)


def is_channel(mask: list[bool]) -> bool:
    candidates = (
        (mask[0:3], mask[6:9], mask[3], mask[5]),
        (mask[6:9], mask[0:3], mask[3], mask[5]),
        (mask[0::3], mask[2::3], mask[1], mask[7]),
        (mask[2::3], mask[0::3], mask[1], mask[7]),
    )
    return any(sum(full) == 3 and sum(empty) == 0 and side_a and side_b for full, empty, side_a, side_b in candidates)


def is_beam(mask: list[bool]) -> bool:
    top, mid, bot = mask[0:3], mask[3:6], mask[6:9]
    if sum(top) >= 2 and sum(bot) >= 2 and mid[1] and not mid[0] and not mid[2]:
        return True
    left, center, right = mask[0::3], mask[1::3], mask[2::3]
    return sum(left) >= 2 and sum(right) >= 2 and center[1] and not center[0] and not center[2]


def classify_sample(sample: dict) -> str:
    length = float(sample.get("length") or 0)
    width = float(sample.get("width") or 0)
    thick = float(sample.get("thick") or 0)
    if sample.get("sheet") or length < 2 or width < 0.08:
        return ""
    if length / max(width, 0.05) < 2.5:
        return ""
    roundish = abs(width - thick) / max(width, 0.05) < 0.12
    fill = float(sample.get("fill") or 0)
    if sample.get("hollow") and roundish and int(sample.get("cylinders") or 0) >= 2:
        return "TUBO"
    if sample.get("hollow"):
        return "PTR"
    if roundish and fill >= 0.62 and int(sample.get("cylinders") or 0) >= 1:
        return "VARILLA"
    if (
        fill >= 0.8
        and width / max(thick, 0.02) >= 1.35
        and thick <= 3
        and width <= 12
    ):
        return "SOLERA"
    found = classify_mask(list(sample.get("mask") or []))
    if found:
        return found
    return ""


def signature_of(sample: dict) -> str:
    mask = sample.get("mask") or []
    bits = "".join("1" if bit else "0" for bit in mask) if len(mask) == 9 else "---------"
    width = float(sample.get("width") or 0)
    thick = float(sample.get("thick") or 0)
    roundish = 1 if width > 0 and abs(width - thick) / max(width, 0.05) < 0.12 else 0
    hollow = 1 if sample.get("hollow") else 0
    fill = round(float(sample.get("fill") or 0), 1)
    return f"{bits}|h{hollow}|r{roundish}|f{fill}"


def suggest_stock(family: str, width: float, thick: float, material: str, stock: list[dict]) -> str:
    if not family:
        return ""
    wanted = family.upper()
    material_key = (material or "").upper()
    limit = 0.4 if wanted == "SOLERA" else 0.75
    best = ""
    best_score = 10**9
    for item in stock:
        if item["family"] != wanted:
            continue
        if wanted == "SOLERA":
            score = abs(item["width"] - width) + abs((item["thick"] or thick) - thick)
        else:
            score = abs(item["width"] - max(width, thick))
        if material_key and material_key not in item["material"].upper() and item["material"].upper() not in material_key:
            score += 2
        if score < best_score:
            best_score = score
            best = item["text"]
    return best if best_score <= limit else ""


def scan_assembly(inv, assembly) -> list[dict]:
    memory = load_memory()
    stock = stock_catalog()
    grouped: dict[str, dict] = {}
    leaves = assembly.ComponentDefinition.Occurrences.AllLeafOccurrences
    for index in range(1, int(leaves.Count) + 1):
        occ = leaves.Item(index)
        try:
            if bool(occ.Suppressed):
                continue
            part = occ.Definition.Document
        except Exception:
            continue
        path = _full_name(part)
        key = path or _name(part)
        if not key:
            continue
        row = grouped.get(key)
        if row is None:
            sample = _measure(inv, part)
            row = _row_from_part(part, sample, stock, memory)
            grouped[key] = row
        row["qty"] += 1

    _collect_assemblies(assembly, grouped, memory)
    rows = list(grouped.values())
    rows.sort(key=lambda item: (not item["included"], not item["accessory"], item["name"].lower()))
    return rows


def classify_picked(
    inv,
    assembly,
    paths: list[str],
    mode: str,
    lengths: dict | None = None,
    class_name: str = "",
    classes: dict[str, str] | None = None,
) -> list[dict]:
    wanted = {str(path or "").replace("\\", "/").lower() for path in paths if path}
    if not wanted:
        return []
    lengths = lengths or {}
    picked = []
    found: set[str] = set()
    for row in scan_assembly(inv, assembly):
        key = str(row.get("path") or "").replace("\\", "/").lower()
        if key not in wanted:
            continue
        measured = float(lengths.get(key) or 0)
        if measured <= 0:
            measured = _length_from_document(inv, assembly, key)
        if measured > 0:
            row["lengthIn"] = round(measured, 3)
        if mode == "accessories":
            painted = (classes or {}).get(key) or class_name
            if _class_is_assy(painted) and str(row.get("kind") or "") != "assembly":
                continue
            if (not _class_is_assy(painted)) and str(row.get("kind") or "") == "assembly":
                continue
            row["accessory"] = True
            row["accessoryWhy"] = painted or "Seleccionado en el modelo"
            row["classification"] = painted or row.get("classification") or ""
            row["source"] = "seleccion"
        else:
            row["included"] = True
            if not row["family"]:
                row["family"] = row["suggestedFamily"] or "SOLERA"
            row["process"] = row["process"] or "CORTE"
            row["source"] = "seleccion"
        picked.append(row)
        found.add(key)
    for path in paths:
        key = str(path or "").replace("\\", "/").lower()
        if not key or key in found:
            continue
        measured = float(lengths.get(key) or 0)
        if measured <= 0:
            measured = _length_from_document(inv, assembly, key)
        painted = (classes or {}).get(key) or class_name
        kind = "assembly" if key.endswith(".iam") or _class_is_assy(painted) else "part"
        if mode == "accessories" and _class_is_assy(painted) and kind != "assembly" and not key.endswith(".iam"):
            continue
        picked.append(_picked_placeholder(path, measured, mode, painted, kind))
    picked.sort(key=lambda item: item["name"].lower())
    return picked


def _length_from_document(inv, assembly, key: str) -> float:
    try:
        leaves = assembly.ComponentDefinition.Occurrences.AllLeafOccurrences
        total = int(leaves.Count)
    except Exception:
        return 0.0
    for index in range(1, total + 1):
        try:
            occ = leaves.Item(index)
            part = occ.Definition.Document
            if str(part.FullFileName or "").replace("\\", "/").lower() != key:
                continue
            sample = _measure(inv, part)
            return float(sample.get("length") or 0)
        except Exception:
            continue
    return 0.0


def _picked_placeholder(path: str, length: float, mode: str, class_name: str = "", kind: str = "part") -> dict:
    accessory = mode == "accessories"
    label = Path(path).stem
    row_kind = "assembly" if str(kind) == "assembly" or str(path).lower().endswith(".iam") else "part"
    return {
        "name": label,
        "path": path,
        "qty": 1,
        "lengthIn": round(length, 3),
        "widthIn": 0,
        "thickIn": 0,
        "fill": 0,
        "family": "" if accessory else "SOLERA",
        "suggestedFamily": "",
        "source": "seleccion",
        "included": not accessory,
        "accessory": accessory,
        "accessoryWhy": class_name or ("Seleccionado en el modelo" if accessory else ""),
        "process": "" if accessory else "CORTE",
        "herinox": "",
        "signature": "",
        "hardware": False,
        "kind": row_kind,
        "classification": class_name if accessory else "",
    }


def remember_rows(rows: list[dict]) -> dict:
    memory = load_memory()
    paths = memory.setdefault("paths", {})
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        path = str(raw.get("path") or "").strip()
        if not path:
            continue
        family = str(raw.get("family") or "").strip().upper()
        if family not in FAMILIES:
            family = ""
        included = bool(raw.get("included")) and bool(family)
        suggested = str(raw.get("suggestedFamily") or "").strip().upper()
        rejected = ""
        if not included and suggested in FAMILIES:
            rejected = suggested
        paths[path] = {
            "name": str(raw.get("name") or "").strip(),
            "signature": str(raw.get("signature") or ""),
            "included": included,
            "family": family,
            "rejectedFamily": rejected,
            "accessory": bool(raw.get("accessory")),
            "process": _process(str(raw.get("process") or "")),
            "herinox": str(raw.get("herinox") or "").strip(),
        }
    save_memory(memory)
    learned = sum(1 for item in paths.values() if item.get("included") or item.get("accessory") or item.get("rejectedFamily"))
    return {"ok": True, "message": f"Aprendizaje guardado. {learned} piezas en memoria.", "learned": learned}


def export_lists(folder: str, rows: list[dict], job: str = "") -> dict:
    saved = remember_rows(rows)
    dest = Path(folder)
    if not folder or not dest.exists():
        return {"ok": False, "message": "Elige la carpeta destino antes de exportar.", "learned": saved.get("learned", 0)}
    if dest.name.lower() != "autodxf":
        dest = dest / "AutoDXF"
    dest.mkdir(parents=True, exist_ok=True)
    job_id = str(job or "").strip()
    if job_id:
        dest = dest / job_id
        dest.mkdir(parents=True, exist_ok=True)

    lengths = [row for row in rows if row.get("included") and row.get("family")]
    missing = [row["name"] for row in lengths if "|" not in str(row.get("herinox") or "")]
    if missing:
        shown = ", ".join(missing[:8])
        extra = f" y {len(missing) - 8} más" if len(missing) > 8 else ""
        return {
            "ok": False,
            "message": f"Falta el material Herinox en: {shown}{extra}",
            "learned": saved.get("learned", 0),
        }

    length_path = dest / "Lista_Perfiles_Clasificados.csv"
    accessory_path = dest / "Accesorios_Sueltos.csv"
    length_csv = ["Nombre,Clasificación,Largo (in),Cantidad,Proceso"]
    for row in lengths:
        length_csv.append(
            ",".join(
                (
                    _csv(row.get("name")),
                    _csv(row.get("herinox")),
                    f"{float(row.get('lengthIn') or 0):.3f}",
                    str(int(row.get("qty") or 0)),
                    _csv(row.get("process")),
                )
            )
        )
    accessories = [row for row in rows if row.get("accessory")]
    accessory_csv = ["Nombre,Cantidad,Morfologia,Clasificacion,Motivo"]
    for row in accessories:
        accessory_csv.append(
            ",".join(
                (
                    _csv(row.get("name")),
                    str(int(row.get("qty") or 0)),
                    _csv(row.get("family")),
                    _csv(row.get("classification")),
                    _csv(row.get("accessoryWhy")),
                )
            )
        )
    length_path.write_text("\n".join(length_csv) + "\n", encoding="utf-8")
    accessory_path.write_text("\n".join(accessory_csv) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "message": (
            f"Lista de largos: {len(lengths)} perfiles. Accesorios sueltos: {len(accessories)}. "
            f"{length_path}"
        ),
        "lengthPath": str(length_path),
        "accessoryPath": str(accessory_path),
        "learned": saved.get("learned", 0),
    }


def load_memory() -> dict:
    if not MEMORY_PATH.is_file():
        return {"paths": {}}
    try:
        data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"paths": {}}
    if not isinstance(data, dict) or not isinstance(data.get("paths"), dict):
        return {"paths": {}}
    return data


def save_memory(memory: dict) -> None:
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_PATH.write_text(json.dumps(memory, ensure_ascii=False, indent=2), encoding="utf-8")


def _row_from_part(part, sample: dict, stock: list[dict], memory: dict) -> dict:
    name = Path(_name(part)).stem or _name(part)
    path = _full_name(part)
    material = _material(part)
    classification = _classification(part)
    hardware = _is_hardware(name)
    heuristic = "" if hardware else classify_sample(sample)
    sign = "" if hardware else signature_of(sample)
    decision = _decide(path, name, sign, heuristic, classification, memory)
    family = decision["family"]
    herinox = decision["herinox"] or suggest_stock(family, sample["width"], sample["thick"], material, stock)
    why = decision["accessoryWhy"]
    if decision["accessory"] and not why:
        why = _accessory_why(classification, decision["source"])
    return {
        "name": name,
        "path": path,
        "qty": 0,
        "lengthIn": round(sample["length"], 3),
        "widthIn": round(sample["width"], 3),
        "thickIn": round(sample["thick"], 3),
        "fill": round(sample["fill"], 2),
        "family": family,
        "suggestedFamily": heuristic,
        "source": decision["source"],
        "included": decision["included"],
        "accessory": decision["accessory"],
        "accessoryWhy": why,
        "process": decision["process"] or ("CORTE" if decision["included"] else ""),
        "herinox": herinox,
        "signature": sign,
        "hardware": hardware,
        "kind": "part",
        "classification": classification,
    }


def _decide(path: str, name: str, sign: str, heuristic: str, classification: str, memory: dict) -> dict:
    record = _path_record(memory, path) or _stem_record(memory, name)
    source = "morfologia"
    family = heuristic
    included = bool(heuristic)
    accessory = _class_is_accessory(classification)
    process = ""
    herinox = ""
    if record:
        source = "ruta" if _path_record(memory, path) else "nombre"
        family = record.get("family") or ""
        included = bool(record.get("included")) and bool(family)
        accessory = bool(record.get("accessory")) or accessory
        process = _process(str(record.get("process") or ""))
        herinox = str(record.get("herinox") or "")
        if record.get("rejectedFamily") and not record.get("included"):
            included = False
            family = ""
    else:
        learned = _signature_family(memory, sign, heuristic)
        if learned == "reject":
            included = False
            family = ""
            source = "aprendido"
        elif learned:
            family = learned
            included = True
            source = "aprendido"
        if _signature_accessory(memory, sign):
            accessory = True
            if source == "morfologia":
                source = "aprendido"
    return {
        "family": family if family in FAMILIES else "",
        "included": included,
        "accessory": accessory,
        "accessoryWhy": _accessory_why(classification, source if accessory else ""),
        "process": process,
        "herinox": herinox,
        "source": source if included or accessory else source,
    }


def _signature_family(memory: dict, sign: str, heuristic: str) -> str:
    if not sign:
        return ""
    accepts: dict[str, int] = {}
    rejects: dict[str, int] = {}
    for record in memory.get("paths", {}).values():
        if record.get("signature") != sign:
            continue
        family = str(record.get("family") or "")
        if record.get("included") and family in FAMILIES:
            accepts[family] = accepts.get(family, 0) + 1
        rejected = str(record.get("rejectedFamily") or "")
        if rejected in FAMILIES:
            rejects[rejected] = rejects.get(rejected, 0) + 1
    if not accepts and heuristic and rejects.get(heuristic, 0) >= 2:
        return "reject"
    if not accepts:
        return ""
    family = max(accepts, key=lambda item: accepts[item])
    if accepts[family] <= rejects.get(family, 0):
        return ""
    if heuristic and family != heuristic and accepts[family] < 2:
        return ""
    return family


def _signature_accessory(memory: dict, sign: str) -> bool:
    if not sign:
        return False
    confirmed = 0
    for record in memory.get("paths", {}).values():
        if record.get("signature") == sign and record.get("accessory"):
            confirmed += 1
    return confirmed >= 2


def _path_record(memory: dict, path: str) -> dict | None:
    record = memory.get("paths", {}).get(path)
    return record if isinstance(record, dict) else None


def _stem_record(memory: dict, name: str) -> dict | None:
    stem = name.strip().lower()
    if not stem:
        return None
    found = [
        record
        for record in memory.get("paths", {}).values()
        if str(record.get("name") or "").strip().lower() == stem
    ]
    if not found:
        return None
    families = {str(record.get("family") or "") for record in found if record.get("included")}
    families.discard("")
    if len(families) > 1:
        return None
    return found[-1]


def _collect_assemblies(assembly, grouped: dict[str, dict], memory: dict) -> None:
    root = _full_name(assembly)

    def walk(occurrences) -> None:
        try:
            count = int(occurrences.Count)
        except Exception:
            return
        for index in range(1, count + 1):
            try:
                occ = occurrences.Item(index)
                if bool(occ.Suppressed):
                    continue
                if int(occ.DefinitionDocumentType) != 12291:
                    continue
                doc = occ.Definition.Document
            except Exception:
                continue
            path = _full_name(doc)
            if not path or path == root:
                continue
            row = grouped.get(path)
            if row is None:
                classification = _classification(doc)
                name = Path(_name(doc)).stem or _name(doc)
                record = _path_record(memory, path) or _stem_record(memory, name)
                accessory = _class_is_accessory(classification) or bool(record and record.get("accessory"))
                grouped[path] = {
                    "name": name,
                    "path": path,
                    "qty": 0,
                    "lengthIn": 0,
                    "widthIn": 0,
                    "thickIn": 0,
                    "fill": 0,
                    "family": "",
                    "suggestedFamily": "",
                    "source": "iprop" if _class_is_accessory(classification) else "ruta" if record else "",
                    "included": False,
                    "accessory": accessory,
                    "accessoryWhy": _accessory_why(classification, "iprop" if accessory else ""),
                    "process": _process(str(record.get("process") or "")) if record else "",
                    "herinox": str(record.get("herinox") or "") if record else "",
                    "signature": "",
                    "hardware": False,
                    "kind": "assembly",
                    "classification": classification,
                }
            grouped[path]["qty"] += 1
            try:
                walk(doc.ComponentDefinition.Occurrences)
            except Exception:
                continue

    try:
        walk(assembly.ComponentDefinition.Occurrences)
    except Exception:
        return


def _measure(inv, part) -> dict:
    empty = {
        "length": 0.0,
        "width": 0.0,
        "thick": 0.0,
        "fill": 0.0,
        "hollow": False,
        "cylinders": 0,
        "sheet": _is_sheet(part),
        "mask": [],
    }
    try:
        definition = part.ComponentDefinition
        bodies = definition.SurfaceBodies
        body = None
        volume = 0.0
        for index in range(1, int(bodies.Count) + 1):
            candidate = bodies.Item(index)
            try:
                size = abs(float(candidate.Volume))
            except Exception:
                continue
            if size > volume:
                body = candidate
                volume = size
        if body is None:
            body = _first_body(part)
        if body is None:
            return empty
        box = body.RangeBox
        dims = sorted(
            abs(_inches(part, getattr(box.MaxPoint, axis) - getattr(box.MinPoint, axis)))
            for axis in ("X", "Y", "Z")
        )
        thick, width, bbox_length = (dims + [0, 0, 0])[:3]
        length = max(bbox_length, _longest_edge_inches(part, body))
        box_volume = thick * width * length
        fill = (volume / 16.387064) / box_volume if box_volume > 0 else 0
        cylinders, hollow = _faces(body)
        sample = {
            "length": length,
            "width": width,
            "thick": thick,
            "fill": fill,
            "hollow": hollow,
            "cylinders": cylinders,
            "sheet": empty["sheet"],
            "mask": [],
        }
        if not sample["sheet"] and not sample["hollow"] and fill < 0.8:
            sample["mask"] = _mask(inv, body, box)
        return sample
    except Exception:
        return empty


def _faces(body) -> tuple[int, bool]:
    cylinders = 0
    hollow = False
    try:
        shells = body.FaceShells
        saw_void = False
        for index in range(1, int(shells.Count) + 1):
            shell = shells.Item(index)
            try:
                saw_void = True
                if bool(shell.IsVoid):
                    hollow = True
            except Exception:
                pass
        if not saw_void and int(shells.Count) >= 2:
            hollow = True
    except Exception:
        hollow = False
    try:
        faces = body.Faces
        limit = min(int(faces.Count), 80)
        for index in range(1, limit + 1):
            if int(faces.Item(index).SurfaceType) == 5891:
                cylinders += 1
    except Exception:
        return cylinders, hollow
    return cylinders, hollow


def _mask(inv, body, box) -> list[bool]:
    try:
        shells = body.FaceShells
        shell = None
        for index in range(1, int(shells.Count) + 1):
            item = shells.Item(index)
            try:
                if bool(item.IsVoid):
                    continue
            except Exception:
                pass
            shell = item
            break
        if shell is None:
            return []
        tg = inv.TransientGeometry

        def code_at(x: float, y: float, z: float):
            point = tg.CreatePoint(float(x), float(y), float(z))
            try:
                return int(shell.IsPointInside(point, 0.02))
            except Exception:
                return None

        outside = code_at(box.MinPoint.X - 5, box.MinPoint.Y - 5, box.MinPoint.Z - 5)
        if outside is None:
            return []
        spans = {
            axis: abs(getattr(box.MaxPoint, axis) - getattr(box.MinPoint, axis))
            for axis in ("X", "Y", "Z")
        }
        length_axis = max(spans, key=spans.get)
        section = [axis for axis in ("X", "Y", "Z") if axis != length_axis]
        mid = {
            axis: (getattr(box.MinPoint, axis) + getattr(box.MaxPoint, axis)) / 2
            for axis in ("X", "Y", "Z")
        }
        bits = []
        for u in (0.2, 0.5, 0.8):
            for v in (0.2, 0.5, 0.8):
                coords = dict(mid)
                for axis, frac in zip(section, (u, v)):
                    low = getattr(box.MinPoint, axis)
                    high = getattr(box.MaxPoint, axis)
                    coords[axis] = low + (high - low) * frac
                code = code_at(coords["X"], coords["Y"], coords["Z"])
                if code is None:
                    return []
                bits.append(code != outside)
        return bits
    except Exception:
        return []


def _class_tokens(value: str) -> list[str]:
    from bloques import split_classes

    return [token.lower() for token in split_classes(value)]


def _class_is_assy(value: str) -> bool:
    return any(token.startswith("assy") for token in _class_tokens(value))


def _class_is_accessory(value: str) -> bool:
    return any(token in ACCESSORY_CLASSES for token in _class_tokens(value)) or _class_is_assy(value)


def _accessory_why(classification: str, source: str) -> str:
    if _class_is_accessory(classification):
        return classification.strip()
    if source == "aprendido":
        return "Morfología aprendida"
    if source in {"ruta", "nombre"}:
        return "Marcado por ingeniería"
    return ""


def _is_sheet(part) -> bool:
    try:
        return str(part.SubType).lower() == "{9c464203-9bae-11d3-8bad-0060b0ce6bb4}"
    except Exception:
        return False


def _is_hardware(name: str) -> bool:
    text = (name or "").lower()
    return any(token in text for token in _HARDWARE)


def _material(part) -> str:
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


def _first_body(part):
    try:
        bodies = part.ComponentDefinition.SurfaceBodies
        if int(bodies.Count) < 1:
            return None
        return bodies.Item(1)
    except Exception:
        return None


def _longest_edge_inches(part, body) -> float:
    longest_cm = 0.0
    try:
        edges = body.Edges
        total = int(edges.Count)
    except Exception:
        return 0.0
    for index in range(1, total + 1):
        try:
            evaluator = edges.Item(index).Evaluator
            extents = evaluator.GetParamExtents()
            start, end = (extents[0], extents[1]) if isinstance(extents, tuple) else (None, None)
            if start is None:
                continue
            measured = evaluator.GetLengthAtParam(float(start), float(end))
            if isinstance(measured, tuple):
                measured = measured[-1]
            value = abs(float(measured))
            if value > longest_cm:
                longest_cm = value
        except Exception:
            continue
    if longest_cm <= 0:
        return 0.0
    return _inches(part, longest_cm)


def _inches(part, value: float) -> float:
    try:
        return float(part.UnitsOfMeasure.ConvertUnits(float(value), 11268, 11272))
    except Exception:
        return float(value) / 2.54


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


def _process(value: str) -> str:
    text = (value or "").strip()
    for option in PROCESSES:
        if option.lower() == text.lower():
            return option
    return text


def _csv(value) -> str:
    text = "" if value is None else str(value)
    if any(token in text for token in (",", '"', "\n", "\r")):
        return '"' + text.replace('"', '""') + '"'
    return text


def _float(value: str) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return 0.0
