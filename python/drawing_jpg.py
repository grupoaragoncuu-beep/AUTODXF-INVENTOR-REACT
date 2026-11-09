"""JPG de acotación por coordenadas: origen (0,0), X/Y absolutos, Ø en el hueco."""

from __future__ import annotations

import math
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_LADO = 980
_AZUL = "#1A5276"
_TEXTO = "#1B2631"
_TESTIGO = "#5D6D7E"
_TRAZO = "#1C2833"
_RELLENO = "#FFFFFF"
_BEND = "#C9A000"


def plan_focuses(measures: dict[str, float], holes: list[dict], wanted: set[str], prueba: bool) -> list[tuple[str, str, float, bool]]:
    _ = holes, wanted, prueba
    return [("FULL", "FULL", _num(measures.get("LENGTH"), 1), False)]


def _agrupar(valores: list[float], tol: float = 0.4) -> list[float]:
    grupos: list[tuple[float, int]] = []
    for valor in sorted(float(v) for v in valores):
        if grupos and abs(grupos[-1][0] - valor) <= tol:
            promedio, cuenta = grupos[-1]
            cuenta += 1
            grupos[-1] = ((promedio * (cuenta - 1) + valor) / cuenta, cuenta)
        else:
            grupos.append((valor, 1))
    return [item[0] for item in grupos]


def save_part_drawing(
    dest: str | Path,
    outline: list[tuple[float, float]],
    holes: list[dict],
    *,
    title: str,
    subtitle: str,
    unit: str,
    measures: dict[str, float],
    highlight: str = "FULL",
    focus_value: float | None = None,
    typ: bool = False,
    hole_anchor: str = "center",
    measure_walls: bool = True,
    focus: dict | None = None,
    landscape: bool = True,
) -> str:
    _ = highlight, focus_value, typ
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    largo = _num(measures.get("LENGTH"), 100.0)
    ancho = _num(measures.get("WIDTH"), 60.0)
    thk = _num(measures.get("THK"), 0.0)
    poly = _clean_poly(outline, largo, ancho)
    if landscape:
        largo, ancho, holes, poly = _landscape(largo, ancho, holes, poly)
    feats = _normalize(holes)
    _render_coord(
        dest,
        largo,
        ancho,
        thk,
        unit,
        feats,
        title,
        subtitle,
        poly,
        hole_anchor=hole_anchor,
        measure_walls=measure_walls,
        focus=focus,
    )
    return str(dest)


def list_face_cotas(
    outline: list,
    holes: list[dict],
    measures: dict[str, float],
    hole_anchor: str = "edge",
    measure_walls: bool = False,
    landscape: bool = True,
) -> list[dict]:
    """Una entrada por coincidencia X/Y, Ø, y largo/ancho de cada rectángulo o slot."""
    largo = _num(measures.get("LENGTH"), 100.0)
    ancho = _num(measures.get("WIDTH"), 60.0)
    poly = _clean_poly(outline, largo, ancho)
    if landscape:
        largo, ancho, holes, poly = _landscape(largo, ancho, holes, poly)
    feats = _normalize(holes)
    cotas_x = _cotas_orillas(_marcas_info(feats, "x", hole_anchor), "x")
    cotas_y = _cotas_orillas(_marcas_info(feats, "y", hole_anchor), "y")
    rows: list[dict] = []
    for item in cotas_x:
        if abs(item["value"]) < 0.2 or (measure_walls and abs(item["value"] - largo) < 0.4):
            continue
        rows.append(_fila_eje("X", item))
    for item in cotas_y:
        if abs(item["value"]) < 0.2 or (measure_walls and abs(item["value"] - ancho) < 0.4):
            continue
        rows.append(_fila_eje("Y", item))
    vistos: set[tuple] = set()
    for feat in feats:
        if feat["kind"] == "circle":
            key = ("HOLE", round(feat["dia"], 2))
            if key in vistos:
                continue
            vistos.add(key)
            rows.append({"kind": "HOLE", "value": feat["dia"], "name": f"HOLE_{_fmt(feat['dia'])}"})
        elif feat["kind"] == "slot":
            key = ("SLOT", round(feat["cut_length"], 2), round(feat["cut_width"], 2))
            if key in vistos:
                continue
            vistos.add(key)
            rows.extend(_filas_rasgo("SLOT", feat))
        elif feat["kind"] == "cut":
            if feat.get("acota") is False or _cut_envuelve_cadena(feat, feats):
                continue
            key = ("CUT", round(feat["cut_length"], 2), round(feat["cut_width"], 2))
            if key in vistos:
                continue
            vistos.add(key)
            rows.extend(_filas_rasgo("CUT", feat))
    if largo > 0.2:
        rows.append({"kind": "LENGTH", "value": largo, "name": f"LENGTH_{_fmt(largo)}"})
    return _nombres_unicos(rows)


def _clean_poly(outline, largo: float, ancho: float) -> list[tuple[float, float]]:
    pts = []
    for item in outline or []:
        if not isinstance(item, (tuple, list)) or len(item) < 2:
            continue
        x, y = _num(item[0], 0), _num(item[1], 0)
        if math.isfinite(x) and math.isfinite(y):
            pts.append((x, y))
    if len(pts) >= 3:
        return pts
    return [(0.0, 0.0), (largo, 0.0), (largo, ancho), (0.0, ancho)]


def _landscape(largo: float, ancho: float, holes: list[dict], poly: list[tuple[float, float]]):
    if ancho <= largo:
        return largo, ancho, holes, poly
    rotated = []
    for item in holes or []:
        out = dict(item)
        if "x" in out and "y" in out:
            out["x"], out["y"] = float(out["y"]), largo - float(out["x"])
        for a, b in (("x0", "y0"), ("x1", "y1")):
            if a in out and b in out:
                out[a], out[b] = float(out[b]), largo - float(out[a])
        if out.get("pts"):
            out["pts"] = [(float(p[1]), largo - float(p[0])) for p in out["pts"]]
        rotated.append(out)
    poly = [(p[1], largo - p[0]) for p in poly]
    return ancho, largo, rotated, poly


def _normalize(holes: list[dict]) -> list[dict]:
    rows = []
    for raw in holes or []:
        kind = str(raw.get("kind") or "circle")
        if kind == "bend":
            rows.append(
                {
                    "kind": "bend",
                    "x0": _num(raw.get("x0"), 0),
                    "y0": _num(raw.get("y0"), 0),
                    "x1": _num(raw.get("x1"), 0),
                    "y1": _num(raw.get("y1"), 0),
                }
            )
            continue
        if kind == "cut":
            pts = []
            for item in raw.get("pts") or []:
                if not isinstance(item, (tuple, list)) or len(item) < 2:
                    continue
                pts.append((_num(item[0], 0), _num(item[1], 0)))
            if len(pts) < 3:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            rows.append(
                {
                    "kind": "cut",
                    "pts": pts,
                    "xmin": min(xs),
                    "xmax": max(xs),
                    "ymin": min(ys),
                    "ymax": max(ys),
                    "cx": (min(xs) + max(xs)) / 2,
                    "cy": (min(ys) + max(ys)) / 2,
                    "cut_length": max(xs) - min(xs),
                    "cut_width": max(ys) - min(ys),
                    "acota": bool(raw.get("acota", True)),
                    "focus": raw.get("focus"),
                    "typ": str(raw.get("typ") or ""),
                }
            )
            continue
        if kind == "slot":
            x0, y0 = _num(raw.get("x0"), 0), _num(raw.get("y0"), 0)
            x1, y1 = _num(raw.get("x1"), 0), _num(raw.get("y1"), 0)
            dia = abs(_num(raw.get("dia"), 0))
            if dia <= 0:
                continue
            dist = math.hypot(x1 - x0, y1 - y0)
            rows.append(
                {
                    "kind": "slot",
                    "x0": x0,
                    "y0": y0,
                    "x1": x1,
                    "y1": y1,
                    "dia": dia,
                    "cx": (x0 + x1) / 2,
                    "cy": (y0 + y1) / 2,
                    "cut_length": dist + dia,
                    "cut_width": dia,
                }
            )
            continue
        if kind in {"circle", "arc"}:
            cx, cy = _num(raw.get("x"), 0), _num(raw.get("y"), 0)
            dia = abs(_num(raw.get("dia"), 0))
            if dia <= 0:
                continue
            rows.append(
                {
                    "kind": "circle",
                    "cx": cx,
                    "cy": cy,
                    "dia": dia,
                    "focus": raw.get("focus"),
                    "typ": str(raw.get("typ") or ""),
                }
            )
    return rows


def _num(value, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float(fallback or 0)
    if not math.isfinite(number) or abs(number) > 1e6:
        return float(fallback or 0)
    return number


def _fmt(valor: float) -> str:
    return f"{abs(float(valor)):.2f}"


def _letra(indice: int) -> str:
    n = indice + 1
    texto = ""
    while n:
        n, r = divmod(n - 1, 26)
        texto = chr(65 + r) + texto
    return texto


def _con_typ(cuerpo: str, n: int, unit: str) -> str:
    if n > 1:
        return f"{cuerpo} TYP {unit}"
    return f"{cuerpo} {unit}"


# Texto de la cota (el número) en Corte, Doblado, Maquinado y referencia.
# 2.5 veces la base: 13 px → 32, 18 px → 45, 28 px → 70.
ESCALA_FUENTE_COTA = 2.5


def _font(size: int, bold: bool = False):
    name = "arialbd.ttf" if bold else "arial.ttf"
    path = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", name)
    if os.path.isfile(path):
        return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _px_cota(size: int) -> int:
    return max(1, int(round(size * ESCALA_FUENTE_COTA)))


def _font_cota(size: int, bold: bool = False):
    return _font(_px_cota(size), bold)


def _measure(draw: ImageDraw.ImageDraw, font, text: str) -> tuple[float, float]:
    box = draw.textbbox((0, 0), text, font=font)
    return float(box[2] - box[0]), float(box[3] - box[1])


class _Marco:
    def __init__(self, largo, ancho, izq, arriba):
        self.escala = _LADO / max(largo, ancho, 1e-6)
        self.izq = izq
        self.arriba = arriba
        self.largo = largo
        self.ancho = ancho
        self.sx0 = izq
        self.sy0 = arriba
        self.sx1 = izq + largo * self.escala
        self.sy1 = arriba + ancho * self.escala

    def px(self, x: float, y: float) -> tuple[float, float]:
        return (self.izq + x * self.escala, self.arriba + (self.ancho - y) * self.escala)


def _render_coord(
    dest: Path,
    largo,
    ancho,
    thk,
    unit,
    feats,
    title,
    subtitle,
    poly=None,
    hole_anchor: str = "center",
    measure_walls: bool = True,
    focus: dict | None = None,
) -> None:
    unit = str(unit or "mm").strip() or "mm"
    indice = 0
    focus = focus if isinstance(focus, dict) else None
    focus_kind = str((focus or {}).get("kind") or "").upper()
    focus_val = _num((focus or {}).get("value"), 0.0)
    focus_val2 = _num((focus or {}).get("value2"), 0.0)
    focus_size = (focus or {}).get("size")
    rasgo_feat = None
    rasgo_axis = ""
    rasgo_texto = ""
    cotas_x = _cotas_orillas(_marcas_info(feats, "x", hole_anchor), "x")
    cotas_y = _cotas_orillas(_marcas_info(feats, "y", hole_anchor), "y")
    if focus_kind == "X":
        cotas_x = [item for item in cotas_x if _misma_orilla(item, focus_val, focus_size)]
        cotas_y = []
    elif focus_kind == "Y":
        cotas_y = [item for item in cotas_y if _misma_orilla(item, focus_val, focus_size)]
        cotas_x = []
    if measure_walls:
        xs = _agrupar([0.0, largo] + [item["value"] for item in cotas_x])
        ys = _agrupar([0.0, ancho] + [item["value"] for item in cotas_y])
    else:
        xs = _agrupar([0.0] + [item["value"] for item in cotas_x])
        ys = _agrupar([0.0] + [item["value"] for item in cotas_y])
    etiqueta_x: dict[float, str] = {}
    etiqueta_y: dict[float, str] = {}
    focus_label = str((focus or {}).get("label") or "")
    for item in cotas_x:
        valor = item["value"]
        if abs(valor) < 0.2 or (measure_walls and abs(valor - largo) < 0.4):
            continue
        if valor in etiqueta_x:
            continue
        etiqueta_x[valor] = _con_typ(f"{_letra(indice)}={_fmt(valor)}", item["n"], unit)
        indice += 1
    for item in cotas_y:
        valor = item["value"]
        if abs(valor) < 0.2 or (measure_walls and abs(valor - ancho) < 0.4):
            continue
        if valor in etiqueta_y:
            continue
        etiqueta_y[valor] = _con_typ(f"{_letra(indice)}={_fmt(valor)}", item["n"], unit)
        indice += 1
    if focus_label and focus_kind == "X":
        etiqueta_x = {v: focus_label for v in etiqueta_x}
        for v in xs:
            if abs(v) >= 0.2:
                etiqueta_x[v] = focus_label
    if focus_label and focus_kind == "Y":
        etiqueta_y = {v: focus_label for v in etiqueta_y}
        for v in ys:
            if abs(v) >= 0.2:
                etiqueta_y[v] = focus_label

    callouts = []
    slots_ok: set[tuple[int, int]] = set()
    for feat in feats:
        if feat["kind"] != "slot":
            continue
        key = (int(round(feat["cut_length"] * 10)), int(round(feat["cut_width"] * 10)))
        if key in slots_ok:
            continue
        slots_ok.add(key)
        n = sum(
            1
            for other in feats
            if other["kind"] == "slot"
            and abs(other["cut_length"] - feat["cut_length"]) < 0.15
            and abs(other["cut_width"] - feat["cut_width"]) < 0.15
        )
        txt = _con_typ(f"{_letra(indice)}={_fmt(feat['cut_length'])}×{_fmt(feat['cut_width'])}", n, unit)
        indice += 1
        callouts.append((feat["cx"], feat["cy"], txt, feat["dia"] / 2))
    cuts_ok: set[tuple[int, int]] = set()
    for feat in feats:
        if feat["kind"] != "cut":
            continue
        key = (int(round(feat["cut_length"] * 10)), int(round(feat["cut_width"] * 10)))
        if key in cuts_ok:
            continue
        cuts_ok.add(key)
        n = sum(
            1
            for other in feats
            if other["kind"] == "cut"
            and abs(other["cut_length"] - feat["cut_length"]) < 0.15
            and abs(other["cut_width"] - feat["cut_width"]) < 0.15
        )
        txt = _con_typ(f"{_letra(indice)}={_fmt(feat['cut_length'])}×{_fmt(feat['cut_width'])}", n, unit)
        indice += 1
        radio = min(feat["cut_length"], feat["cut_width"]) / 2
        callouts.append((feat["cx"], feat["cy"], txt, radio))
    for dia in _agrupar([f["dia"] for f in feats if f["kind"] == "circle"], tol=0.02):
        hits = [f for f in feats if f["kind"] == "circle" and abs(f["dia"] - dia) <= 0.02]
        if not hits:
            continue
        txt = _con_typ(f"{_letra(indice)}=Ø{_fmt(dia)}", len(hits), unit)
        indice += 1
        callouts.append((hits[0]["cx"], hits[0]["cy"], txt, hits[0]["dia"] / 2))

    if focus_kind == "X":
        xs = [v for v in xs if abs(v) < 0.2 or abs(v - focus_val) <= 0.25]
        ys = [v for v in ys if abs(v) < 0.2]
        callouts = []
    elif focus_kind == "Y":
        ys = [v for v in ys if abs(v) < 0.2 or abs(v - focus_val) <= 0.25]
        xs = [v for v in xs if abs(v) < 0.2]
        callouts = []
    elif focus_kind == "HOLE":
        xs = [v for v in xs if abs(v) < 0.2]
        ys = [v for v in ys if abs(v) < 0.2]
        callouts = [row for row in callouts if "Ø" in row[2] and abs(row[3] * 2 - focus_val) <= 0.02]
    elif focus_kind in {"SLOT", "CUT"}:
        xs = [v for v in xs if abs(v) < 0.2]
        ys = [v for v in ys if abs(v) < 0.2]
        callouts = []
        rasgo_axis = str((focus or {}).get("axis") or "L").upper()
        if rasgo_axis not in {"L", "W"}:
            rasgo_axis = "L"
        rasgo_feat = next(
            (
                feat
                for feat in feats
                if _feat_en_foco(feat, focus_kind, focus_val, focus_val2, hole_anchor, focus_size)
            ),
            None,
        )
        mostrado = focus_val2 if rasgo_axis == "W" else focus_val
        n_rasgo = sum(
            1
            for feat in feats
            if _feat_en_foco(feat, focus_kind, focus_val, focus_val2, hole_anchor, focus_size)
        )
        rasgo_texto = _con_typ(
            f"{'WIDTH' if rasgo_axis == 'W' else 'LENGTH'}={_fmt(mostrado)}",
            max(n_rasgo, 1),
            unit,
        )
    elif focus_kind == "LENGTH":
        xs = _agrupar([0.0, largo])
        ys = [v for v in ys if abs(v) < 0.2]
        callouts = []
    elif focus_kind == "WIDTH":
        ys = _agrupar([0.0, ancho])
        xs = [v for v in xs if abs(v) < 0.2]
        callouts = []

    _ = title, subtitle
    num_font = _font_cota(13, False)
    # LENGTH / WIDTH / X / Y a orilla: 20 % más que el resto de las cotas.
    font_orilla = _font(max(1, int(round(_px_cota(13) * 1.2))), False)
    dummy = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    textos_x_all = []
    for valor in xs:
        if (measure_walls or focus_kind == "LENGTH") and abs(valor - largo) < 0.4:
            textos_x_all.append(f"LENGTH={_fmt(valor)} {unit}")
        elif abs(valor) < 0.2:
            textos_x_all.append("0.00")
        else:
            textos_x_all.append(etiqueta_x.get(valor, f"{_fmt(valor)} {unit}"))
    # El texto vertical ocupa el ancho del rótulo. +28 cubre el margen de la capa y separa filas.
    alto_etiq = max((_measure(dummy, font_orilla, t)[0] + 28) for t in (textos_x_all or ["0.00"]))
    grosor = max((_measure(dummy, font_orilla, t)[1] + 20) for t in (textos_x_all or ["0.00"]))
    textos_y = []
    for valor in ys:
        if (measure_walls or focus_kind == "WIDTH") and abs(valor - ancho) < 0.4:
            textos_y.append(f"WIDTH={_fmt(valor)} {unit}")
        elif abs(valor) < 0.2:
            textos_y.append("0.00")
        else:
            textos_y.append(etiqueta_y.get(valor, f"{_fmt(valor)} {unit}"))
    izq, der, arriba = 220, max(160, int(grosor) + 48), 96
    if textos_y:
        izq = max(izq, int(max(_measure(dummy, font_orilla, t)[0] for t in textos_y)) + 48)
    if callouts:
        medidas_call = [_measure(dummy, num_font, row[2]) for row in callouts]
        der = max(der, int(max(item[0] for item in medidas_call)) + 56)
        izq = max(izq, int(max(item[0] for item in medidas_call)) + 56)
        arriba = max(arriba, int(max(item[1] for item in medidas_call)) + 56)
    if rasgo_texto:
        tw_rasgo, _th_rasgo = _measure(dummy, font_orilla, rasgo_texto)
        ancho_px = float(largo) * (_LADO / max(float(largo), float(ancho), 1e-6))
        if tw_rasgo + 64 > ancho_px:
            falta = int(tw_rasgo + 64 - ancho_px)
            izq += falta // 2 + 8
            der += falta - falta // 2 + 8
    marco = _Marco(largo, ancho, izq, arriba)
    px_xs = [marco.px(v, 0)[0] for v in xs]
    # El rótulo vertical ocupa el alto de la letra. Si dos ticks caben en menos que eso, bajan de fila.
    filas_x = _filas_sin_solape(px_xs, max(36.0, float(grosor)))
    n_filas = max(filas_x) + 1 if filas_x else 1
    abajo = int(n_filas * alto_etiq + 40)
    width = int(marco.sx1 + der + 24)
    height = int(marco.sy1 + abajo + 48)
    img = Image.new("RGB", (max(width, 420), max(height, 280)), "#FFFFFF")
    draw = ImageDraw.Draw(img)

    _draw_poly(draw, marco, poly, largo, ancho)
    orden = {"bend": 0, "cut": 1, "slot": 2, "circle": 3}
    for feat in sorted(feats, key=lambda item: orden.get(item["kind"], 9)):
        if feat["kind"] == "bend":
            a, b = marco.px(feat["x0"], feat["y0"]), marco.px(feat["x1"], feat["y1"])
            _dash(draw, a, b, _BEND, 2)
        elif feat["kind"] == "circle":
            c = marco.px(feat["cx"], feat["cy"])
            r = feat["dia"] / 2 * marco.escala
            activa = _feat_en_foco(feat, focus_kind, focus_val, focus_val2, hole_anchor, focus_size)
            draw.ellipse(
                (c[0] - r, c[1] - r, c[0] + r, c[1] + r),
                outline="#1A5276" if activa else _TRAZO,
                fill="#D6EAF8" if activa else None,
                width=3 if activa else 2,
            )
            if str(hole_anchor).lower() != "edge":
                _cross(draw, c, r * 1.35)
        elif feat["kind"] == "slot":
            activa = _feat_en_foco(feat, focus_kind, focus_val, focus_val2, hole_anchor, focus_size)
            _stadium(draw, marco, feat, activo=activa)
            r = feat["dia"] / 2 * marco.escala
            if str(hole_anchor).lower() != "edge":
                _cross(draw, marco.px(feat["x0"], feat["y0"]), r * 1.2)
                _cross(draw, marco.px(feat["x1"], feat["y1"]), r * 1.2)
        elif feat["kind"] == "cut":
            pts = [marco.px(x, y) for x, y in feat["pts"]]
            if len(pts) >= 3:
                activa = _feat_en_foco(feat, focus_kind, focus_val, focus_val2, hole_anchor, focus_size)
                draw.polygon(pts, outline="#1A5276" if activa else _TRAZO, fill="#D6EAF8" if activa else "#F4F6F7")
    typ_font = _font_cota(15, True)
    for feat in feats:
        letra = str(feat.get("typ") or "")
        if not letra:
            continue
        c = marco.px(feat["cx"], feat["cy"])
        draw.text((c[0] - 5, c[1] - 8), letra, fill="#1A5276", font=typ_font)

    eje_y = marco.sx0 - 18
    eje_x = marco.sy1 + 18
    draw.line((eje_y, marco.sy0, eje_y, marco.sy1), fill=_TESTIGO, width=1)
    draw.line((marco.sx0, eje_x, marco.sx1, eje_x), fill=_TESTIGO, width=1)

    puestos: list[tuple[float, float, float, float]] = []
    fila_x = eje_x + 8
    for i, valor in enumerate(xs):
        px, _py = marco.px(valor, 0)
        hit = None if focus_kind == "LENGTH" else _primera_en_x(
            feats, valor, hole_anchor, size=_size_cota(cotas_x, valor, focus_size)
        )
        if hit is not None:
            hx, hy = marco.px(hit["cx"], hit["cy"])
            draw.line((hx, hy, px, hy), fill=_TESTIGO, width=1)
            draw.line((px, hy, px, eje_x + 6), fill=_TESTIGO, width=1)
        else:
            draw.line((px, marco.sy1, px, eje_x + 6), fill=_TESTIGO, width=1)
        texto = textos_x_all[i]
        y_txt = fila_x + filas_x[i] * alto_etiq
        if filas_x[i]:
            draw.line((px, eje_x + 6, px, y_txt), fill=_TESTIGO, width=1)
        box = _texto_vertical(img, [], px, y_txt, texto, font_orilla)
        puestos.append(box)

    for valor in ys:
        _px, py = marco.px(0, valor)
        hit = None if focus_kind == "WIDTH" else _primera_en_y(
            feats, valor, hole_anchor, size=_size_cota(cotas_y, valor, focus_size)
        )
        if hit is not None:
            hx, hy = marco.px(hit["cx"], hit["cy"])
            draw.line((hx, hy, eje_y - 6, hy), fill=_TESTIGO, width=1)
            py = hy
        else:
            draw.line((marco.sx0, py, eje_y - 6, py), fill=_TESTIGO, width=1)
        if (measure_walls or focus_kind == "WIDTH") and abs(valor - ancho) < 0.4:
            texto = f"WIDTH={_fmt(valor)} {unit}"
        elif abs(valor) < 0.2:
            texto = "0.00"
        else:
            texto = etiqueta_y.get(valor, f"{_fmt(valor)} {unit}")
        tw, th = _measure(draw, font_orilla, texto)
        ancla_x, ancla_y = eje_y - 6, py
        x_txt = max(2.0, ancla_x - tw)
        natural = (x_txt, ancla_y - th / 2, x_txt + tw, ancla_y + th / 2)
        box, movido = _bajar_si_empalma(natural, puestos, img.height, img.width)
        if movido:
            _diagonal(draw, (ancla_x, ancla_y), (box[2], (box[1] + box[3]) / 2))
        else:
            draw.line((box[2] + 1, py, ancla_x, py), fill=_TESTIGO, width=1)
        _texto(draw, box, texto, font_orilla)
        puestos.append(box)

    for cx, cy, texto, radio in callouts:
        _leader(draw, marco, cx, cy, radio, texto, num_font, puestos, img.size)

    if rasgo_feat is not None and rasgo_texto:
        _dibujar_medida_rasgo(draw, img, marco, rasgo_feat, rasgo_axis, rasgo_texto, font_orilla, puestos)

    if thk and not focus_kind:
        pie = f"THK={_fmt(thk)} {unit}"
        tw, tht = _measure(draw, num_font, pie)
        _texto(draw, ((img.width - tw) / 2, img.height - tht - 8, (img.width + tw) / 2, img.height - 8), pie, num_font)
    img.save(dest, "JPEG", quality=93, optimize=True)


def _feat_en_foco(feat: dict, kind: str, valor: float, valor2: float, hole_anchor: str, size=None) -> bool:
    if not kind:
        return False
    if kind in {"X", "Y"} and "focus" in feat and feat.get("focus") is not None:
        return bool(feat.get("focus"))
    if kind in {"X", "Y"}:
        if size and not _same_size(_tamano(feat), size):
            return False
        eje = "x" if kind == "X" else "y"
        return any(
            abs((mx if kind == "X" else my) - valor) <= 0.25
            for mx, my in _marcas([feat], eje, hole_anchor)
        )
    if kind == "HOLE":
        return feat.get("kind") == "circle" and abs(float(feat.get("dia") or 0) - valor) <= 0.02
    if kind == "SLOT":
        return (
            feat.get("kind") == "slot"
            and abs(float(feat.get("cut_length") or 0) - valor) <= 0.15
            and abs(float(feat.get("cut_width") or 0) - valor2) <= 0.15
        )
    if kind == "CUT":
        return (
            feat.get("kind") == "cut"
            and abs(float(feat.get("cut_length") or 0) - valor) <= 0.15
            and abs(float(feat.get("cut_width") or 0) - valor2) <= 0.15
        )
    return False


def _segmento_rasgo(feat: dict, axis: str) -> tuple[bool, float, float, float, float]:
    """Segmento del largo o del ancho. horizontal, x0, y0, x1, y1 en coordenadas de la pieza."""
    axis = str(axis or "L").upper()
    if feat.get("kind") == "slot":
        x0, y0 = float(feat["x0"]), float(feat["y0"])
        x1, y1 = float(feat["x1"]), float(feat["y1"])
        horizontal = abs(x1 - x0) >= abs(y1 - y0)
        radio = float(feat["dia"]) / 2
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if axis == "L":
            if horizontal:
                return True, min(x0, x1) - radio, cy, max(x0, x1) + radio, cy
            return False, cx, min(y0, y1) - radio, cx, max(y0, y1) + radio
        if horizontal:
            return False, cx, cy - radio, cx, cy + radio
        return True, cx - radio, cy, cx + radio, cy
    if axis == "W":
        x = (float(feat["xmin"]) + float(feat["xmax"])) / 2
        return False, x, float(feat["ymin"]), x, float(feat["ymax"])
    y = (float(feat["ymin"]) + float(feat["ymax"])) / 2
    return True, float(feat["xmin"]), y, float(feat["xmax"]), y


def _borde_px(marco: _Marco, feat: dict, horizontal: bool, p0, p1) -> tuple[float, float, float, float]:
    """Caja del hueco en pixeles: izquierda, derecha, arriba, abajo."""
    if feat.get("kind") == "cut":
        a = marco.px(float(feat["xmin"]), float(feat["ymin"]))
        b = marco.px(float(feat["xmax"]), float(feat["ymax"]))
        return min(a[0], b[0]), max(a[0], b[0]), min(a[1], b[1]), max(a[1], b[1])
    radio = float(feat.get("dia") or 0) / 2 * marco.escala
    if horizontal:
        return (
            min(p0[0], p1[0]),
            max(p0[0], p1[0]),
            min(p0[1], p1[1]) - radio,
            max(p0[1], p1[1]) + radio,
        )
    return (
        min(p0[0], p1[0]) - radio,
        max(p0[0], p1[0]) + radio,
        min(p0[1], p1[1]),
        max(p0[1], p1[1]),
    )


def _dibujar_medida_rasgo(draw, img, marco: _Marco, feat: dict, axis: str, texto: str, font, puestos: list) -> None:
    """Largo y ancho del corte, sobre el hueco. El texto no se sube al margen de la pieza."""
    horizontal, x0, y0, x1, y1 = _segmento_rasgo(feat, axis)
    p0 = marco.px(x0, y0)
    p1 = marco.px(x1, y1)
    borde_izq, borde_der, borde_arr, borde_aba = _borde_px(marco, feat, horizontal, p0, p1)
    tw, th = _measure(draw, font, texto)
    if horizontal:
        x_a, x_b = min(p0[0], p1[0]), max(p0[0], p1[0])
        y_dim = (min(p0[1], p1[1]) + max(p0[1], p1[1])) / 2
        draw.line((x_a, y_dim - 7, x_a, y_dim + 7), fill=_TRAZO, width=2)
        draw.line((x_b, y_dim - 7, x_b, y_dim + 7), fill=_TRAZO, width=2)
        draw.line((x_a, y_dim, x_b, y_dim), fill=_TESTIGO, width=1)
        tx = (x_a + x_b) / 2 - tw / 2
        ty = y_dim - th - 6
        ancla = ((x_a + x_b) / 2, y_dim)
    else:
        y_a, y_b = min(borde_arr, borde_aba), max(borde_arr, borde_aba)
        x_dim = borde_izq - 16
        x_ext = borde_izq
        if x_dim < 12:
            x_dim = borde_der + 16
            x_ext = borde_der
        draw.line((x_ext, y_a, x_dim, y_a), fill=_TESTIGO, width=1)
        draw.line((x_ext, y_b, x_dim, y_b), fill=_TESTIGO, width=1)
        draw.line((x_dim, y_a, x_dim, y_b), fill=_TESTIGO, width=1)
        draw.line((x_dim - 7, y_a, x_dim + 7, y_a), fill=_TRAZO, width=2)
        draw.line((x_dim - 7, y_b, x_dim + 7, y_b), fill=_TRAZO, width=2)
        tx = x_dim - tw - 8 if x_dim <= borde_izq else x_dim + 8
        ty = (y_a + y_b) / 2 - th / 2
        ancla = (x_dim, (y_a + y_b) / 2)
    box = _clamp_box((tx, ty, tx + tw, ty + th), img.width, img.height)
    box, movido = _bajar_si_empalma(box, puestos, img.height, img.width)
    box = _clamp_box(box, img.width, img.height)
    if movido:
        _diagonal(draw, ancla, ((box[0] + box[2]) / 2, box[1] if box[1] > ancla[1] else box[3]))
    _texto(draw, box, texto, font)
    puestos.append(box)


def _filas_sin_solape(posiciones: list[float], min_sep: float) -> list[int]:
    """Cada cota cercana baja a la siguiente fila; ninguna se omite."""
    filas: list[int] = []
    ultimo: dict[int, float] = {}
    for px in posiciones:
        fila = 0
        while True:
            prev = ultimo.get(fila)
            if prev is None or px - prev >= min_sep:
                ultimo[fila] = px
                filas.append(fila)
                break
            fila += 1
    return filas


def _marcas_x(feats: list[dict]) -> list[tuple[float, float]]:
    return _marcas(feats, "x", "center")


def _cut_envuelve_cadena(cut: dict, feats: list[dict]) -> bool:
    """No cotar un CUT que solo envuelve 3+ barrenos Ø iguales alineados (canal)."""
    if str(cut.get("kind") or "") != "cut":
        return False
    largo = max(float(cut.get("cut_length") or 0), float(cut.get("cut_width") or 0))
    ancho = min(float(cut.get("cut_length") or 0), float(cut.get("cut_width") or 0))
    if ancho < 0.2 or largo < ancho * 2.5:
        return False
    xmin, xmax = float(cut["xmin"]), float(cut["xmax"])
    ymin, ymax = float(cut["ymin"]), float(cut["ymax"])
    inside = [
        feat
        for feat in feats
        if feat.get("kind") == "circle"
        and xmin - 0.3 <= float(feat["cx"]) <= xmax + 0.3
        and ymin - 0.3 <= float(feat["cy"]) <= ymax + 0.3
    ]
    if len(inside) < 3:
        return False
    dia = float(inside[0]["dia"])
    if any(abs(float(feat["dia"]) - dia) > max(0.2, dia * 0.2) for feat in inside):
        return False
    xs = [float(feat["cx"]) for feat in inside]
    ys = [float(feat["cy"]) for feat in inside]
    return (max(xs) - min(xs) > dia * 2 and max(ys) - min(ys) < dia * 0.8) or (
        max(ys) - min(ys) > dia * 2 and max(xs) - min(xs) < dia * 0.8
    )


def _marcas(feats: list[dict], eje: str, anchor: str) -> list[tuple[float, float]]:
    return [(item["x"], item["y"]) for item in _marcas_info(feats, eje, anchor)]


def _marcas_info(feats: list[dict], eje: str, anchor: str) -> list[dict]:
    """BUSBAR: centros. Tank: orilla. Cada marca lleva el tamaño del hueco (TYP no mezcla Ø)."""
    pts = []
    edge = str(anchor or "center").lower() == "edge"
    for feat in feats:
        if feat.get("acota") is False or (feat.get("kind") == "cut" and _cut_envuelve_cadena(feat, feats)):
            continue
        size = _tamano(feat)
        if feat["kind"] == "slot":
            x0, y0 = float(feat["x0"]), float(feat["y0"])
            x1, y1 = float(feat["x1"]), float(feat["y1"])
            r = float(feat["dia"]) / 2
            if edge:
                mid_x, mid_y = (x0 + x1) / 2, (y0 + y1) / 2
                if eje == "x":
                    pares = ((min(x0, x1) - r, mid_y), (max(x0, x1) + r, mid_y))
                else:
                    pares = ((mid_x, min(y0, y1) - r), (mid_x, max(y0, y1) + r))
            else:
                pares = ((x0, y0), (x1, y1))
            for x, y in pares:
                pts.append({"x": x, "y": y, "size": size})
        elif feat["kind"] == "circle":
            cx, cy, r = float(feat["cx"]), float(feat["cy"]), float(feat["dia"]) / 2
            if edge:
                x, y = (cx - r, cy) if eje == "x" else (cx, cy - r)
            else:
                x, y = cx, cy
            pts.append({"x": x, "y": y, "size": size})
        elif feat["kind"] == "cut":
            xmin, xmax = float(feat["xmin"]), float(feat["xmax"])
            ymin, ymax = float(feat["ymin"]), float(feat["ymax"])
            cx, cy = float(feat["cx"]), float(feat["cy"])
            if edge:
                pares = ((xmin, cy), (xmax, cy)) if eje == "x" else ((cx, ymin), (cx, ymax))
            else:
                pares = ((cx, cy),)
            for x, y in pares:
                pts.append({"x": x, "y": y, "size": size})
    return pts


def _tamano(feat: dict) -> tuple:
    kind = str(feat.get("kind") or "")
    if kind == "circle":
        return ("circle", round(float(feat.get("dia") or 0), 2))
    if kind == "slot":
        return ("slot", round(float(feat.get("dia") or 0), 2), round(float(feat.get("cut_length") or 0), 2))
    if kind == "cut":
        return ("cut", round(float(feat.get("cut_length") or 0), 2), round(float(feat.get("cut_width") or 0), 2))
    return (kind, 0.0)


def _same_size(a, b) -> bool:
    if a is None or b is None:
        return True
    if not isinstance(a, (tuple, list)) or not isinstance(b, (tuple, list)):
        return a == b
    if len(a) != len(b) or a[0] != b[0]:
        return False
    for left, right in zip(a[1:], b[1:]):
        try:
            if abs(float(left) - float(right)) > 0.05:
                return False
        except (TypeError, ValueError):
            if left != right:
                return False
    return True


def _cotas_orillas(marcas: list[dict], eje: str) -> list[dict]:
    """Agrupa orillas solo entre huecos del mismo tamaño. TYP no mezcla diámetros."""
    familias: dict[tuple, list[float]] = {}
    for item in marcas:
        coord = float(item["x"] if eje == "x" else item["y"])
        familias.setdefault(item["size"], []).append(coord)
    rows: list[dict] = []
    for size, coords in familias.items():
        for valor in _agrupar(coords, tol=0.25):
            n = sum(1 for coord in coords if abs(coord - valor) <= 0.25)
            rows.append({"value": valor, "size": size, "n": n})
    rows.sort(key=lambda row: (row["value"], str(row["size"])))
    return rows


def _filas_rasgo(kind: str, feat: dict) -> list[dict]:
    """Rectángulo o slot: una cota de largo y otra de ancho. Sin L×W en la misma vista."""
    largo = float(feat["cut_length"])
    ancho = float(feat["cut_width"])
    return [
        {
            "kind": kind,
            "axis": "L",
            "value": largo,
            "value2": ancho,
            "name": f"LENGTH_{_fmt(largo)}",
        },
        {
            "kind": kind,
            "axis": "W",
            "value": largo,
            "value2": ancho,
            "name": f"WIDTH_{_fmt(ancho)}",
        },
    ]


def _nombres_unicos(rows: list[dict]) -> list[dict]:
    """Si dos cotas comparten nombre, la segunda no pisa el JPG de la primera."""
    vistos: dict[str, int] = {}
    for row in rows:
        base = str(row.get("name") or "COTA")
        n = vistos.get(base, 0) + 1
        vistos[base] = n
        if n > 1:
            row["name"] = f"{base}_{n}"
    return rows


def _fila_eje(kind: str, item: dict) -> dict:
    size = item.get("size") or ("", 0.0)
    return {
        "kind": kind,
        "value": item["value"],
        "size": size,
        "n": item.get("n") or 1,
        "name": f"{kind}_{_fmt(item['value'])}",
    }


def _misma_orilla(item: dict, valor: float, size) -> bool:
    if abs(float(item["value"]) - valor) > 0.25:
        return False
    return _same_size(item.get("size"), size)


def _cuenta_marcas(marcas: list[tuple[float, float]], eje: int, valor: float, tol: float = 0.6) -> int:
    return sum(1 for p in marcas if abs(float(p[eje]) - valor) <= tol)


def _cross(draw, c, arm: float) -> None:
    x, y = c
    arm = max(6, arm)
    draw.line((x - arm, y - arm, x + arm, y + arm), fill=_AZUL, width=1)
    draw.line((x - arm, y + arm, x + arm, y - arm), fill=_AZUL, width=1)


def _cuenta_en(feats, clave: str, valor: float, tol: float = 0.6) -> int:
    return sum(1 for f in feats if clave in f and abs(float(f[clave]) - valor) <= tol)


def _ink_box(font, texto) -> tuple[float, float, float, float]:
    scratch = ImageDraw.Draw(Image.new("RGB", (4, 4)))
    box = scratch.textbbox((0, 0), texto, font=font)
    return float(box[0]), float(box[1]), float(box[2]), float(box[3])


def _texto(draw, box, texto, font) -> None:
    """El rótulo cae dentro de la caja. El ancla de la fuente no es la esquina de la tinta."""
    x0, y0, x1, y1 = box
    left, top, _right, _bottom = _ink_box(font, texto)
    draw.rectangle((x0 - 3, y0 - 2, x1 + 3, y1 + 2), fill="#FFFFFF")
    draw.text((x0 - left, y0 - top), texto, fill=_TEXTO, font=font)


def _capa_texto(texto, font) -> Image.Image:
    left, top, right, bottom = _ink_box(font, texto)
    pad = 8
    ancho = max(int(math.ceil(right - left)) + pad * 2, 8)
    alto = max(int(math.ceil(bottom - top)) + pad * 2, 8)
    capa = Image.new("RGBA", (ancho, alto), (255, 255, 255, 0))
    ImageDraw.Draw(capa).text((pad - left, pad - top), texto, fill=_TEXTO, font=font)
    return capa


def _texto_vertical(img: Image.Image, ocupados, cx, y0, texto, font):
    rot = _capa_texto(texto, font).rotate(90, expand=True)
    rw, rh = rot.size
    x = int(cx - rw / 2)
    y = int(y0)
    box = _sitio(ocupados, x, y, rw, rh, "x")
    px = int(min(max(0, box[0]), max(0, img.width - rw)))
    py = int(min(max(0, box[1]), max(0, img.height - rh)))
    img.paste(rot, (px, py), rot)
    return (px, py, px + rw, py + rh)


def _clamp_box(box, ancho: float, alto: float, margen: float = 8):
    x0, y0, x1, y1 = box
    tw, th = x1 - x0, y1 - y0
    x0 = min(max(margen, x0), max(margen, ancho - tw - margen))
    y0 = min(max(margen, y0), max(margen, alto - th - margen))
    return (x0, y0, x0 + tw, y0 + th)


def _bajar_si_empalma(box, puestos, alto: float, ancho: float):
    """Si el rótulo pisa otro, lo baja un poco y lo corre a la izquierda.

    El ancla (la cota en el modelo) se queda; quien llama dibuja la diagonal.
    """
    x0, y0, x1, y1 = box
    tw, th = x1 - x0, y1 - y0
    ocupados = [p for p in puestos or [] if p]
    if not any(_cajas_chocan(box, otro, 8) for otro in ocupados):
        return box, False
    salto = max(th * 0.85, 18)
    for i in range(1, 7):
        for dx in (18, 36, 56):
            nx = max(8.0, x0 - dx)
            ny = y0 + i * salto
            if nx + tw > ancho - 8 or ny + th > alto - 8:
                continue
            cand = (nx, ny, nx + tw, ny + th)
            if not any(_cajas_chocan(cand, otro, 8) for otro in ocupados):
                return cand, True
    return box, False


def _diagonal(draw, ancla, destino) -> None:
    """Tramo corto del ancla real al texto que se bajó."""
    if math.hypot(destino[0] - ancla[0], destino[1] - ancla[1]) < 4:
        return
    draw.line((ancla[0], ancla[1], destino[0], destino[1]), fill=_TESTIGO, width=1)


def _sitio(ocupados, x, y, tw, th, eje: str):
    x = max(2, x)
    y = max(2, y)
    paso = th + 5
    box = (x, y, x + tw, y + th)
    for _ in range(14):
        if not any(_cajas_chocan(box, otro, 5) for otro in ocupados):
            return box
        if eje == "x":
            y += paso
        else:
            x -= paso
            if x < 2:
                x = 2
                y += paso
        box = (x, y, x + tw, y + th)
    return box


def _size_cota(cotas: list[dict], valor: float, fallback=None):
    for item in cotas or []:
        if abs(float(item.get("value") or 0) - valor) <= 0.25:
            return item.get("size")
    return fallback


def _primera_en_x(feats, x: float, hole_anchor: str = "center", size=None, tol: float = 0.25):
    hits = []
    for feat in feats:
        if size and not _same_size(_tamano(feat), size):
            continue
        for mx, my in _marcas([feat], "x", hole_anchor):
            if abs(mx - x) <= tol:
                hits.append({"cx": mx, "cy": my})
    if not hits:
        return None
    return min(hits, key=lambda f: float(f["cy"]))


def _primera_en_y(feats, y: float, hole_anchor: str = "center", size=None, tol: float = 0.25):
    hits = []
    for feat in feats:
        if size and not _same_size(_tamano(feat), size):
            continue
        for mx, my in _marcas([feat], "y", hole_anchor):
            if abs(my - y) <= tol:
                hits.append({"cx": mx, "cy": my})
    if not hits:
        return None
    return min(hits, key=lambda f: float(f["cx"]))


def _dash(draw, a, b, color, width) -> None:
    dist = math.hypot(b[0] - a[0], b[1] - a[1]) or 1
    steps = max(2, int(dist / 7))
    for i in range(0, steps, 2):
        t0, t1 = i / steps, min(1.0, (i + 1) / steps)
        p0 = (a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0)
        p1 = (a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1)
        draw.line([p0, p1], fill=color, width=width)


def _stadium(draw, marco: _Marco, feat: dict, activo: bool = False) -> None:
    x0, y0, x1, y1, r = feat["x0"], feat["y0"], feat["x1"], feat["y1"], feat["dia"] / 2
    a = marco.px(min(x0, x1) - r, min(y0, y1) - r)
    b = marco.px(max(x0, x1) + r, max(y0, y1) + r)
    box = [min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])]
    rad = max(1, min(r * marco.escala, (box[2] - box[0]) / 2, (box[3] - box[1]) / 2))
    draw.rounded_rectangle(
        box,
        radius=rad,
        outline="#1A5276" if activo else _TRAZO,
        fill="#D6EAF8" if activo else None,
        width=3 if activo else 2,
    )


def _draw_poly(draw, marco: _Marco, poly, largo, ancho) -> None:
    pts = []
    for item in poly or []:
        if not isinstance(item, (tuple, list)) or len(item) < 2:
            continue
        pts.append(marco.px(float(item[0]), float(item[1])))
    if len(pts) < 3:
        draw.rectangle((marco.sx0, marco.sy0, marco.sx1, marco.sy1), fill=_RELLENO, outline=_TRAZO, width=2)
        return
    draw.polygon(pts, fill=_RELLENO, outline=_TRAZO)
    closed = pts + [pts[0]]
    draw.line(closed, fill=_TRAZO, width=2)
    _ = largo, ancho


def _cajas_chocan(a, b, gap: float = 4) -> bool:
    return not (a[2] + gap < b[0] or b[2] + gap < a[0] or a[3] + gap < b[1] or b[3] + gap < a[1])


def _caja_en_pieza(box, marco: _Marco, pad: float = 2) -> bool:
    return not (
        box[2] < marco.sx0 - pad
        or box[0] > marco.sx1 + pad
        or box[3] < marco.sy0 - pad
        or box[1] > marco.sy1 + pad
    )


def _leader(draw, marco: _Marco, cx, cy, radio, texto, font, ocupados: list, img_size=(0, 0)) -> None:
    tw, th = _measure(draw, font, texto)
    c = marco.px(cx, cy)
    r = max(radio * marco.escala, 6)
    margen = 16
    cerca_derecha = c[0] >= marco.sx1 - 90

    opciones = []

    def registrar(peso, ax, ay, bx, by, tx, ty):
        box = (tx, ty, tx + tw, ty + th)
        opciones.append((peso, ax, ay, bx, by, tx, ty, box))

    registrar(
        0 if cerca_derecha else 3,
        c[0] + r,
        c[1],
        marco.sx1 + margen,
        c[1],
        marco.sx1 + margen + 4,
        c[1] - th / 2,
    )
    x_arriba = min(max(c[0] + 24, marco.sx0 + 8), marco.sx1 - tw - 8)
    registrar(
        0 if not cerca_derecha else 3,
        c[0],
        c[1] - r,
        x_arriba,
        marco.sy0 - margen,
        x_arriba + 4,
        marco.sy0 - margen - th - 2,
    )
    registrar(
        2,
        c[0],
        c[1] - r,
        c[0],
        marco.sy0 - margen,
        c[0] + 5,
        marco.sy0 - margen - th - 2,
    )
    registrar(
        5,
        c[0] - r,
        c[1],
        marco.sx0 - margen,
        c[1],
        marco.sx0 - margen - tw - 4,
        c[1] - th / 2,
    )

    def choca(box):
        return any(_cajas_chocan(box, otro, 6) for otro in ocupados)

    opciones.sort(
        key=lambda it: (
            1 if choca(it[7]) else 0,
            1 if _caja_en_pieza(it[7], marco) else 0,
            it[0],
            abs(it[3] - c[0]) + abs(it[4] - c[1]),
        )
    )
    _peso, ax, ay, bx, by, tx, ty, box = opciones[0]
    box = _sitio(ocupados, box[0], box[1], tw, th, "x" if cerca_derecha else "x")
    limite_x = float(img_size[0] or 0)
    limite_y = float(img_size[1] or 0)
    tx = float(box[0])
    ty = float(box[1])
    if limite_x > tw + 12:
        tx = min(max(6.0, tx), limite_x - tw - 6)
    if limite_y > th + 12:
        ty = min(max(6.0, ty), limite_y - th - 6)
    box = (tx, ty, tx + tw, ty + th)
    if abs(ax - bx) > 1.5 and abs(ay - by) > 1.5:
        rodilla = (bx, ay) if abs(marco.sx1 - c[0]) < abs(c[1] - marco.sy0) else (ax, by)
        draw.line((ax, ay, rodilla[0], rodilla[1], bx, by), fill=_TESTIGO, width=1)
    else:
        draw.line((ax, ay, bx, by), fill=_TESTIGO, width=1)
    draw.line((bx, by, tx - 2 if tx >= bx else tx + tw + 2, ty + th / 2), fill=_TESTIGO, width=1)
    _texto(draw, box, texto, font)
    ocupados.append(box)
