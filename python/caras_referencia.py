"""COTAS_POR_REFERENCIA: ubicación de hijos en 6 caras del tanque (FRONT Pillow).

Inventor a menudo reutiliza el mismo Occurrence.Name en copias/patrones
(p. ej. cinco C Channel Brace llamados ..._64). No se agrupa por nombre:
cada instancia va al par de muro (S1↔S3, S2↔S4, TOP↔BASE) según el lado
de la placa, para el Módulo de Ingeniería y la barra local.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from armado_kit import (
    TIPO_IAM,
    TIPO_IPT,
    _RE_HOLE,
    _RE_HW,
    _centro_doc,
    _centro_occ,
    _cross,
    _dot,
    _ejes,
    _ejes_ancla_mundo,
    _elegir_ancla,
    _escala,
    _mat4,
    _neg,
    _norm,
    _proyectar_occ,
    _xform_pt,
)
from drawing_jpg import _letra, _px_cota
from inventor_session import _classification, _name, _short
from mesh_view import _proy as _proy_mesh
from mesh_view import tessellate_part
from vista_hlr import capturar_alambrico

ORDEN_CARAS = ("TOP", "SEGM1", "SEGM2", "SEGM3", "SEGM4", "BASE")
PAR_CARA = {
    "SEGM1": "SEGM3",
    "SEGM3": "SEGM1",
    "SEGM2": "SEGM4",
    "SEGM4": "SEGM2",
    "TOP": "BASE",
    "BASE": "TOP",
}
_MESH_CACHE: dict[str, object] = {}
DEFAULT_FACES = {
    "TOP": ["top cover", "tapa superior", "tank lid", "tank-lid", "tapa"],
    "SEGM1": ["segmento 1", "segmento #1", "segm1", "s1"],
    "SEGM2": ["segmento 2", "segmento #2", "segm2", "s2"],
    "SEGM3": ["segmento 3", "segmento #3", "segm3", "s3"],
    "SEGM4": ["segmento 4", "segmento #4", "segm4", "s4"],
    "BASE": ["base de soleras", "cuadro base", "base plate", "tank base", "tank-base", "base"],
}
MIN_COTA = 0.20
CONTROL_DIR = Path(__file__).resolve().parents[1] / "cotas-por-referencia"
ARRIBA_MUNDO = (0.0, 1.0, 0.0)
TOL = 0.12
_RE_CIRC = re.compile(
    r"(flange|flane|pipe|niple|nipple|tierra|ground|boss|gauge|od[\s_-]|rfso|wnrf|swrf)",
    re.I,
)


def collect_caras(assembly, faces_cfg=None) -> list[tuple]:
    """Caras TOP / SEGM1–4 / BASE: .iam de cara, placas IPT, o selector L2 por geometría."""
    _MESH_CACHE.clear()
    patterns = _patrones(faces_cfg)
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

    best: dict[str, tuple[int, object, int]] = {}
    for docs in grouped.values():
        doc = docs[0]
        cara, score = _cara_de(_name(doc), patterns)
        if not cara:
            continue
        n_hijos = _contar_hijos(doc)
        prev = best.get(cara)
        if prev is None or score > prev[0] or (score == prev[0] and n_hijos > _contar_hijos(prev[1])):
            best[cara] = (score, doc, len(docs))
    iam_rows = [(cara, best[cara][1], best[cara][2], None) for cara in ORDEN_CARAS if cara in best]
    sesion = []
    try:
        from roles_inventor import filas_desde_sesion

        sesion = filas_desde_sesion(assembly) or []
    except Exception:
        sesion = []
    ipt_rows = _collect_ipt_caras(assembly, patterns)
    anclas = {}
    for row in list(sesion) + list(ipt_rows):
        occ = row[3] if len(row) > 3 else None
        if occ is not None:
            anclas.setdefault(row[0], occ)
    geo = []
    try:
        from roles_inventor import last_bags, proponer_muros

        bags = last_bags() if sesion else {}
        if len(anclas) < 6:
            bags = proponer_muros(assembly, anclas_por_cara=anclas or None) or bags
        for cara in ORDEN_CARAS:
            miembros = (bags or {}).get(cara) or []
            ancla = next((m for m in miembros if m.get("placa_rol") and m.get("occ") is not None), None)
            if ancla is None:
                ancla = next((m for m in miembros if m.get("occ") is not None), None)
            if ancla is not None:
                geo.append((cara, assembly, 1, ancla["occ"]))
    except Exception:
        geo = []
    merged: dict[str, tuple] = {}
    for source in (sesion, geo, iam_rows if len(iam_rows) >= 6 else [], ipt_rows, iam_rows):
        for row in source:
            if row and row[0] not in merged:
                merged[row[0]] = row
    return [merged[cara] for cara in ORDEN_CARAS if cara in merged]


def mapa_ipt_cara(assembly, faces_cfg=None) -> dict[str, str]:
    """FullFileName .ipt → cara: selector L2 (contacto), IAM de cara o nombre S1/BASE."""
    out: dict[str, str] = {}
    patterns = _patrones(faces_cfg)
    rows = collect_caras(assembly, faces_cfg)
    try:
        from roles_inventor import mapa_desde_bolsas

        out.update(mapa_desde_bolsas())
    except Exception:
        pass
    for row in rows:
        cara, doc, _qty = row[0], row[1], row[2]
        ancla_occ = row[3] if len(row) > 3 else None
        if ancla_occ is not None:
            try:
                path = str(ancla_occ.Definition.Document.FullFileName or "").replace("\\", "/").lower()
            except Exception:
                path = ""
            if path:
                out.setdefault(path, cara)
            continue
        try:
            leaves = doc.ComponentDefinition.Occurrences.AllLeafOccurrences
            total = int(leaves.Count)
        except Exception:
            continue
        for index in range(1, total + 1):
            try:
                occ = leaves.Item(index)
                if bool(occ.Suppressed):
                    continue
                child = occ.Definition.Document
                if int(getattr(child, "DocumentType", 0) or 0) != TIPO_IPT:
                    continue
                path = str(child.FullFileName or "").replace("\\", "/").lower()
            except Exception:
                continue
            if path:
                out.setdefault(path, cara)
    try:
        leaves = assembly.ComponentDefinition.Occurrences.AllLeafOccurrences
        total = int(leaves.Count)
    except Exception:
        return out
    for index in range(1, total + 1):
        try:
            occ = leaves.Item(index)
            if bool(occ.Suppressed):
                continue
            child = occ.Definition.Document
            if int(getattr(child, "DocumentType", 0) or 0) != TIPO_IPT:
                continue
            path = str(child.FullFileName or "").replace("\\", "/").lower()
            cara, _score = _cara_de(_name(child), patterns)
        except Exception:
            continue
        if path and cara:
            out.setdefault(path, cara)
    bags = {}
    try:
        from roles_inventor import filas_desde_sesion, last_bags

        if not last_bags():
            filas_desde_sesion(assembly)
        bags = last_bags() or {}
    except Exception:
        bags = {}
    anclas = _anclas_planos(assembly, bags)
    if not anclas:
        return out
    votos: dict[str, dict[str, int]] = {}
    try:
        occs = assembly.ComponentDefinition.Occurrences.AllLeafOccurrences
        total = int(occs.Count)
    except Exception:
        return out
    for index in range(1, total + 1):
        try:
            occ = occs.Item(index)
            if bool(occ.Suppressed):
                continue
            child = occ.Definition.Document
            if int(getattr(child, "DocumentType", 0) or 0) != TIPO_IPT:
                continue
            path = str(child.FullFileName or "").replace("\\", "/").lower()
        except Exception:
            continue
        muro = _muro_de_occ(occ, anclas)
        if not path or not muro:
            continue
        votos.setdefault(path, {})
        votos[path][muro] = votos[path].get(muro, 0) + 1
    for path, tally in votos.items():
        out[path] = max(tally, key=tally.get)
    return out


def exportar_cara(
    files: list[str],
    errors: list[str],
    assy,
    cara: str,
    qty: int,
    job: str,
    unit: str,
    dest_root: Path,
    ancla_occ=None,
) -> int:
    dest_cara = Path(dest_root) / cara
    bolsa = _miembros_bolsa(cara, assy)
    if bolsa:
        hijos = _hijos_de_bolsa(assy, bolsa, cara)
        ancla = next((h for h in hijos if h.get("placa_rol")), None)
        if ancla is None:
            ancla = _ancla_de_occ(hijos, ancla_occ) if ancla_occ is not None else _elegir_ancla(hijos)
    else:
        hijos = _hijos_hoja(assy) if ancla_occ is not None else _hijos_cara(assy)
        ancla = _ancla_de_occ(hijos, ancla_occ) if ancla_occ is not None else _elegir_ancla(hijos)
    if not hijos or ancla is None:
        errors.append(f"{cara}: sin placa-ancla o hijos")
        return 0
    cam = _camara_frente(ancla, hijos, unit, _centro_doc(assy))
    if cam is None:
        errors.append(f"{cara}: no se obtuvo FRONT de la placa")
        return 0
    look, u_axis, v_axis = cam
    scale = _escala(assy, unit)
    origin = _centro_occ(ancla.get("occ")) or _centro_doc(assy)
    ancla_uv = _uv_ancla(ancla, origin, u_axis, v_axis, look, scale)
    if ancla_uv is None:
        errors.append(f"{cara}: no se proyectó la malla del ancla")
        return 0
    ox, oy, span_u, span_v = ancla_uv
    n_antes = len(hijos)
    hijos = _filtrar_lado_placa(hijos, origin, look, scale, cara)
    print(
        f"  {cara}: lado placa {len(hijos)}/{n_antes} hijos (muro de 6, no solo par)",
        flush=True,
    )
    ancla_id = str(ancla.get("pieza_id") or "")
    piezas = []
    for hijo in hijos:
        if str(hijo.get("pieza_id") or "") == ancla_id:
            continue
        if _es_otra_placa(hijo, cara):
            continue
        env = _proyectar_occ(hijo.get("occ"), origin, u_axis, v_axis, scale)
        if env is None:
            continue
        xs = [p[0] - ox for p in env["pts"]]
        ys = [p[1] - oy for p in env["pts"]]
        if len(xs) < 3:
            continue
        if not _sobre_placa(hijo, origin, look, scale, ox, oy, span_u, span_v, xs, ys):
            continue
        circ = _es_circular(hijo, xs, ys)
        cx = (min(xs) + max(xs)) / 2
        cy = (min(ys) + max(ys)) / 2
        piezas.append(
            {
                "tipo": _tipo(hijo.get("name") or "TIPO"),
                "name": hijo.get("name"),
                "xmin": min(xs),
                "ymin": min(ys),
                "xmax": max(xs),
                "ymax": max(ys),
                "cx": cx,
                "cy": cy,
                "circ": circ,
                "x": cx if circ else min(xs),
                "y": cy if circ else min(ys),
            }
        )
    ctrl = _control_referencia()
    solo_vista = bool(ctrl.get("solo_vista"))
    if not piezas and not solo_vista:
        errors.append(f"{cara}: sin hijos que acotar (no se cota la placa madre)")
        return 0
    if dest_cara.is_dir():
        import shutil

        shutil.rmtree(dest_cara, ignore_errors=True)
    dest_cara.mkdir(parents=True, exist_ok=True)
    margen = 0.55
    crop = (ox - margen, oy - margen, ox + span_u + margen, oy + span_v + margen)
    try:
        inv = assy.Parent
        active = assy
        width_cm = max((span_u + 2 * margen) / max(scale, 1e-9), 1.0)
        height_cm = max((span_v + 2 * margen) / max(scale, 1e-9), 1.0)
        keep_nombres = []
        keep_rutas = []
        for h in hijos:
            occ = h.get("occ")
            if occ is None:
                continue
            try:
                keep_nombres.append(str(occ.Name))
            except Exception:
                pass
            try:
                keep_rutas.append(str(occ.Definition.Document.FullFileName or "").replace("\\", "/").lower())
            except Exception:
                path = str(h.get("name") or "")
                if path:
                    keep_rutas.append(path)
        base = capturar_alambrico(
            inv=inv,
            active_asm=active,
            scene_doc=assy,
            cara=cara,
            keep_nombres=keep_nombres,
            keep_rutas=keep_rutas,
            origin=origin,
            look=look,
            v_axis=v_axis,
            width_cm=width_cm,
            height_cm=height_cm,
            dest=dest_cara / "_hlr.jpg",
            scale=scale,
            tank_c=_centro_doc(assy),
        )
    except Exception as ex:
        errors.append(f"{cara}: vista Inventor alambrica {_short(ex)}")
        return 0
    width_in = span_u + 2 * margen
    height_in = span_v + 2 * margen
    w0, h0 = base.size

    def px_full(x: float, y: float) -> tuple[float, float]:
        u = ox + float(x)
        v = oy + float(y)
        return ((u / width_in + 0.5) * (w0 - 1), (0.5 - v / height_in) * (h0 - 1))

    a = px_full(0.0, 0.0)
    b = px_full(span_u, span_v)
    pad = 28
    box = (
        max(0, int(min(a[0], b[0]) - pad)),
        max(0, int(min(a[1], b[1]) - pad)),
        min(w0, int(max(a[0], b[0]) + pad)),
        min(h0, int(max(a[1], b[1]) + pad)),
    )
    base = base.crop(box)

    def px(x: float, y: float) -> tuple[float, float]:
        p = px_full(x, y)
        return (p[0] - box[0], p[1] - box[1])

    _limpiar_cara_frontal(base, px, span_u, span_v)
    vista_limpia = dest_cara / "VISTA_ALAMBRICA.jpg"
    try:
        base.save(vista_limpia, "JPEG", quality=92)
        files.append(str(vista_limpia))
    except Exception:
        pass
    if not solo_vista:
        extra_l, extra_t, extra_b = 130, 44, 88
        lienzo = Image.new("RGB", (base.size[0] + extra_l, base.size[1] + extra_t + extra_b), (255, 255, 255))
        lienzo.paste(base, (extra_l, extra_t))
        base = lienzo
        px_placa = px

        def px(x: float, y: float) -> tuple[float, float]:
            p = px_placa(x, y)
            return (p[0] + extra_l, p[1] + extra_t)

    _escribir_camara(
        dest_cara,
        cara=cara,
        look=look,
        u_axis=u_axis,
        v_axis=v_axis,
        ox=ox,
        oy=oy,
        span_u=span_u,
        span_v=span_v,
        origen="IL",
        hijos=len(hijos),
        piezas=len(piezas),
        modo=str(ctrl.get("vista") or "alambrico"),
        tipos=[p.get("tipo") for p in piezas],
    )
    if solo_vista:
        dest_jpg = dest_cara / "VISTA_ALAMBRICA.jpg"
        try:
            img = base.copy()
            _dibujar_origen_il(img, px, span_u=span_u, span_v=span_v, unit=unit)
            img.save(dest_jpg, "JPEG", quality=92)
            files.append(str(dest_jpg))
        except Exception as ex:
            errors.append(f"{cara}: vista alambrica {_short(ex)}")
            return 0
        return 1

    grupos: dict[str, list] = {}
    for pieza in piezas:
        grupos.setdefault(pieza["tipo"], []).append(pieza)
    n_jpg = 0
    for tipo, miembros in grupos.items():
        dest_tipo = dest_cara / _safe(tipo)
        dest_tipo.mkdir(parents=True, exist_ok=True)
        orden = sorted(miembros, key=lambda p: (p["cx"], p["cy"]))
        letras = {_id_pieza(p, i): _letra(i) for i, p in enumerate(orden)}
        vistos: set[tuple] = set()
        for pieza in miembros:
            kind_x = "XCENTRO" if pieza["circ"] else "XMIN"
            kind_y = "YCENTRO" if pieza["circ"] else "YMIN"
            for kind, valor in ((kind_x, pieza["x"]), (kind_y, pieza["y"])):
                if abs(valor) < MIN_COTA:
                    continue
                key = (kind, round(valor / TOL) * TOL)
                if key in vistos:
                    continue
                vistos.add(key)
                n_mismo = sum(1 for other in miembros if _misma_cota(other, kind, valor))
                marca = f"{kind}_{_fmt_val(valor)}"
                if n_mismo > 1:
                    marca = f"{kind}_TYP_{_fmt_val(valor)}"
                label = f"{kind}={_fmt_val(valor)} {unit}"
                if n_mismo > 1:
                    label = f"{kind}={_fmt_val(valor)} TYP {unit}"
                dest_jpg = dest_tipo / _archivo(job, tipo, marca)
                try:
                    foco = [
                        other
                        for other in miembros
                        if _misma_cota(other, kind, valor)
                    ]
                    img = base.copy()
                    _dibujar_cotas_ref(
                        img,
                        px,
                        title=f"{cara}  {tipo}  {marca}  qty {qty}",
                        kind=kind,
                        valor=float(valor),
                        label=label,
                        unit=unit,
                        foco=foco,
                        miembros=miembros,
                        letras=letras,
                    )
                    img.save(dest_jpg, "JPEG", quality=92)
                    files.append(str(dest_jpg))
                    n_jpg += 1
                except Exception as ex:
                    errors.append(f"{cara}/{tipo} {marca}: {_short(ex)}")
    return n_jpg


def _dibujar_origen_il(img, px, *, span_u: float, span_v: float, unit: str) -> None:
    """Marca 0,0 en la esquina inferior izquierda de la placa y los ejes X/Y."""
    draw = ImageDraw.Draw(img)
    font = _font_ref(_px_cota(16))
    fontb = _font_ref(18, True)
    o = px(0.0, 0.0)
    x1 = px(min(6.0, span_u * 0.14), 0.0)
    y1 = px(0.0, min(6.0, span_v * 0.14))
    placa = [px(0.0, 0.0), px(span_u, 0.0), px(span_u, span_v), px(0.0, span_v)]
    draw.line(placa + [placa[0]], fill="#C0392B", width=2)
    draw.line((o, x1), fill="#1A5276", width=3)
    draw.line((o, y1), fill="#1A5276", width=3)
    draw.ellipse((o[0] - 7, o[1] - 7, o[0] + 7, o[1] + 7), outline="#C0392B", width=3)
    draw.ellipse((o[0] - 3, o[1] - 3, o[0] + 3, o[1] + 3), fill="#C0392B")
    txt = px(1.1, 1.1)
    draw.text(txt, f"0,0 IL {unit}", fill="#1A5276", font=fontb)
    draw.text((x1[0] - 2, x1[1] - 22), "X", fill="#1A5276", font=fontb)
    draw.text((y1[0] + 10, y1[1] - 8), "Y", fill="#1A5276", font=fontb)
    draw.text(
        (14, 10),
        f"origen IL   X={_fmt_val(span_u)} {unit}   Y={_fmt_val(span_v)} {unit}",
        fill="#1B2631",
        font=font,
    )


def _font_ref(size: int, bold: bool = False):
    name = "arialbd.ttf" if bold else "arial.ttf"
    path = os.path.join(os.environ.get("WINDIR", r"C:\\Windows"), "Fonts", name)
    if os.path.isfile(path):
        return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _dibujar_cotas_ref(img, px, *, title, kind, valor, label, unit, foco, miembros, letras) -> None:
    draw = ImageDraw.Draw(img)
    _ = title
    font = _font_ref(16)
    font_cota = _font_ref(_px_cota(18), True)
    fontl = _font_ref(15, True)
    azul = "#1A5276"
    testigo = "#5D6D7E"
    o = px(0.0, 0.0)
    draw.ellipse((o[0] - 4, o[1] - 4, o[0] + 4, o[1] + 4), fill="#1B2631")
    draw.text((o[0] + 6, o[1] + 4), f"0,0 {unit}", fill="#1B2631", font=font)
    for other in miembros:
        letra = letras.get(_id_pieza(other)) or ""
        if not letra:
            continue
        p = px(other["cx"], other["cy"])
        draw.text((p[0] + 5, p[1] - 16), letra, fill="#0B1C2C", font=fontl)
    for item in foco:
        a = px(item["xmin"] - 0.25, item["ymax"] + 0.25)
        b = px(item["xmax"] + 0.25, item["ymin"] - 0.25)
        box = [min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])]
        draw.rectangle(box, outline="#F4D03F", width=4)
    if kind.startswith("X"):
        p0 = px(0.0, 0.0)
        p1 = px(valor, 0.0)
        yd = p0[1] + 42
        draw.line((p0[0], yd, p1[0], yd), fill=azul, width=2)
        draw.line((p0[0], yd - 8, p0[0], yd + 8), fill=azul, width=2)
        draw.line((p1[0], yd - 8, p1[0], yd + 8), fill=azul, width=2)
        draw.line((p0[0], p0[1], p0[0], yd), fill=testigo, width=1)
        for item in foco:
            c = px(valor, item["cy"])
            draw.line((c[0], c[1], c[0], yd), fill=testigo, width=1)
        mid = ((p0[0] + p1[0]) / 2, yd + 6)
        draw.text(mid, label, fill=azul, font=font_cota, anchor="mt")
    else:
        p0 = px(0.0, 0.0)
        p1 = px(0.0, valor)
        xd = p0[0] - 48
        draw.line((xd, p0[1], xd, p1[1]), fill=azul, width=2)
        draw.line((xd - 8, p0[1], xd + 8, p0[1]), fill=azul, width=2)
        draw.line((xd - 8, p1[1], xd + 8, p1[1]), fill=azul, width=2)
        draw.line((p0[0], p0[1], xd, p0[1]), fill=testigo, width=1)
        for item in foco:
            c = px(item["cx"], valor)
            draw.line((c[0], c[1], xd, c[1]), fill=testigo, width=1)
        mid = (xd - 8, (p0[1] + p1[1]) / 2)
        draw.text(mid, label, fill=azul, font=font_cota, anchor="rm")


def _camara_frente(ancla: dict, hijos: list[dict], unit: str, tank_c=None):
    """Cara frontal de la placa: eje delgado + Y mundo arriba. Cámara fuera del tanque."""
    ejes = _ejes_ancla_mundo(ancla, unit) or _ejes(ancla.get("doc"), unit)
    origin = _centro_occ(ancla.get("occ"))
    occ = ancla.get("occ")
    doc = ancla.get("doc")
    if not ejes or origin is None or occ is None or doc is None:
        return None
    try:
        raw = tessellate_part(doc, 0.03)
        mat = _mat4(occ)
    except Exception:
        raw, mat = None, None
    if not raw or mat is None:
        return None
    verts = [_xform_pt(mat, *p) for p in raw["verts"]]
    look = None
    espesor = None
    for item in ejes:
        vec = item["vec"]
        ds = [_dot(_sub(p, origin), vec) for p in verts]
        span = max(ds) - min(ds)
        if espesor is None or span < espesor:
            espesor = span
            look = vec
    if look is None:
        return None
    ancla_id = str(ancla.get("pieza_id") or "")
    umbral = float(espesor or 0.0) * 0.6 + 1e-4
    acc = 0.0
    n = 0
    for hijo in hijos:
        if str(hijo.get("pieza_id") or "") == ancla_id:
            continue
        c = _centro_occ(hijo.get("occ"))
        if c is None:
            continue
        d = _dot((c[0] - origin[0], c[1] - origin[1], c[2] - origin[2]), look)
        if abs(d) < umbral:
            continue
        acc += d
        n += 1
    if n and acc < 0:
        look = _neg(look)
    if tank_c is not None and origin is not None:
        afuera = _sub(origin, tank_c)
        if (afuera[0] * afuera[0] + afuera[1] * afuera[1] + afuera[2] * afuera[2]) > 1e-6:
            if _dot(look, afuera) < 0:
                look = _neg(look)
    ctrl = _control_referencia()
    arriba = tuple(ctrl.get("arriba_mundo") or ARRIBA_MUNDO)
    if len(arriba) != 3:
        arriba = ARRIBA_MUNDO
    v = _sub(arriba, _scale(look, _dot(arriba, look)))
    if (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) < 1e-8:
        v = _sub((1.0, 0.0, 0.0), _scale(look, _dot((1.0, 0.0, 0.0), look)))
    if (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) < 1e-8:
        v = (0.0, 0.0, 1.0)
    v = _norm(v)
    u = _norm(_cross(v, look))
    if u is None or v is None:
        return None
    v = _norm(_cross(look, u))
    u = _norm(_cross(v, look))
    return look, u, v


def _frente_placa(ancla, look, u_axis, v_axis, scale: float):
    """Caja UV de la piel frontal (sin retornos ni cantos). Origen = centro de esa piel."""
    occ = ancla.get("occ")
    doc = ancla.get("doc")
    if occ is None or doc is None:
        return None
    try:
        raw = tessellate_part(doc, 0.03)
        mat = _mat4(occ)
    except Exception:
        return None
    if not raw or mat is None:
        return None
    verts = [_xform_pt(mat, *p) for p in raw["verts"]]
    if len(verts) < 3:
        return None
    seed = (
        sum(p[0] for p in verts) / len(verts),
        sum(p[1] for p in verts) / len(verts),
        sum(p[2] for p in verts) / len(verts),
    )
    ds = [_dot(_sub(p, seed), look) for p in verts]
    bin_cm = 0.20
    cuentas: dict[int, int] = {}
    for d in ds:
        key = int(round(float(d) / bin_cm))
        cuentas[key] = cuentas.get(key, 0) + 1
    minimo = max(8, int(len(ds) * 0.10))
    candidatos = [k for k, n in cuentas.items() if n >= minimo] or list(cuentas)
    d_cara = max(candidatos) * bin_cm
    piel = [p for p, d in zip(verts, ds) if abs(d - d_cara) <= bin_cm * 2.2]
    if len(piel) < 3:
        piel = verts
    origin = (
        sum(p[0] for p in piel) / len(piel),
        sum(p[1] for p in piel) / len(piel),
        sum(p[2] for p in piel) / len(piel),
    )
    us, vs = [], []
    for p in piel:
        uu, vv, _d = _proy_mesh(p, origin, u_axis, v_axis, look, scale)
        us.append(uu)
        vs.append(vv)
    if len(us) < 3:
        return None
    ox, oy = min(us), min(vs)
    return origin, ox, oy, max(us) - ox, max(vs) - oy


def _limpiar_cara_frontal(img, px, span_u: float, span_v: float) -> None:
    """Borra cantos/retornos fuera de la piel frontal. Deja el recuadro de la cara."""
    draw = ImageDraw.Draw(img)
    a = px(0.0, 0.0)
    b = px(span_u, span_v)
    x0, x1 = min(a[0], b[0]), max(a[0], b[0])
    y0, y1 = min(a[1], b[1]), max(a[1], b[1])
    w, h = img.size
    banda = 6
    draw.rectangle((0, 0, w, max(0, int(y0) + banda)), fill=(255, 255, 255))
    draw.rectangle((0, min(h, int(y1) - banda), w, h), fill=(255, 255, 255))
    draw.rectangle((0, 0, max(0, int(x0) + banda), h), fill=(255, 255, 255))
    draw.rectangle((min(w, int(x1) - banda), 0, w, h), fill=(255, 255, 255))
    ink = (28, 36, 44)
    draw.rectangle((x0, y0, x1, y1), outline=ink, width=2)


def _uv_ancla(ancla, origin, u_axis, v_axis, look, scale: float):
    occ = ancla.get("occ")
    doc = ancla.get("doc")
    if occ is None or doc is None or origin is None:
        return None
    try:
        raw = tessellate_part(doc, 0.03)
        mat = _mat4(occ)
    except Exception:
        return None
    if not raw or mat is None:
        return None
    us, vs = [], []
    for p in raw["verts"]:
        w = _xform_pt(mat, *p)
        uu, vv, _d = _proy_mesh(w, origin, u_axis, v_axis, look, scale)
        us.append(uu)
        vs.append(vv)
    if len(us) < 3:
        return None
    ox, oy = min(us), min(vs)
    return ox, oy, max(us) - ox, max(vs) - oy


def _px_imagen(img, crop):
    u0, v0, u1, v1 = crop
    w, h = img.size
    su = max(u1 - u0, 1e-6)
    sv = max(v1 - v0, 1e-6)

    def px0(x: float, y: float) -> tuple[float, float]:
        return (float(x) / su * (w - 1), (sv - float(y)) / sv * (h - 1))

    return px0


def _crop_mesh(mesh, origin, u_axis, v_axis, look, scale, ox, oy, span_u, span_v):
    margen = 0.45
    return (ox - margen, oy - margen, ox + span_u + margen, oy + span_v + margen)


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _scale(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def _escribir_camara(dest_cara: Path, **data) -> None:
    payload = {}
    for key, value in data.items():
        if isinstance(value, tuple):
            payload[key] = [round(float(x), 6) for x in value]
        else:
            payload[key] = value
    try:
        (dest_cara / "_camara.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass


def _control_referencia() -> dict:
    path = CONTROL_DIR / "control.json"
    if not path.is_file():
        return {"vista": "alambrico", "arriba_mundo": list(ARRIBA_MUNDO), "origen": "IL"}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {"vista": "alambrico", "arriba_mundo": list(ARRIBA_MUNDO), "origen": "IL"}
    if not isinstance(data, dict):
        return {"vista": "alambrico", "arriba_mundo": list(ARRIBA_MUNDO), "origen": "IL"}
    if str(data.get("fase") or "").lower() == "cerrada" or not bool(data.get("local_debug")):
        data["solo_vista"] = False
        data["local_debug"] = False
    return data


def _patrones(faces_cfg) -> dict[str, list[str]]:
    raw = faces_cfg if isinstance(faces_cfg, dict) else {}
    out = {}
    for cara in ORDEN_CARAS:
        seen: list[str] = []
        for v in list(DEFAULT_FACES.get(cara) or []) + list(raw.get(cara) or []):
            item = str(v).strip()
            if item and item not in seen:
                seen.append(item)
        out[cara] = seen or [cara.lower()]
    return out


def _cara_de(nombre: str, patterns: dict[str, list[str]]) -> tuple[str, int]:
    texto = _clave(nombre)
    mejor, score = "", 0
    for cara, pats in patterns.items():
        local = 0
        for pat in pats:
            clave = _clave(pat)
            if clave and _token_en(texto, clave):
                pts = len(clave)
                if clave in {"s1", "s2", "s3", "s4", "base"} and texto == clave:
                    pts += 50
                local = max(local, pts)
        if local > score:
            mejor, score = cara, local
    return mejor, score


def _token_en(texto: str, clave: str) -> bool:
    if not clave:
        return False
    if re.search(rf"(^| ){re.escape(clave)}( |$)", texto):
        return True
    return len(clave) >= 4 and clave in texto


def _clave(nombre: str) -> str:
    texto = Path(str(nombre or "")).stem
    return re.sub(r"[\s_\-#]+", " ", texto.casefold()).strip()


def _contar_hijos(doc) -> int:
    try:
        return int(doc.ComponentDefinition.Occurrences.Count)
    except Exception:
        return 0


def _hijos_cara(asm_doc) -> list[dict]:
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
            nombre = Path(_name(doc)).stem or str(occ.Name).split(":")[0]
            if _RE_HOLE.search(nombre):
                continue
            if _RE_HW.search(nombre) and not _RE_CIRC.search(nombre):
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
                    "clas": str(_classification(doc) or "").strip(),
                }
            )
        except Exception:
            continue
    return hijos


def _collect_ipt_caras(assembly, patterns) -> list[tuple]:
    best: dict[str, tuple] = {}
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
            if int(occ.DefinitionDocumentType) != TIPO_IPT:
                continue
            doc = occ.Definition.Document
            cara, score = _cara_de(_name(doc), patterns)
            if not cara:
                continue
            rb = occ.RangeBox
            area = abs(float(rb.MaxPoint.X) - float(rb.MinPoint.X))
            area *= abs(float(rb.MaxPoint.Y) - float(rb.MinPoint.Y))
        except Exception:
            continue
        prev = best.get(cara)
        if prev is None or score > prev[0] or (score == prev[0] and area > prev[1]):
            best[cara] = (score, area, occ, doc)
    return [(cara, assembly, 1, best[cara][2]) for cara in ORDEN_CARAS if cara in best]


def _hijos_hoja(asm_doc) -> list[dict]:
    hijos = []
    try:
        occs = asm_doc.ComponentDefinition.Occurrences.AllLeafOccurrences
        total = int(occs.Count)
    except Exception:
        return hijos
    vistos: dict[str, int] = {}
    for index in range(1, total + 1):
        try:
            occ = occs.Item(index)
            if bool(occ.Suppressed):
                continue
            if int(occ.DefinitionDocumentType) != TIPO_IPT:
                continue
            rb = occ.RangeBox
            doc = occ.Definition.Document
            nombre = Path(_name(doc)).stem or str(occ.Name).split(":")[0]
            if _RE_HOLE.search(nombre):
                continue
            if _RE_HW.search(nombre) and not _RE_CIRC.search(nombre):
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
                    "clas": str(_classification(doc) or "").strip(),
                }
            )
        except Exception:
            continue
    return hijos


def _ancla_de_occ(hijos: list[dict], occ) -> dict | None:
    try:
        nombre = str(occ.Name)
        path = str(occ.Definition.Document.FullFileName or "").replace("\\", "/").lower()
    except Exception:
        return None
    for hijo in hijos:
        try:
            if str(hijo.get("occ").Name) == nombre:
                return hijo
        except Exception:
            continue
    for hijo in hijos:
        try:
            other = str(hijo.get("doc").FullFileName or "").replace("\\", "/").lower()
        except Exception:
            continue
        if other == path:
            return hijo
    return None


def _miembros_bolsa(cara: str, assy=None) -> list[dict]:
    try:
        from roles_inventor import filas_desde_sesion, last_bags
    except Exception:
        return []
    bags = last_bags()
    if not bags.get(cara) and assy is not None:
        try:
            filas_desde_sesion(assy)
            bags = last_bags()
        except Exception:
            pass
    return list(bags.get(cara) or [])


def _hijos_de_bolsa(asm_doc, bolsa: list[dict], cara: str = "") -> list[dict]:
    """Placa de esta cara + accesorios cuyo centro cae en esta placa de las 6, no en un lateral."""
    bags = {}
    try:
        from roles_inventor import last_bags

        bags = last_bags() or {}
    except Exception:
        bags = {}
    if cara and cara not in bags and bolsa:
        bags = {**bags, cara: bolsa}
    miembros_cara = bags.get(cara) or bolsa or []
    nombres_cara = {str(m.get("nombre_ocurrencia") or "") for m in miembros_cara if m}
    placa_nombres = {str(m.get("nombre_ocurrencia") or "") for m in miembros_cara if m.get("placa_rol")}
    placa_rutas = {
        str(m.get("ruta_archivo") or "").replace("\\", "/").lower()
        for m in miembros_cara
        if m.get("placa_rol")
    }
    rutas_cara = {
        str(m.get("ruta_archivo") or "").replace("\\", "/").lower()
        for m in miembros_cara
        if m.get("ruta_archivo") and not m.get("placa_rol")
    }
    anclas = _anclas_planos(asm_doc, bags)
    hijos = []
    try:
        occs = asm_doc.ComponentDefinition.Occurrences.AllLeafOccurrences
        total = int(occs.Count)
    except Exception:
        return hijos
    for index in range(1, total + 1):
        try:
            occ = occs.Item(index)
            if bool(occ.Suppressed):
                continue
            nombre = str(occ.Name)
            path = str(occ.Definition.Document.FullFileName or "").replace("\\", "/").lower()
        except Exception:
            continue
        es_placa = nombre in placa_nombres or path in placa_rutas
        en_esta = nombre in nombres_cara
        mismo_ipt = path in rutas_cara
        if not es_placa and not en_esta and not mismo_ipt:
            continue
        try:
            rb = occ.RangeBox
            doc = occ.Definition.Document
            stem = Path(_name(doc)).stem or nombre.split(":")[0]
        except Exception:
            continue
        if es_placa or _es_placa_nombre(stem, nombre):
            if not es_placa:
                continue
        elif anclas and _muro_de_occ(occ, anclas) != str(cara).upper():
            continue
        centro = _centro_occ(occ)
        marca = ""
        if centro is not None:
            marca = f"@{centro[0]:.2f}_{centro[1]:.2f}_{centro[2]:.2f}"
        hijos.append(
            {
                "name": stem,
                "pieza_id": nombre.replace(":", "_") + marca,
                "occ": occ,
                "doc": doc,
                "rb": rb,
                "es_hw": bool(_RE_HW.search(stem)),
                "clas": str(_classification(doc) or "").strip(),
                "placa_rol": es_placa,
                "elegido": bool(en_esta or es_placa),
            }
        )
    return hijos


def _es_placa_nombre(stem: str, nombre: str) -> bool:
    try:
        from roles_muros import es_placa_muro
    except Exception:
        es_placa_muro = None
    if es_placa_muro:
        return bool(es_placa_muro(stem) or es_placa_muro(nombre))
    otra, _score = _cara_de(stem, _patrones(None))
    return bool(otra)


def _centros_ancla(asm_doc, bags: dict) -> dict[str, tuple]:
    centros: dict[str, tuple] = {}
    for cara, miembros in (bags or {}).items():
        for m in miembros or []:
            if not m.get("placa_rol"):
                continue
            occ = m.get("occ")
            c = _centro_occ(occ) if occ is not None else None
            if c is not None:
                centros[str(cara).upper()] = c
                break
    faltan = [c for c in ORDEN_CARAS if c not in centros]
    if not faltan:
        return centros
    try:
        occs = asm_doc.ComponentDefinition.Occurrences.AllLeafOccurrences
        total = int(occs.Count)
    except Exception:
        return centros
    patterns = _patrones(None)
    for index in range(1, total + 1):
        try:
            occ = occs.Item(index)
            if bool(occ.Suppressed):
                continue
            cara, _score = _cara_de(_name(occ.Definition.Document), patterns)
        except Exception:
            continue
        if not cara or cara in centros:
            continue
        c = _centro_occ(occ)
        if c is not None:
            centros[cara] = c
    return centros


def _anclas_planos(asm_doc, bags: dict) -> dict[str, dict]:
    """Centro, normal afuera y rectángulo UV de cada placa de muro."""
    tank = _centro_doc(asm_doc)
    out: dict[str, dict] = {}
    for cara, miembros in (bags or {}).items():
        for m in miembros or []:
            if not m.get("placa_rol"):
                continue
            occ = m.get("occ")
            geo = _geo_ancla_occ(occ, tank)
            if geo:
                out[str(cara).upper()] = geo
                break
    faltan = [c for c in ORDEN_CARAS if c not in out]
    if not faltan:
        return out
    centros = _centros_ancla(asm_doc, bags)
    patterns = _patrones(None)
    try:
        occs = asm_doc.ComponentDefinition.Occurrences.AllLeafOccurrences
        total = int(occs.Count)
    except Exception:
        return out
    for index in range(1, total + 1):
        try:
            occ = occs.Item(index)
            if bool(occ.Suppressed):
                continue
            cara, _score = _cara_de(_name(occ.Definition.Document), patterns)
        except Exception:
            continue
        if not cara or cara in out:
            continue
        geo = _geo_ancla_occ(occ, tank)
        if geo is None and cara in centros:
            c = centros[cara]
            n = _norm(_sub(c, tank)) if tank is not None else None
            if n is not None:
                geo = {"c": c, "n": n}
        if geo:
            out[cara] = geo
    return out


def _geo_ancla_occ(occ, tank_c) -> dict | None:
    c = _centro_occ(occ)
    if c is None:
        return None
    n = _norm(_sub(c, tank_c)) if tank_c is not None else None
    if n is None or (n[0] * n[0] + n[1] * n[1] + n[2] * n[2]) < 0.5:
        return {"c": c, "n": n or (0.0, 0.0, 1.0)}
    v = _sub(ARRIBA_MUNDO, _scale(n, _dot(ARRIBA_MUNDO, n)))
    if (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) < 1e-8:
        v = _sub((1.0, 0.0, 0.0), _scale(n, _dot((1.0, 0.0, 0.0), n)))
    v = _norm(v)
    u = _norm(_cross(v, n))
    try:
        rb = occ.RangeBox
        corners = [
            (float(x), float(y), float(z))
            for x in (rb.MinPoint.X, rb.MaxPoint.X)
            for y in (rb.MinPoint.Y, rb.MaxPoint.Y)
            for z in (rb.MinPoint.Z, rb.MaxPoint.Z)
        ]
    except Exception:
        return {"c": c, "n": n}
    us = [_dot(_sub(p, c), u) for p in corners]
    vs = [_dot(_sub(p, c), v) for p in corners]
    return {
        "c": c,
        "n": n,
        "u": u,
        "v": v,
        "umin": min(us),
        "umax": max(us),
        "vmin": min(vs),
        "vmax": max(vs),
    }


def _muro_de_occ(occ, anclas: dict[str, dict]) -> str:
    c = _centro_occ(occ)
    if c is None or not anclas:
        return ""
    return _muro_de_punto(c, anclas)


def _muro_de_punto(c, anclas: dict[str, dict]) -> str:
    mejor, mejor_s = "", None
    for cara, a in (anclas or {}).items():
        ac = a.get("c")
        n = a.get("n")
        if ac is None or n is None:
            continue
        d = abs(_dot(_sub(c, ac), n))
        penal = 0.0
        if a.get("u") is not None and "umin" in a:
            uu = _dot(_sub(c, ac), a["u"])
            vv = _dot(_sub(c, ac), a["v"])
            du = max(0.0, a["umin"] - uu, uu - a["umax"])
            dv = max(0.0, a["vmin"] - vv, vv - a["vmax"])
            penal = (du + dv) * 3.0
        s = d + penal
        if mejor_s is None or s < mejor_s:
            mejor, mejor_s = str(cara).upper(), s
    return mejor


def _filtrar_lado_placa(hijos: list[dict], origin, look, scale: float, cara: str = "") -> list[dict]:
    """Solo piezas de este muro: delante/sobre la placa, no laterales ni el par."""
    out = []
    for hijo in hijos or []:
        if hijo.get("placa_rol"):
            out.append(hijo)
            continue
        if not _mismo_lado_placa(hijo, origin, look, scale):
            continue
        out.append(hijo)
    return out


def _mismo_lado_placa(hijo: dict, origin, look, scale: float) -> bool:
    c = _centro_occ(hijo.get("occ"))
    if c is None or origin is None or look is None:
        return False
    d_in = _dot((c[0] - origin[0], c[1] - origin[1], c[2] - origin[2]), look) * float(scale or 0.3937)
    # look apunta afuera: el muro par queda a d negativo (dentro del tanque).
    return d_in >= -12.0


def _del_este_lado(occ, cara: str, centros: dict[str, tuple]) -> bool:
    """True si está más cerca de esta placa que de la opuesta (S1 vs S3, no vs laterales)."""
    c = _centro_occ(occ)
    ac = centros.get(str(cara).upper())
    if c is None or ac is None:
        return True
    d_esta = (c[0] - ac[0]) ** 2 + (c[1] - ac[1]) ** 2 + (c[2] - ac[2]) ** 2
    opp = PAR_CARA.get(str(cara).upper())
    ao = centros.get(opp) if opp else None
    if ao is None:
        return True
    d_otra = (c[0] - ao[0]) ** 2 + (c[1] - ao[1]) ** 2 + (c[2] - ao[2]) ** 2
    return d_esta <= d_otra


def _es_otra_placa(hijo: dict, cara: str) -> bool:
    otra, _score = _cara_de(hijo.get("name") or "", _patrones(None))
    return bool(otra) and otra != cara


def _sobre_placa(hijo, origin, look, scale, ox, oy, span_u, span_v, xs, ys) -> bool:
    if max(xs) < -1 or min(xs) > span_u + 1 or max(ys) < -1 or min(ys) > span_v + 1:
        return False
    wu = max(xs) - min(xs)
    hv = max(ys) - min(ys)
    # Canto de un muro vecino: caja fina pegada al borde (p.ej. flange de S1 visto en S4).
    if wu < 2.2 and (max(xs) < 1.4 or min(xs) > span_u - 1.4):
        return False
    if hv < 2.2 and (max(ys) < 1.4 or min(ys) > span_v - 1.4):
        return False
    c = _centro_occ(hijo.get("occ"))
    if c is None or origin is None:
        return True
    depth = abs(_dot((c[0] - origin[0], c[1] - origin[1], c[2] - origin[2]), look)) * scale
    return depth <= max(10.0, 0.15 * max(span_u, span_v))


def _tipo(nombre: str) -> str:
    stem = Path(str(nombre or "TIPO")).stem.strip() or "TIPO"
    return re.sub(r"_\d+$", "", stem)


def _es_circular(hijo: dict, xs: list[float], ys: list[float]) -> bool:
    nom = str(hijo.get("name") or "")
    if re.search(r"(patch|placa|solera|plate|aisc|marco|cuadro|jacking|lug|parking)", nom, re.I):
        return False
    if _RE_CIRC.search(nom):
        return True
    wu = max(xs) - min(xs)
    hv = max(ys) - min(ys)
    if min(wu, hv) < 0.25 or max(wu, hv) > 10.0:
        return False
    return abs(wu - hv) / max(wu, hv, 1e-6) < 0.15


def _misma_cota(pieza: dict, kind: str, valor: float) -> bool:
    eje = "x" if kind.startswith("X") else "y"
    circ = "CENTRO" in kind
    if bool(pieza.get("circ")) != circ:
        return False
    return abs(float(pieza[eje]) - float(valor)) <= TOL * 1.5


def _id_pieza(pieza: dict, fallback: int = 0) -> str:
    return str(pieza.get("name") or "") + f"@{pieza.get('cx', fallback):.3f},{pieza.get('cy', 0):.3f}"


def _fmt_val(valor: float) -> str:
    v = abs(float(valor))
    if abs(v - round(v)) < 0.001:
        return str(int(round(v)))
    return f"{v:.3f}".rstrip("0").rstrip(".")


def _safe(name: str) -> str:
    cleaned = str(name or "TIPO").translate(str.maketrans('<>:"/\\|?*', "_________")).strip().rstrip(". ")
    return cleaned or "TIPO"


def _archivo(job: str, item: str, marca: str) -> str:
    base = f"{job}__{item}__{marca}"
    for ch in '<>:"/\\|?*':
        base = base.replace(ch, "_")
    return f"{base}.jpg"
