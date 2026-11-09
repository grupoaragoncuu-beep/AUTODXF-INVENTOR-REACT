"""Vista de perfil (canto) para doblez: patas A, B, C, HEIGHT, ángulos y THK."""

from __future__ import annotations

import math
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from drawing_jpg import _AZUL, _TRAZO, _cajas_chocan, _capa_texto, _fmt, _font, _font_cota, _measure

_FONDO = "#FFFFFF"


def save_bend_drawing(
    dest: str | Path,
    outline: list[tuple[float, float]],
    *,
    title: str,
    subtitle: str,
    unit: str,
    legs: list[dict],
    height: float,
    thk: float,
    angles: list[dict],
    segments: list | None = None,
) -> str:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    unit = str(unit or "mm").strip() or "mm"
    xs = [p[0] for p in outline] or [0.0, 1.0]
    ys = [p[1] for p in outline] or [0.0, 1.0]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    span_x = max(maxx - minx, 1e-3)
    span_y = max(maxy - miny, height, 1e-3)
    poly = [(p[0] - minx, p[1] - miny) for p in outline]
    shifted = []
    for leg in legs:
        shifted.append(
            {
                **leg,
                "cx": float(leg.get("cx", 0)) - minx,
                "cy": float(leg.get("cy", 0)) - miny,
                "minx": float(leg.get("minx", 0)) - minx,
                "maxx": float(leg.get("maxx", 0)) - minx,
                "miny": float(leg.get("miny", 0)) - miny,
                "maxy": float(leg.get("maxy", 0)) - miny,
            }
        )
    angs = []
    for ang in angles:
        angs.append({"deg": float(ang.get("deg", 90)), "x": float(ang.get("x", 0)) - minx, "y": float(ang.get("y", 0)) - miny, "letter": str(ang.get("letter") or "")})

    _ = title, subtitle
    dim_font = _font_cota(13, False)
    dummy = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    h_val = height if height > 0.2 else span_y
    vs_pre = [leg for leg in shifted if str(leg.get("kind")) == "V"]
    height_leg = None
    if vs_pre:
        iguales = [leg for leg in vs_pre if abs(float(leg.get("length") or 0) - h_val) < 1.0]
        height_leg = iguales[0] if iguales else max(vs_pre, key=lambda leg: float(leg.get("maxy") or 0))
    height_right = bool(height_leg and float(height_leg.get("cx") or 0) > span_x * 0.45)
    left_v = any(float(leg.get("cx") or 0) <= span_x * 0.45 for leg in vs_pre)
    if height_right and left_v:
        izq, der, abajo, arriba = 280, 320, 130, 88
    elif height_right:
        izq, der, abajo, arriba = 96, 300, 130, 88
    else:
        izq, der, abajo, arriba = 268, 210, 130, 88
    escala = 720 / max(span_x, span_y)
    mw = int(izq + span_x * escala + der)
    mh = int(arriba + span_y * escala + abajo)
    img = Image.new("RGB", (max(mw, 520), max(mh, 380)), _FONDO)
    draw = ImageDraw.Draw(img)

    def px(x: float, y: float) -> tuple[float, float]:
        return (izq + x * escala, arriba + (span_y - y) * escala)

    if len(poly) >= 3:
        pts = [px(x, y) for x, y in poly]
        draw.polygon(pts, fill="#F0F2F4", outline=_TRAZO)
        closed = pts if pts[0] == pts[-1] else pts + [pts[0]]
        draw.line(closed, fill=_TRAZO, width=3)
    else:
        for trazo in segments or []:
            if len(trazo) < 2:
                continue
            draw.line([px(p[0] - minx, p[1] - miny) for p in trazo], fill=_TRAZO, width=2)

    x0, y0 = px(0, 0)
    x1, y1 = px(span_x, span_y)
    n_v = sum(1 for leg in shifted if str(leg.get("kind")) == "V")
    a_right = any(
        str(leg.get("kind")) == "V"
        and float(leg.get("cx") or 0) > span_x * 0.45
        and not (n_v == 1 and abs(float(leg.get("length") or 0) - h_val) < 1.0)
        for leg in shifted
    )
    puestos: list[tuple[float, float, float, float]] = []
    x_top = _x_en_y(poly, span_y, thk)
    x_bot = _x_en_y(poly, 0.0, thk)
    if height_right:
        hx = x1 + (110 if a_right else 36)
        _dash(draw, (px(x_top, span_y)[0], y1), (hx, y1))
        _dash(draw, (px(x_bot, 0)[0], y0), (hx, y0))
        _dash(draw, (hx, y1), (hx, y0))
        puestos.append(_cota_v(draw, dummy, dim_font, hx, y1, y0, f"HEIGHT={_fmt(h_val)} {unit}", lado="right"))
    else:
        hx = izq
        _dash(draw, (px(x_top, span_y)[0], y1), (hx, y1))
        _dash(draw, (px(x_bot, 0)[0], y0), (hx, y0))
        _dash(draw, (hx, y1), (hx, y0))
        puestos.append(_cota_v(draw, dummy, dim_font, 132, y1, y0, f"HEIGHT={_fmt(h_val)} {unit}", lado="left"))

    for leg in shifted:
        letra = str(leg.get("letter") or "")
        valor = float(leg.get("length") or 0)
        kind = str(leg.get("kind") or "V")
        if n_v == 1 and kind == "V" and abs(valor - h_val) < 1.0:
            continue
        texto = f"{letra}={_fmt(valor)} {unit}"
        if kind == "H":
            xa, ya = px(leg["minx"], span_y)
            xb, yb = px(leg["maxx"], span_y)
            y_dim = yb - 28
            _dash(draw, (xa, y_dim), (xa, px(leg["minx"], max(float(leg["maxy"]), 0))[1]))
            _dash(draw, (xb, y_dim), (xb, ya))
            puestos.append(_cota_h(draw, dummy, dim_font, xa, xb, y_dim, texto))
        else:
            side = "right" if leg["cx"] > span_x * 0.45 else "left"
            ya = px(leg["cx"], leg["maxy"])[1]
            yb = px(leg["cx"], leg["miny"])[1]
            if side == "right":
                _dash(draw, (px(leg["maxx"], leg["maxy"])[0], ya), (x1 + 36, ya))
                _dash(draw, (px(leg["maxx"], leg["miny"])[0], yb), (x1 + 36, yb))
                puestos.append(
                    _cota_v(draw, dummy, dim_font, x1 + 36, ya, yb, texto, lado="right", img=img, puestos=puestos)
                )
            else:
                _dash(draw, (px(leg["minx"], leg["maxy"])[0], ya), (izq - 18, ya))
                _dash(draw, (px(leg["minx"], leg["miny"])[0], yb), (izq - 18, yb))
                puestos.append(
                    _cota_v(draw, dummy, dim_font, izq - 18, ya, yb, texto, lado="left", img=img, puestos=puestos)
                )

    for ang in angs:
        box_g = _angulo_detalle(
            draw,
            dummy,
            dim_font,
            px,
            ang,
            shifted,
            thk,
            unit,
            escala,
            x1,
            poly,
            mostrar_thk=False,
        )
        if box_g:
            puestos.append(box_g)
    _thk_auto(draw, dummy, dim_font, px, shifted, thk, unit, span_x, img, puestos)

    img.save(dest, "JPEG", quality=93, optimize=True)
    return str(dest)


def _cota_v(draw, dummy, font, x, y_a, y_b, texto, lado: str = "left", img=None, puestos=None):
    y0, y1 = (y_a, y_b) if y_a < y_b else (y_b, y_a)
    draw.line((x, y0, x, y1), fill=_AZUL, width=1)
    draw.line((x - 4, y0, x + 4, y0), fill=_AZUL, width=1)
    draw.line((x - 4, y1, x + 4, y1), fill=_AZUL, width=1)
    tw, th = _measure(dummy, font, texto)
    mid = (y0 + y1) / 2
    if "HEIGHT=" in texto:
        valor = texto.split("HEIGHT=", 1)[1]
        tw1, _ = _measure(dummy, font, "HEIGHT")
        tw2, _ = _measure(dummy, font, valor)
        if lado == "right":
            draw.text((x + 8, mid - th - 1), "HEIGHT", fill=_AZUL, font=font)
            draw.text((x + 8, mid + 2), valor, fill=_AZUL, font=font)
            return (x + 6, mid - th - 2, x + 8 + max(tw1, tw2), mid + th + 4)
        draw.text((x - max(tw1, tw2) - 6, mid - th - 1), "HEIGHT", fill=_AZUL, font=font)
        draw.text((x - tw2 - 6, mid + 2), valor, fill=_AZUL, font=font)
        return (x - max(tw1, tw2) - 8, mid - th - 2, x - 4, mid + th + 4)
    if lado == "right":
        box = (x + 8, mid - th / 2, x + 8 + tw, mid + th / 2)
    else:
        box = (x - tw - 8, mid - th / 2, x - 8, mid + th / 2)
    if img is not None and puestos and any(_cajas_chocan(box, p, 6) for p in puestos if p):
        return _texto_vertical_cota(img, font, texto, x, mid, lado)
    draw.text((box[0], box[1]), texto, fill=_AZUL, font=font)
    return box


def _cota_h(draw, dummy, font, x_a, x_b, y, texto):
    x0, x1 = (x_a, x_b) if x_a < x_b else (x_b, x_a)
    draw.line((x0, y, x1, y), fill=_AZUL, width=1)
    draw.line((x0, y - 4, x0, y + 4), fill=_AZUL, width=1)
    draw.line((x1, y - 4, x1, y + 4), fill=_AZUL, width=1)
    tw, th = _measure(dummy, font, texto)
    tx = (x0 + x1) / 2 - tw / 2
    draw.text((tx, y - th - 4), texto, fill=_AZUL, font=font)
    return (tx, y - th - 4, tx + tw, y)


def _x_en_y(poly: list, y_ref: float, thk: float) -> float:
    """X de la pieza en esa altura, para que la extensión de HEIGHT toque metal."""
    banda = max(float(thk or 6.0) * 0.7, 2.0)
    hits = [p[0] for p in poly if abs(p[1] - y_ref) <= banda]
    if not hits:
        return 0.0 if y_ref < 1 else max((p[0] for p in poly), default=0.0)
    return max(hits) if y_ref > 1 else max(hits)


def _texto_vertical_cota(img, font, texto, x, mid, lado: str):
    rot = _capa_texto(texto, font).rotate(90, expand=True)
    rw, rh = rot.size
    if lado == "right":
        px, py = int(x + 8), int(mid - rh / 2)
    else:
        px, py = int(x - 8 - rw), int(mid - rh / 2)
    img.paste(rot, (px, py), rot)
    return (px, py, px + rw, py + rh)


def _dash(draw, a, b, dash: int = 5, gap: int = 4) -> None:
    x0, y0 = a
    x1, y1 = b
    length = math.hypot(x1 - x0, y1 - y0)
    if length < 2:
        return
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    pos = 0.0
    while pos < length:
        q0 = pos
        q1 = min(length, pos + dash)
        draw.line((x0 + ux * q0, y0 + uy * q0, x0 + ux * q1, y0 + uy * q1), fill=_AZUL, width=1)
        pos += dash + gap


def _angulo_detalle(
    draw,
    dummy,
    font,
    px,
    ang,
    legs,
    thk: float,
    unit: str,
    escala: float,
    x_max: float = 0.0,
    poly: list | None = None,
    mostrar_thk: bool = False,
) -> None:
    letra = str(ang.get("letter") or "A")
    deg = float(ang.get("deg") or 90)
    vleg = next((leg for leg in legs if str(leg.get("letter")) == letra and str(leg.get("kind")) == "V"), None)
    hleg = next((leg for leg in legs if str(leg.get("kind")) == "H"), None)
    if vleg is None or hleg is None:
        cx, cy = px(float(ang.get("x") or 0), float(ang.get("y") or 0))
        return _globo_ang(draw, dummy, font, (cx, cy), letra, deg)
    if float(hleg["cx"]) < float(vleg["cx"]):
        ix = float(vleg["minx"])
        hx = float(hleg["minx"])
        ox_s = -1.0
    else:
        ix = float(vleg["maxx"])
        hx = float(hleg["maxx"])
        ox_s = 1.0
    if float(vleg["cy"]) > float(hleg["cy"]):
        iy = float(hleg["maxy"])
        vy = float(vleg["maxy"])
        oy_s = 1.0
    else:
        iy = float(hleg["miny"])
        vy = float(vleg["miny"])
        oy_s = -1.0
    r_mm = _radio_filete(poly or [], ix, iy, ox_s, oy_s, thk)
    cx_m, cy_m = ix + ox_s * r_mm, iy + oy_s * r_mm
    centro = px(cx_m, cy_m)
    tan_h = px(cx_m, iy)
    tan_v = px(ix, cy_m)
    r_px = max(r_mm * escala, 2.0)
    corner = px(ix, iy)
    bx = (px(hx, iy)[0] - corner[0]) + (px(ix, vy)[0] - corner[0])
    by = (px(hx, iy)[1] - corner[1]) + (px(ix, vy)[1] - corner[1])
    bl = math.hypot(bx, by) or 1.0
    ux, uy = bx / bl, by / bl
    globo = (centro[0] + ux * (r_px + 52), centro[1] + uy * (r_px + 52))
    return _globo_slot(draw, dummy, font, centro, globo, letra, deg)


def _radio_filete(poly: list, ix: float, iy: float, ox_s: float, oy_s: float, thk: float) -> float:
    """Radio interior del doblez, acotado al filete de esa esquina."""
    guess = max(float(thk or 6.0), 1.0)
    if len(poly) < 8:
        return guess
    window = guess * 4.0
    best_r, best_s = guess, -1e9
    r = guess * 0.35
    while r <= guess * 2.2:
        cx, cy = ix + ox_s * r, iy + oy_s * r
        hits = 0
        for x, y in poly:
            if math.hypot(x - ix, y - iy) > window:
                continue
            if (x - ix) * ox_s < -0.8 or (y - iy) * oy_s < -0.8:
                continue
            if abs(math.hypot(x - cx, y - cy) - r) <= 0.45:
                hits += 1
        score = hits - 0.25 * abs(r - guess)
        if score > best_s:
            best_s, best_r = score, r
        r += 0.2
    return best_r if best_s >= 2 else guess


def _arco_entre(draw, centro, p1, p2, r: float) -> None:
    """Arco de 90° concéntrico al filete, entre las dos tangentes."""
    cx, cy = centro
    a1 = math.degrees(math.atan2(p1[1] - cy, p1[0] - cx))
    a2 = math.degrees(math.atan2(p2[1] - cy, p2[0] - cx))
    d_cw = (a2 - a1) % 360.0
    if d_cw <= 180.0:
        start, end = a1, a1 + d_cw
    else:
        start, end = a2, a2 + ((a1 - a2) % 360.0)
    box = (cx - r, cy - r, cx + r, cy + r)
    draw.arc(box, start=start, end=end, fill=_AZUL, width=3)


def _font_angulo(size: int):
    """Arial no trae ∠ (sale un recuadro). Segoe UI Symbol / Cambria / Arial Unicode sí."""
    windir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    for name in ("seguisym.ttf", "cambria.ttc", "arialuni.ttf"):
        path = os.path.join(windir, name)
        if not os.path.isfile(path):
            continue
        try:
            return ImageFont.truetype(path, size, index=0)
        except OSError:
            continue
    return _font(size, False)


def _thk_auto(draw, dummy, font, px, legs, thk: float, unit: str, span_x: float, img=None, puestos=None) -> None:
    """THK en un hueco libre del alma; si choca, el texto se pone vertical."""
    if not thk:
        return
    hleg = max((leg for leg in legs if str(leg.get("kind")) == "H"), key=lambda leg: float(leg.get("length") or 0), default=None)
    if hleg is None:
        return
    xmin, xmax = float(hleg["minx"]), float(hleg["maxx"])
    pie = f"THK={_fmt(thk)} {unit}"
    tw, tht = _measure(dummy, font, pie)
    ocup = [p for p in (puestos or []) if p]
    best = None
    for t in (0.28, 0.4, 0.5, 0.6, 0.72):
        x = xmin + t * (xmax - xmin)
        for cara, signo in (("maxy", -1), ("miny", 1)):
            p0 = px(x, float(hleg[cara]))
            tx = p0[0] - tw / 2
            ty = p0[1] + (14 if signo > 0 else -14 - tht)
            box = (tx, ty, tx + tw, ty + tht)
            if any(_cajas_chocan(box, p, 8) for p in ocup):
                continue
            score = min((math.hypot((box[0] + box[2]) / 2 - (p[0] + p[2]) / 2, (box[1] + box[3]) / 2 - (p[1] + p[3]) / 2) for p in ocup), default=400)
            if best is None or score > best[0]:
                best = (score, p0, box, False)
    if best is None:
        p0 = px((xmin + xmax) / 2, float(hleg["miny"]))
        box = (p0[0] + 10, p0[1] + 8, p0[0] + 10 + tw, p0[1] + 8 + tht)
        best = (0, p0, box, True)
    _p0, box, vertical = best[1], best[2], best[3]
    y_txt = box[1] if box[1] > _p0[1] else box[3]
    draw.line((_p0[0], _p0[1], _p0[0], y_txt), fill=_AZUL, width=1)
    if vertical and img is not None:
        _texto_vertical_cota(img, font, pie, _p0[0], _p0[1] + 40, "right")
    else:
        draw.text((box[0], box[1]), pie, fill=_AZUL, font=font)


def _globo_ang(draw, dummy, font, centro, letra: str, deg: float) -> None:
    _globo_slot(draw, dummy, font, centro, centro, letra, deg)


def _globo_slot(draw, dummy, font, origen, centro, letra: str, deg: float):
    cx, cy = centro
    ang_font = _font_angulo(max(int(getattr(font, "size", 13) or 13), 14))
    texto = f"{letra}\u2220{int(round(deg))}"
    bb = dummy.textbbox((0, 0), texto, font=ang_font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    pad_x, pad_y = 14, 8
    w, h = tw + pad_x * 2, max(th + pad_y * 2, 24)
    rad = h / 2
    box = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
    dx, dy = cx - origen[0], cy - origen[1]
    dist = math.hypot(dx, dy) or 1.0
    ux, uy = dx / dist, dy / dist
    borde = (cx - ux * (w / 2 - 1), cy - uy * (h / 2 - 1))
    if dist > 8:
        _dash(draw, origen, borde, 4, 3)
    draw.rounded_rectangle(box, radius=rad, outline=_AZUL, width=1, fill=_FONDO)
    draw.text((cx - tw / 2 - bb[0], cy - th / 2 - bb[1]), texto, fill=_AZUL, font=ang_font)
    return box
