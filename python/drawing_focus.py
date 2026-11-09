"""Un JPG por cota: silueta + una sola dimensión (estilo dossier Tank)."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

from drawing_jpg import _TESTIGO, _TEXTO, _font_cota, _measure, _texto

_AZUL = _TESTIGO
_TRAZO = "#1C2833"
_RELLENO = "#FFFFFF"
_LETRA = _font_cota(13, False)


def save_focus_drawing(
    dest: str | Path,
    outline: list[tuple[float, float]],
    *,
    title: str,
    unit: str,
    value: float,
    orient: str,
) -> str:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    unit = str(unit or "in").strip() or "in"
    poly = _orientar(_shift(outline), str(orient).upper().startswith("V"))
    if len(poly) < 3:
        poly = [(0.0, 0.0), (max(value, 1.0), 0.0), (max(value, 1.0), max(value * 0.12, 0.2)), (0.0, max(value * 0.12, 0.2))]
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    span_x = max(maxx - minx, 1e-3)
    span_y = max(maxy - miny, 1e-3)
    vertical = str(orient).upper().startswith("V")
    dummy = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    texto = f"{abs(float(value)):.2f} {unit}"
    tw, th = _measure(dummy, _LETRA, texto)
    izq, der, arriba, abajo = (max(132, int(tw + 52)), 48, 36, 48) if vertical else (48, 48, max(72, int(th + 36)), 36)
    escala = 640.0 / max(span_x, span_y)
    width = int(izq + span_x * escala + der)
    height = int(arriba + span_y * escala + abajo)
    img = Image.new("RGB", (max(width, 280), max(height, 240)), "#FFFFFF")
    draw = ImageDraw.Draw(img)

    def px(x: float, y: float) -> tuple[float, float]:
        return (izq + (x - minx) * escala, arriba + (maxy - y) * escala)

    pts = [px(x, y) for x, y in poly]
    draw.polygon(pts, fill=_RELLENO, outline=_TRAZO)
    closed = pts if pts[0] == pts[-1] else pts + [pts[0]]
    draw.line(closed, fill=_TRAZO, width=3)

    x0, y0 = px(minx, miny)
    x1, y1 = px(maxx, maxy)
    if vertical:
        hx = 28
        draw.line((x0, y1, hx, y1), fill=_AZUL, width=1)
        draw.line((x0, y0, hx, y0), fill=_AZUL, width=1)
        _flecha_v(draw, hx, y1, y0)
        mid = (y0 + y1) / 2
        _texto(draw, (hx + 10, mid - th / 2, hx + 10 + tw, mid + th / 2), texto, _LETRA)
    else:
        hy = 22
        draw.line((x0, y1, x0, hy), fill=_AZUL, width=1)
        draw.line((x1, y1, x1, hy), fill=_AZUL, width=1)
        _flecha_h(draw, x0, x1, hy)
        _texto(draw, ((x0 + x1) / 2 - tw / 2, hy - th - 8, (x0 + x1) / 2 + tw / 2, hy - 4), texto, _LETRA)
    img.save(dest, "JPEG", quality=94, optimize=True)
    return str(dest)


def save_thk_drawing(
    dest: str | Path,
    outline: list[tuple[float, float]],
    *,
    title: str,
    unit: str,
    thk: float,
) -> str:
    """Espesor entre las dos caras del alma, lejos del filete."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    poly = _shift(outline)
    t = max(float(thk), 0.05)
    if len(poly) < 3:
        poly = [(0.0, 0.0), (t, 0.0), (t, t * 8), (0.0, t * 8)]
    horizontal, a, b, estacion = _par_espesor(poly, t)
    dummy = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    texto = f"{t:.2f} {unit}"
    tw, tht = _measure(dummy, _LETRA, texto)
    if horizontal:
        ventana = (a - t * 2.4, estacion - t * 8, b + t * 2.0, estacion + t * 8)
        img, draw, px = _lienzo(poly, ventana, margen=(max(90, int(tw + 28)), 48, 36, 36))
        ya, yb = px(a, estacion), px(b, estacion)
        hy = (ya[1] + yb[1]) / 2
        _flecha_h(draw, ya[0], yb[0], hy)
        _texto(draw, (min(ya[0], yb[0]) - tw - 12, hy - tht / 2, min(ya[0], yb[0]) - 8, hy + tht / 2), texto, _LETRA)
    else:
        ventana = (estacion - t * 8, a - t * 2.0, estacion + t * 8, b + t * 2.4)
        img, draw, px = _lienzo(poly, ventana, margen=(48, 48, max(72, int(tht + 36)), 36))
        ya, yb = px(estacion, a), px(estacion, b)
        hx = (ya[0] + yb[0]) / 2
        _flecha_v(draw, hx, ya[1], yb[1])
        medio = (ya[1] + yb[1]) / 2
        _texto(draw, (hx + 10, medio - tht / 2, hx + 10 + tw, medio + tht / 2), texto, _LETRA)
    img.save(dest, "JPEG", quality=94, optimize=True)
    return str(dest)


def _par_espesor(poly: list[tuple[float, float]], thk: float) -> tuple[bool, float, float, float]:
    """Dos caras reales separadas ~thk. (horizontal, a, b, estación).

    No usa el vértice más a la izquierda + espesor: en un perfil en L ese punto
    es la punta del pie y la cota queda al aire, con una sola cara en el recorte.
    """
    xs = [float(p[0]) for p in poly] or [0.0]
    ys = [float(p[1]) for p in poly] or [0.0]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    # El perfil va de pie: el alma es la franja vertical y el espesor cruza en X.
    # El pie también mide ~thk, pero en Y; esa cota no es la del canto.
    grupos = {True: [], False: []}
    for horizontal, lo, hi in ((True, miny, maxy), (False, minx, maxx)):
        span = hi - lo
        if span < thk * 0.5:
            continue
        for frac in (0.5, 0.42, 0.58, 0.34, 0.66, 0.26, 0.74):
            nivel = lo + span * frac
            cortes = _cortes_perfil(poly, nivel, horizontal, max(thk * 0.12, 0.02))
            for i in range(len(cortes) - 1):
                sep = cortes[i + 1] - cortes[i]
                if sep < thk * 0.55 or sep > thk * 1.75:
                    continue
                score = (abs(sep - thk) / thk, abs(frac - 0.5))
                grupos[horizontal].append((score, cortes[i], cortes[i + 1], nivel))
    pool = grupos[True] or grupos[False]
    if pool:
        pool.sort(key=lambda item: item[0])
        _score, a, b, nivel = pool[0]
        return bool(grupos[True]), a, b, nivel
    return True, minx, min(maxx, minx + thk), miny + (maxy - miny) * 0.58


def _cortes_perfil(poly, nivel: float, horizontal: bool, tol: float) -> list[float]:
    """Intersecciones de una línea (horizontal o vertical) con el contorno."""
    pts = [(float(p[0]), float(p[1])) for p in poly if len(p) >= 2]
    if len(pts) < 2:
        return []
    if math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) > 1e-4:
        pts.append(pts[0])
    hits: list[float] = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if horizontal:
            u0, u1, v0, v1 = y0, y1, x0, x1
        else:
            u0, u1, v0, v1 = x0, x1, y0, y1
        if abs(u1 - u0) < 1e-9:
            continue
        if (u0 < nivel <= u1) or (u1 < nivel <= u0):
            t = (nivel - u0) / (u1 - u0)
            hits.append(v0 + t * (v1 - v0))
    if not hits:
        return []
    hits.sort()
    limpios = [hits[0]]
    for valor in hits[1:]:
        if valor - limpios[-1] > tol:
            limpios.append(valor)
    return limpios


def save_leg_drawing(
    dest: str | Path,
    outline: list[tuple[float, float]],
    *,
    unit: str,
    value: float,
    xmin: float,
    xmax: float,
    y_ref: float,
) -> str:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    poly = _shift(outline)
    ox = min(p[0] for p in outline)
    oy = min(p[1] for p in outline)
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    alto = max(abs(float(value)) * 2.2, (maxx - minx) * 1.4, 1.2)
    ventana = (minx - 0.15, miny - 0.1, maxx + 0.15, miny + alto)
    dummy = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    texto = f"{abs(float(value)):.2f} {unit}"
    tw, th = _measure(dummy, _LETRA, texto)
    img, draw, px = _lienzo(poly, ventana, margen=(40, 40, max(88, int(th + 48)), 36))
    left = px(float(xmin) - ox, float(y_ref) - oy)
    right = px(float(xmax) - ox, float(y_ref) - oy)
    hy = min(left[1], right[1]) - 36
    if hy < 8:
        hy = max(left[1], right[1]) + 36
    draw.line((left[0], left[1], left[0], hy), fill=_AZUL, width=1)
    draw.line((right[0], right[1], right[0], hy), fill=_AZUL, width=1)
    _flecha_h(draw, left[0], right[0], hy)
    cx = (left[0] + right[0]) / 2
    _texto(draw, (cx - tw / 2, hy - th - 10, cx + tw / 2, hy - 6), texto, _LETRA)
    img.save(dest, "JPEG", quality=94, optimize=True)
    return str(dest)


def _lienzo(poly: list[tuple[float, float]], ventana: tuple[float, float, float, float], margen=(48, 48, 36, 36)):
    vx0, vy0, vx1, vy1 = ventana
    if vx1 <= vx0:
        vx1 = vx0 + 1
    if vy1 <= vy0:
        vy1 = vy0 + 1
    izq, der, arriba, abajo = margen
    span_x, span_y = vx1 - vx0, vy1 - vy0
    escala = 560.0 / max(span_x, span_y)
    img = Image.new(
        "RGB",
        (max(int(izq + span_x * escala + der), 280), max(int(arriba + span_y * escala + abajo), 240)),
        "#FFFFFF",
    )
    draw = ImageDraw.Draw(img)

    def px(x: float, y: float) -> tuple[float, float]:
        return (izq + (x - vx0) * escala, arriba + (vy1 - y) * escala)

    pts = [px(x, y) for x, y in poly]
    if len(pts) >= 3:
        draw.polygon(pts, fill=_RELLENO, outline=_TRAZO)
        closed = pts if pts[0] == pts[-1] else pts + [pts[0]]
        draw.line(closed, fill=_TRAZO, width=3)
    return img, draw, px


def _orientar(poly: list[tuple[float, float]], vertical: bool) -> list[tuple[float, float]]:
    if len(poly) < 2:
        return poly
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    span_x, span_y = max(xs) - min(xs), max(ys) - min(ys)
    if vertical and span_x > span_y * 1.05:
        mx = max(xs)
        return [(p[1], mx - p[0]) for p in poly]
    if not vertical and span_y > span_x * 1.05:
        mx = max(xs)
        return [(p[1], mx - p[0]) for p in poly]
    return poly


def _shift(outline: list[tuple[float, float]]) -> list[tuple[float, float]]:
    pts = [(float(p[0]), float(p[1])) for p in outline or [] if len(p) >= 2]
    if not pts:
        return []
    minx = min(p[0] for p in pts)
    miny = min(p[1] for p in pts)
    return [(p[0] - minx, p[1] - miny) for p in pts]


def _flecha_v(draw, x, y_a, y_b) -> None:
    y0, y1 = (y_a, y_b) if y_a < y_b else (y_b, y_a)
    draw.line((x, y0, x, y1), fill=_AZUL, width=1)
    s = 7
    draw.polygon([(x, y0), (x - 4, y0 + s), (x + 4, y0 + s)], fill=_AZUL)
    draw.polygon([(x, y1), (x - 4, y1 - s), (x + 4, y1 - s)], fill=_AZUL)


def _flecha_h(draw, x_a, x_b, y) -> None:
    x0, x1 = (x_a, x_b) if x_a < x_b else (x_b, x_a)
    draw.line((x0, y, x1, y), fill=_AZUL, width=1)
    s = 7
    draw.polygon([(x0, y), (x0 + s, y - 4), (x0 + s, y + 4)], fill=_AZUL)
    draw.polygon([(x1, y), (x1 - s, y - 4), (x1 - s, y + 4)], fill=_AZUL)
