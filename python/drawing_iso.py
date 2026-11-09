"""Isométrica sin cotas, con globos, para el baño de estaño."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from drawing_jpg import _AZUL, _TEXTO, _TRAZO, _font, _measure

_FONDO = "#FFFFFF"


def save_iso_drawing(
    dest: str | Path,
    edges: list[list[tuple[float, float]]],
    holes: list[tuple[float, float, float]],
    balloons: list[dict],
    *,
    title: str,
    subtitle: str,
) -> str:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    pts = [p for edge in edges for p in edge] + [(b["x"], b["y"]) for b in balloons] + [(h[0], h[1]) for h in holes]
    if not pts:
        pts = [(0.0, 0.0), (1.0, 1.0)]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    span_x = max(maxx - minx, 1e-3)
    span_y = max(maxy - miny, 1e-3)
    title_font = _font(18, True)
    balloon_font = _font(14, True)
    dummy = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    pad = 90
    escala = 680 / max(span_x, span_y)
    mw = int(pad * 2 + span_x * escala)
    mh = int(pad * 2 + span_y * escala + 36)
    img = Image.new("RGB", (max(mw, 420), max(mh, 360)), _FONDO)
    draw = ImageDraw.Draw(img)

    def px(x: float, y: float) -> tuple[float, float]:
        return (pad + (x - minx) * escala, pad + 28 + (maxy - y) * escala)

    for edge in edges:
        if len(edge) < 2:
            continue
        draw.line([px(x, y) for x, y in edge], fill=_TRAZO, width=2)
    for cx, cy, rad in holes:
        c = px(cx, cy)
        r = max(3.0, rad * escala)
        draw.ellipse((c[0] - r, c[1] - r, c[0] + r, c[1] + r), outline=_TRAZO, width=2)

    for ball in balloons:
        _globo(draw, dummy, balloon_font, px(ball["x"], ball["y"]), px(ball["tx"], ball["ty"]), str(ball.get("letter") or "?"))

    draw.text((pad, 12), title, fill=_TEXTO, font=title_font)
    if subtitle:
        draw.text((pad, 34), subtitle, fill=_TEXTO, font=_font(11, False))
    img.save(dest, "JPEG", quality=93, optimize=True)
    return str(dest)


def _globo(draw, dummy, font, ancla, texto_xy, letra: str) -> None:
    ax, ay = ancla
    tx, ty = texto_xy
    r = 14
    draw.line((ax, ay, tx, ty), fill=_AZUL, width=1)
    draw.ellipse((tx - r, ty - r, tx + r, ty + r), outline=_AZUL, width=2, fill=_FONDO)
    tw, th = _measure(dummy, font, letra)
    draw.text((tx - tw / 2, ty - th / 2 - 1), letra, fill=_AZUL, font=font)
