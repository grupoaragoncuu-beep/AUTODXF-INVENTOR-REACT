"""Instructivo de armado por subensamble .iam, sin plano .idw.

Cada .iam único con ≥2 hijos útiles (o clasificado Assy Tanks / Assy Loose)
se acota como kit: vista de frente de la placa-ancla, hijos visibles,
origen = esquina inferior-izquierda del ancla, una JPG por cota X/Y.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

from drawing_jpg import save_part_drawing
from inventor_session import _classes, _classification, _name, _short
from mesh_view import save_iso_mesh, silhouette, tessellate_document, tessellate_part

TIPO_IAM = 12291
TIPO_IPT = 12290
VISTAS = ("FRONT", "BACK", "TOP", "BOTTOM", "RIGHT", "LEFT")
MIN_PLACA = 0.25
MIN_HW = 1.0
TOL_TYP = 0.15
_RE_HW = re.compile(
    r"(^HW[-_])|(^DIN\d)|(^ISO\d)|"
    r"(WASHER|NUT|BOLT|SCREW|RIVET|FW[-_]|HN[-_]|HH[-_]|LOCK[\s_-]?WASHER)|"
    r"(\bSTACK\b)|(ISOLATOR)",
    re.IGNORECASE,
)
_RE_HOLE = re.compile(r"(_HOLE)", re.IGNORECASE)
# Misma lista que EsMuroAssy en SelectorComponentes.iLogicVb.
_MURO_TOKENS = (
    "segmento",
    "segm1",
    "segm2",
    "segm3",
    "segm4",
    "top cover",
    "tapa superior",
    "tank lid",
    "tank-lid",
    "base de soleras",
    "cuadro base",
    "base plate",
    "tank base",
    "tank-base",
)
def es_muro_nombre(nombre: str) -> bool:
    """Segmento, Top Cover, Base y Tank-Lid no son un kit Assy.

    "base" suelto o al inicio ("Base de soleras"). No un accesorio que solo menciona base.
    """
    name = str(nombre or "").strip().casefold()
    if not name:
        return False
    if any(token in name for token in _MURO_TOKENS):
        return True
    if name in {"base", "tapa"} or name.startswith("base ") or name.startswith("tapa "):
        return True
    return False


def collect_kits(assembly, classes: set[str], omit: set[str]) -> list[tuple[object, int, str]]:
    """Únicos .iam bajo el tanque: clasificados Assy o con ≥2 hijos útiles."""
    grouped: dict[str, list] = {}
    try:
        root = str(assembly.FullFileName or "").replace("\\", "/").lower()
    except Exception:
        root = ""

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
                if int(occ.DefinitionDocumentType) != TIPO_IAM:
                    continue
                doc = occ.Definition.Document
                key = str(doc.FullFileName or "").replace("\\", "/").lower()
            except Exception:
                continue
            if key and key != root:
                grouped.setdefault(key, []).append(doc)
            try:
                walk(occ.SubOccurrences)
            except Exception:
                continue

    try:
        walk(assembly.ComponentDefinition.Occurrences)
    except Exception:
        return []

    rows: list[tuple[object, int, str]] = []
    for docs in grouped.values():
        doc = docs[0]
        clas = str(_classification(doc) or "").strip()
        keys = _classes(doc)
        if keys and not keys - omit - {"almacen", "almacén"}:
            continue
        n_utiles = len(_hijos_utiles(doc))
        marcado = bool(keys & classes)
        if not marcado and n_utiles < 2:
            continue
        rows.append((doc, len(docs), clas))
    rows.sort(key=lambda item: _name(item[0]).lower())
    return rows


def exportar_detalle_hijos(
    files: list[str],
    errors: list[str],
    assy,
    job: str,
    item: str,
    unit: str,
    dest_kit: Path,
) -> int:
    """Cotas de sólido de cada hijo (Ø, PASADO, escalón), la misma lectura que Maquinado.

    El STEP del kit lo escribe el llamador. Un hijo sin círculos ni placa no agrega JPG.
    """
    from maquinado_geo import cotas_de, dibujar, morfologia
    from referencia_geo import preparar_def
    from referencia_snapshot import _def_con_cache

    escritos = 0
    for hijo in _hijos_utiles(assy):
        if hijo.get("es_hw") or hijo.get("es_almacen"):
            continue
        doc = hijo.get("doc")
        try:
            if int(doc.DocumentType) != TIPO_IPT:
                continue
        except Exception:
            continue
        nombre = str(hijo.get("name") or "hijo")
        try:
            morf = morfologia(preparar_def(_def_con_cache(doc, {"cache": 0, "nuevas": 0})))
            cotas = cotas_de(morf, unit)
        except Exception as ex:
            errors.append(f"{item}/{nombre} sólido: {ex}")
            continue
        if not cotas:
            continue
        folder = Path(dest_kit) / _carpeta(nombre)
        folder.mkdir(parents=True, exist_ok=True)
        for cota in cotas:
            marca = str(cota.get("name") or "cota")
            try:
                files.append(dibujar(folder / _archivo(job, nombre, marca), morf, cota, f"{nombre}  {marca}"))
                escritos += 1
            except Exception as ex:
                errors.append(f"{item}/{nombre} {marca}: {ex}")
    return escritos


def exportar_kit(
    files: list[str],
    errors: list[str],
    assy,
    qty: int,
    item: str,
    job: str,
    unit: str,
    dest_kit: Path,
    dest_iso: Path,
) -> None:
    dest_kit = Path(dest_kit)
    dest_iso = Path(dest_iso)
    dest_kit.mkdir(parents=True, exist_ok=True)
    dest_iso.mkdir(parents=True, exist_ok=True)
    hijos = _hijos_utiles(assy, incluir_almacen=True)
    ancla = _elegir_ancla(hijos)
    cameras = _camaras(_ejes_ancla_mundo(ancla, unit) or _ejes(assy, unit))
    mesh = None
    try:
        mesh = tessellate_document(assy, chord=0.01)
    except Exception as ex:
        errors.append(f"{item} malla: {_short(ex)}")
    if mesh:
        try:
            files.append(
                save_iso_mesh(
                    dest_iso / f"{job}_{item}_ISO.jpg".replace(" ", "_"),
                    mesh,
                    title=item,
                    subtitle=f"qty {qty}  ·  Inspección Visual",
                )
            )
        except Exception as ex:
            errors.append(f"{item} ISO: {_short(ex)}")
    if not hijos or not cameras:
        return
    for vista, look, u_axis, v_axis in cameras:
        try:
            n = _exportar_vista(
                files,
                assy,
                hijos,
                ancla,
                look,
                u_axis,
                v_axis,
                unit,
                dest_kit / vista,
                job,
                item,
                mesh,
            )
            if n == 0:
                errors.append(f"{item} {vista}: sin cotas X/Y de hijos")
        except Exception as ex:
            errors.append(f"{item} {vista}: {_short(ex)}")


def _hijos_utiles(asm_doc, *, incluir_almacen: bool = False) -> list[dict]:
    hijos = []
    try:
        occs = asm_doc.ComponentDefinition.Occurrences
        total = int(occs.Count)
    except Exception:
        return hijos
    vistos: dict[str, int] = {}
    for index in range(1, total + 1):
        try:
            occ = occs.Item(index)
            if bool(occ.Suppressed):
                continue
            rb = occ.RangeBox
            doc = occ.Definition.Document
            es_almacen = bool(_classes(doc) & {"almacén", "almacen"})
            if es_almacen and not incluir_almacen:
                continue
            nombre = Path(_name(doc)).stem or str(occ.Name).split(":")[0]
            if _RE_HOLE.search(nombre):
                continue
            pieza_id = str(occ.Name).replace(":", "_")
            vistos[nombre] = vistos.get(nombre, 0) + 1
            if vistos[nombre] > 1:
                pieza_id = f"{nombre}_{vistos[nombre]}"
            hijos.append(
                {
                    "name": nombre,
                    "pieza_id": pieza_id,
                    "occ": occ,
                    "doc": doc,
                    "rb": rb,
                    "es_hw": bool(_RE_HW.search(nombre)),
                    "es_almacen": es_almacen,
                }
            )
        except Exception:
            continue
    return hijos


def _ejes(doc, unit: str) -> list[dict]:
    try:
        box = doc.ComponentDefinition.RangeBox
        uom = doc.UnitsOfMeasure
        target = "mm" if str(unit).lower() == "mm" else "in"
    except Exception:
        return []
    rows = []
    for vec, axis in (((1.0, 0.0, 0.0), "X"), ((0.0, 1.0, 0.0), "Y"), ((0.0, 0.0, 1.0), "Z")):
        raw = abs(float(getattr(box.MaxPoint, axis)) - float(getattr(box.MinPoint, axis)))
        try:
            size = abs(float(uom.ConvertUnits(raw, "cm", target)))
        except Exception:
            size = abs(raw)
        rows.append({"vec": vec, "size": size, "axis": axis})
    rows.sort(key=lambda item: -item["size"])
    return rows


def _neg(v):
    return (-v[0], -v[1], -v[2])


def _camaras(axes: list[dict]) -> list[tuple[str, tuple, tuple, tuple]]:
    if len(axes) < 2:
        return []
    x, y = axes[0]["vec"], axes[1]["vec"]
    z = axes[2]["vec"] if len(axes) > 2 else _norm(_cross(x, y))
    return [
        ("FRONT", z, x, y),
        ("BACK", _neg(z), _neg(x), y),
        ("TOP", y, x, _neg(z)),
        ("BOTTOM", _neg(y), x, z),
        ("RIGHT", x, _neg(z), y),
        ("LEFT", _neg(x), z, y),
    ]


def _elegir_ancla(hijos: list[dict]) -> dict | None:
    utiles = [h for h in hijos if h.get("rb") is not None]
    if not utiles:
        return None
    return max(utiles, key=_score_ancla)


def _score_ancla(hijo: dict) -> float:
    tam = _tamano(hijo)
    if not tam:
        return 0.0
    sx, sy, sz = tam
    cara = max(sx * sy, sy * sz, sx * sz)
    espesor = max(min(sx, sy, sz), 1e-3)
    score = cara * (1.0 + min(cara / espesor, 40.0) * 0.2)
    nom = str(hijo.get("name") or "")
    if hijo.get("es_hw") or _RE_HW.search(nom):
        return score * 0.02
    if re.search(r"-P\d+", nom, re.I):
        return score * 6.0
    if "placa" in nom.casefold() or "segmento" in nom.casefold():
        return score * 4.0
    return score


def _tamano(hijo: dict) -> tuple[float, float, float] | None:
    doc = hijo.get("doc")
    try:
        rb = doc.ComponentDefinition.RangeBox if doc is not None else hijo.get("rb")
        return (
            abs(float(rb.MaxPoint.X) - float(rb.MinPoint.X)),
            abs(float(rb.MaxPoint.Y) - float(rb.MinPoint.Y)),
            abs(float(rb.MaxPoint.Z) - float(rb.MinPoint.Z)),
        )
    except Exception:
        return None


def _exportar_vista(
    files: list[str],
    assy,
    hijos: list[dict],
    ancla: dict | None,
    look,
    u_axis,
    v_axis,
    unit: str,
    dest: Path,
    job: str,
    item: str,
    mesh,
) -> int:
    dest.mkdir(parents=True, exist_ok=True)
    scale = _escala(assy, unit)
    ancla = ancla or (hijos[0] if hijos else None)
    if ancla is None:
        return 0
    origin = _centro_occ(ancla.get("occ")) or _centro_doc(assy)
    ancla_env = _proyectar_occ(ancla.get("occ"), origin, u_axis, v_axis, scale)
    if ancla_env is None:
        return 0
    ox, oy = float(ancla_env["minu"]), float(ancla_env["minv"])
    span_u = max(float(ancla_env["maxu"]) - ox, 0.5)
    span_v = max(float(ancla_env["maxv"]) - oy, 0.5)
    if min(span_u, span_v) < 0.4:
        return 0
    outline = _silueta_ancla(ancla, origin, u_axis, v_axis, look, scale)
    outline = [(x - ox, y - oy) for x, y in outline]
    if len(outline) < 3:
        outline = [(0.0, 0.0), (span_u, 0.0), (span_u, span_v), (0.0, span_v)]
    holes = []
    cotas: list[dict] = []
    vistos: set[tuple] = set()
    ancla_id = str(ancla.get("pieza_id") or "")
    for hijo in hijos:
        if str(hijo.get("pieza_id") or "") == ancla_id:
            continue
        env = _proyectar_occ(hijo.get("occ"), origin, u_axis, v_axis, scale)
        if env is None:
            continue
        pts = [(p[0] - ox, p[1] - oy) for p in env["pts"]]
        if len(pts) < 3:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        x_val = min(xs)
        y_val = min(ys)
        min_ok = MIN_HW if hijo.get("es_hw") else MIN_PLACA
        holes.append(
            {
                "kind": "cut",
                "pts": pts,
                "acota": True,
                "name": hijo.get("name"),
            }
        )
        if hijo.get("es_hw"):
            if abs(x_val) >= abs(y_val) and abs(x_val) >= min_ok:
                _add_cota(cotas, vistos, "X", x_val)
            elif abs(y_val) >= min_ok:
                _add_cota(cotas, vistos, "Y", y_val)
        else:
            if abs(x_val) >= min_ok:
                _add_cota(cotas, vistos, "X", x_val)
            if abs(y_val) >= min_ok:
                _add_cota(cotas, vistos, "Y", y_val)
    if not holes:
        return 0
    xs = [p[0] for p in outline]
    ys = [p[1] for p in outline]
    measures = {
        "LENGTH": round(max(max(xs) - min(xs), span_u, 1.0), 3),
        "WIDTH": round(max(max(ys) - min(ys), span_v, 1.0), 3),
        "THK": 0.0,
    }
    n = 0
    for cota in cotas:
        marca = str(cota["name"])
        dest_jpg = dest / _archivo(job, item, f"{dest.name}_{marca}")
        files.append(
            save_part_drawing(
                dest_jpg,
                outline,
                holes,
                title=f"{item}  {dest.name}  {marca}",
                subtitle="",
                unit=unit,
                measures=measures,
                hole_anchor="edge",
                measure_walls=False,
                focus=cota,
                landscape=False,
            )
        )
        n += 1
    return n


def _add_cota(cotas: list[dict], vistos: set[tuple], eje: str, valor: float) -> None:
    valor = abs(float(valor))
    key = (eje, round(valor / TOL_TYP) * TOL_TYP)
    if key in vistos:
        return
    vistos.add(key)
    cotas.append({"kind": eje, "value": valor, "name": f"{eje}_{valor:.2f}"})


def _ejes_ancla_mundo(ancla: dict | None, unit: str) -> list[dict]:
    if not ancla or ancla.get("occ") is None or ancla.get("doc") is None:
        return []
    locales = _ejes(ancla["doc"], unit)
    mat = _mat4(ancla["occ"])
    if not locales or mat is None:
        return []
    rows = []
    for item in locales:
        rows.append({**item, "vec": _norm(_xform_vec(mat, item["vec"]))})
    return rows


def _proyectar_occ(occ, origin, u_axis, v_axis, scale: float) -> dict | None:
    corners = _esquinas_mundo(occ)
    if len(corners) < 4:
        return None
    pts = [_proy(pt, origin, u_axis, v_axis, scale) for pt in corners]
    us = [p[0] for p in pts]
    vs = [p[1] for p in pts]
    hull = _convex(pts)
    return {
        "minu": min(us),
        "maxu": max(us),
        "minv": min(vs),
        "maxv": max(vs),
        "pts": hull if len(hull) >= 3 else _hull(pts),
    }


def _proy(pt, origin, u_axis, v_axis, scale: float) -> tuple[float, float]:
    d = (pt[0] - origin[0], pt[1] - origin[1], pt[2] - origin[2])
    return (_dot(d, u_axis) * scale, _dot(d, v_axis) * scale)


def _silueta_ancla(ancla: dict, origin, u_axis, v_axis, look, scale: float) -> list[tuple[float, float]]:
    occ = ancla.get("occ")
    doc = ancla.get("doc")
    if occ is None or doc is None:
        return []
    try:
        mesh = tessellate_part(doc, chord=0.004)
    except Exception:
        mesh = None
    if not mesh:
        return []
    mat = _mat4(occ)
    if mat is None:
        return []
    world = {
        "verts": [_xform_pt(mat, *v) for v in mesh["verts"]],
        "tris": mesh["tris"],
        "norms": mesh.get("norms") or [],
    }
    outline, _mask = silhouette(world, origin, u_axis, v_axis, look, unit_scale=scale, size=1100, min_px=80)
    return outline or []


def _esquinas_mundo(occ) -> list[tuple[float, float, float]]:
    try:
        rb = occ.Definition.Document.ComponentDefinition.RangeBox
        mat = _mat4(occ)
    except Exception:
        return []
    if mat is None:
        return []
    xs = (float(rb.MinPoint.X), float(rb.MaxPoint.X))
    ys = (float(rb.MinPoint.Y), float(rb.MaxPoint.Y))
    zs = (float(rb.MinPoint.Z), float(rb.MaxPoint.Z))
    pts = []
    for x in xs:
        for y in ys:
            for z in zs:
                pts.append(_xform_pt(mat, x, y, z))
    return pts


def _mat4(occ) -> list[list[float]] | None:
    try:
        m = occ.Transformation
        return [[float(m.Cell(r, c)) for c in range(1, 5)] for r in range(1, 4)]
    except Exception:
        return None


def _xform_pt(m, x: float, y: float, z: float) -> tuple[float, float, float]:
    return (
        m[0][0] * x + m[0][1] * y + m[0][2] * z + m[0][3],
        m[1][0] * x + m[1][1] * y + m[1][2] * z + m[1][3],
        m[2][0] * x + m[2][1] * y + m[2][2] * z + m[2][3],
    )


def _xform_vec(m, v) -> tuple[float, float, float]:
    return (
        m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
        m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
        m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2],
    )


def _centro_occ(occ) -> tuple[float, float, float] | None:
    pts = _esquinas_mundo(occ)
    if not pts:
        return None
    return (
        sum(p[0] for p in pts) / len(pts),
        sum(p[1] for p in pts) / len(pts),
        sum(p[2] for p in pts) / len(pts),
    )


def _convex(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    uniq = sorted(set((round(p[0], 5), round(p[1], 5)) for p in pts))
    if len(uniq) <= 2:
        return [(float(x), float(y)) for x, y in uniq]
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower = []
    for p in uniq:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(uniq):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return [(float(x), float(y)) for x, y in lower[:-1] + upper[:-1]]


def _centro_doc(doc) -> tuple[float, float, float]:
    box = doc.ComponentDefinition.RangeBox
    return (
        (float(box.MinPoint.X) + float(box.MaxPoint.X)) / 2,
        (float(box.MinPoint.Y) + float(box.MaxPoint.Y)) / 2,
        (float(box.MinPoint.Z) + float(box.MaxPoint.Z)) / 2,
    )


def _escala(doc, unit: str) -> float:
    target = "mm" if str(unit).lower() == "mm" else "in"
    try:
        return float(doc.UnitsOfMeasure.ConvertUnits(1.0, "cm", target))
    except Exception:
        return 1.0 / 2.54 if target == "in" else 10.0


def _hull(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    xs = [p[0] for p in pts] or [0.0]
    ys = [p[1] for p in pts] or [0.0]
    return [
        (min(xs), min(ys)),
        (max(xs), min(ys)),
        (max(xs), max(ys)),
        (min(xs), max(ys)),
    ]


def _carpeta(nombre: str) -> str:
    base = str(nombre or "hijo")
    for ch in '<>:"/\\|?*':
        base = base.replace(ch, "_")
    return base.strip().rstrip(". ") or "hijo"


def _archivo(job: str, item: str, marca: str) -> str:
    base = f"{job}_{item}_{marca}"
    for ch in '<>:"/\\|?*':
        base = base.replace(ch, "_")
    return f"{base}.jpg"


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b) -> tuple[float, float, float]:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a) -> tuple[float, float, float]:
    mag = math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2]) or 1.0
    return (a[0] / mag, a[1] / mag, a[2] / mag)
