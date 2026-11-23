"""Una vista por cara, con los puntos numerados. No publica ni toca la base."""

from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from espesor_geo import NOMBRE_OCULTA

CM_A_IN = 1 / 2.54
ROJO = (220, 38, 38)
AZUL = (37, 99, 235)
TINTA = (23, 23, 23)
SUAVE = (90, 90, 90)
LINEA = (40, 40, 40)
CAJA = (210, 210, 210)
RADIO = 20


def dibujar_trazos(
    ruta: Path,
    trazos: list[list[tuple[float, float]]],
    *,
    titulo: str,
    subtitulo: str,
    ancho: float,
    alto: float,
    puntos: list[dict],
    radio: int = RADIO,
) -> None:
    """Contorno real de las caras (aristas), no la caja del RangeBox."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    margen = 56
    leyenda = 300
    escala = 1100 / max(float(ancho), float(alto), 1.0)
    lienzo_w = max(int(ancho * escala), 40)
    lienzo_h = max(int(alto * escala), 40)
    imagen = Image.new("RGB", (lienzo_w + margen * 2 + leyenda, lienzo_h + margen * 2 + 28), "white")
    draw = ImageDraw.Draw(imagen)
    fuente = _fuente(18)
    fuente_sm = _fuente(14)
    fuente_xs = _fuente(12)

    def px(x: float, y: float) -> tuple[float, float]:
        return (margen + float(x) * escala, margen + (float(alto) - float(y)) * escala)

    for trazo in trazos:
        pts = [px(x, y) for x, y in trazo]
        if len(pts) >= 2:
            draw.line(pts, fill=LINEA, width=2)
    for punto in puntos:
        cx, cy = px(float(punto["x"]), float(punto["y"]))
        _circulo(draw, cx, cy, punto, radio)
    draw.text((margen, 8), titulo, fill=TINTA, font=fuente)
    draw.text((margen, 30), subtitulo, fill=SUAVE, font=fuente_xs)
    _leyenda(draw, puntos, lienzo_w + margen * 2 + 8, margen, fuente_sm, fuente_xs, radio)
    pie = f"{ancho * CM_A_IN:.1f} in × {alto * CM_A_IN:.1f} in"
    draw.text((margen, imagen.height - 22), pie, fill=SUAVE, font=fuente_xs)
    imagen.save(ruta, format="JPEG", quality=92)


def asentar_puntos(
    puntos: list[dict],
    solido,
    ventana,
    origen_u: float,
    origen_v: float,
    cara: tuple[float, float] | None = None,
) -> None:
    """Si el punto cae en un hueco, una ventana o un barreno, lo corre a la chapa.

    Con `cara` (ancho, alto) solo se corre a chapa dentro de esa cara y nunca más
    lejos que un cuarto de su lado corto: no salta a una pieza de afuera.
    """
    try:
        import numpy as np
    except Exception:
        return
    if solido is None:
        return
    cuerpo = np.asarray(solido, dtype=bool)
    if cuerpo.ndim != 2 or cuerpo.sum() < 30:
        return
    alto, ancho = cuerpo.shape
    marca = Image.fromarray(np.where(cuerpo, np.uint8(255), np.uint8(0)))
    interior = np.asarray(marca.filter(ImageFilter.MinFilter(11))) > 128
    if int(interior.sum()) < 30:
        interior = cuerpo
    izquierda, abajo, derecha, arriba = (float(v) for v in ventana)
    span_x = derecha - izquierda or 1.0
    span_y = arriba - abajo or 1.0
    salto = None
    if cara is not None:
        cara_x0 = (origen_u - izquierda) / span_x * (ancho - 1)
        cara_x1 = (float(cara[0]) + origen_u - izquierda) / span_x * (ancho - 1)
        cara_y0 = (arriba - (float(cara[1]) + origen_v)) / span_y * (alto - 1)
        cara_y1 = (arriba - origen_v) / span_y * (alto - 1)
        borde_x = abs(cara_x1 - cara_x0) * 0.015
        borde_y = abs(cara_y1 - cara_y0) * 0.015
        xa = int(max(0, round(min(cara_x0, cara_x1) + borde_x)))
        xb = int(min(ancho, round(max(cara_x0, cara_x1) - borde_x)))
        ya = int(max(0, round(min(cara_y0, cara_y1) + borde_y)))
        yb = int(min(alto, round(max(cara_y0, cara_y1) - borde_y)))
        dentro = np.zeros_like(interior)
        if xb > xa and yb > ya:
            dentro[ya:yb, xa:xb] = True
        interior = interior & dentro
        salto = 0.25 * min(abs(cara_x1 - cara_x0), abs(cara_y1 - cara_y0))
    filas, columnas = np.nonzero(interior)
    if len(columnas) == 0:
        return
    for punto in puntos:
        px = (float(punto["x"]) + origen_u - izquierda) / span_x * (ancho - 1)
        py = (arriba - (float(punto["y"]) + origen_v)) / span_y * (alto - 1)
        ix = int(round(min(max(px, 0.0), ancho - 1)))
        iy = int(round(min(max(py, 0.0), alto - 1)))
        if interior[iy, ix]:
            continue
        distancias = (columnas - ix) ** 2 + (filas - iy) ** 2
        cercano = int(np.argmin(distancias))
        if salto is not None and float(distancias[cercano]) > salto * salto:
            continue
        nx = int(columnas[cercano])
        ny = int(filas[cercano])
        punto["x"] = izquierda + nx / (ancho - 1) * span_x - origen_u
        punto["y"] = arriba - ny / (alto - 1) * span_y - origen_v


def mascara_chapa(imagen: Image.Image):
    """La chapa va pintada de gris oscuro. El hueco y el fondo blanco quedan fuera."""
    try:
        import numpy as np

        datos = np.asarray(imagen.convert("RGB"))
        solido = datos.min(axis=2) < 220
        parte = float(solido.mean()) if solido.size else 0.0
        if parte < 0.01 or parte > 0.985:
            return None
        return solido
    except Exception:
        return None


def trazo_fino(imagen: Image.Image) -> Image.Image:
    """Aristas del sombreado. El relleno de la chapa, claro u oscuro, queda en blanco."""
    rgb = imagen.convert("RGB")
    try:
        import numpy as np

        datos = np.asarray(rgb)
        delta = datos.astype(np.int16)
        borde = np.zeros(datos.shape[:2], dtype=bool)
        borde[:, 1:] |= np.abs(delta[:, 1:] - delta[:, :-1]).sum(axis=2) > 22
        borde[1:, :] |= np.abs(delta[1:, :] - delta[:-1, :]).sum(axis=2) > 22
        fondo = datos.min(axis=2) > 242
        tinta = borde & ~fondo
        return Image.fromarray(np.where(tinta, np.uint8(0), np.uint8(255)), mode="L").convert("RGB")
    except Exception:
        return a_contorno(rgb)


def unir_trazos(alambre: Image.Image, sombra: Image.Image) -> Image.Image:
    """La línea se queda si aparece en el alambrado o en el sombreado."""
    try:
        import numpy as np

        a = np.asarray(alambre.convert("L"))
        b = np.asarray(sombra.convert("L"))
        if a.shape != b.shape:
            return alambre
        return Image.fromarray(np.minimum(a, b), mode="L").convert("RGB")
    except Exception:
        return alambre


def contorno_y_solido(imagen: Image.Image):
    """Líneas del alzado y la máscara de chapa. El hueco, la ventana y el barreno quedan vacíos."""
    rgb = imagen.convert("RGB")
    try:
        import numpy as np

        datos = np.asarray(rgb)
        solido = datos.min(axis=2) < 245
        delta = datos.astype(np.int16)
        borde = np.zeros(solido.shape, dtype=bool)
        borde[:, :-1] |= np.abs(delta[:, 1:] - delta[:, :-1]).sum(axis=2) > 48
        borde[:-1, :] |= np.abs(delta[1:, :] - delta[:-1, :]).sum(axis=2) > 48
        borde &= solido
        marca = np.where(borde, np.uint8(0), np.uint8(255))
        return Image.fromarray(marca, mode="L").convert("RGB"), solido
    except Exception:
        return a_contorno(rgb), None


def a_contorno(imagen: Image.Image) -> Image.Image:
    """Una sola línea negra. El relleno no se imprime y el trazo no se engorda."""
    rgb = imagen.convert("RGB")
    try:
        import numpy as np

        datos = np.asarray(rgb, dtype=np.int16)
        tinta = datos.min(axis=2) < 250
        return Image.fromarray(np.where(tinta, np.uint8(0), np.uint8(255)), mode="L").convert("RGB")
    except Exception:
        ancho, alto = rgb.size
        origen = rgb.load()
        salida = Image.new("RGB", (ancho, alto), "white")
        destino = salida.load()
        for y in range(alto):
            for x in range(ancho):
                punto = origen[x, y]
                if punto[0] < 250 or punto[1] < 250 or punto[2] < 250:
                    destino[x, y] = (0, 0, 0)
        return salida


def guardar_foto(
    ruta: Path,
    imagen: Image.Image,
    px,
    *,
    titulo: str,
    subtitulo: str,
    ancho: float,
    alto: float,
    puntos: list[dict],
    pie: str = "Alzado del ensamble",
    radio: int = RADIO,
) -> None:
    """La foto es el alzado del ensamble. El título no la tapa."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    titulo_h = 48
    leyenda = 300
    lienzo = imagen.convert("RGB")
    salida = Image.new("RGB", (lienzo.width + leyenda, lienzo.height + titulo_h + 28), "white")
    salida.paste(lienzo, (0, titulo_h))
    draw = ImageDraw.Draw(salida)
    fuente = _fuente(18)
    fuente_sm = _fuente(14)
    fuente_xs = _fuente(12)
    draw.text((16, 6), titulo, fill=TINTA, font=fuente)
    draw.text((16, 26), subtitulo, fill=SUAVE, font=fuente_xs)
    for punto in puntos:
        cx, cy = px(float(punto["x"]), float(punto["y"]))
        _circulo(draw, cx, cy + titulo_h, punto, radio)
    _leyenda(draw, puntos, lienzo.width + 16, titulo_h, fuente_sm, fuente_xs, radio)
    pie = f"{ancho * CM_A_IN:.1f} in × {alto * CM_A_IN:.1f} in   ·   {pie}"
    draw.text((16, salida.height - 22), pie, fill=SUAVE, font=fuente_xs)
    salida.save(ruta, format="JPEG", quality=92)


def guardar_vista(
    ruta: Path,
    imagen,
    px,
    *,
    titulo: str,
    subtitulo: str,
    ancho: float,
    alto: float,
    puntos: list[dict],
    radio: int = RADIO,
) -> None:
    """Pega los puntos sobre el alzado ya dibujado del tanque."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    extra = 300
    lienzo = imagen.convert("RGB")
    salida = Image.new("RGB", (lienzo.width + extra, lienzo.height), "white")
    salida.paste(lienzo, (0, 0))
    draw = ImageDraw.Draw(salida)
    fuente = _fuente(18)
    fuente_sm = _fuente(14)
    fuente_xs = _fuente(12)
    draw.rectangle((0, 0, lienzo.width, 46), fill="white")
    draw.text((16, 6), titulo, fill=TINTA, font=fuente)
    draw.text((16, 28), subtitulo, fill=SUAVE, font=fuente_xs)
    for punto in puntos:
        cx, cy = px(float(punto["x"]), float(punto["y"]))
        _circulo(draw, cx, cy, punto, radio)
    _leyenda(draw, puntos, lienzo.width + 16, 16, fuente_sm, fuente_xs, radio)
    pie = f"{ancho * CM_A_IN:.1f} in × {alto * CM_A_IN:.1f} in"
    draw.text((16, lienzo.height - 22), pie, fill=SUAVE, font=fuente_xs)
    salida.save(ruta, format="JPEG", quality=90)


def _circulo(draw, cx, cy, punto, radio: int = RADIO) -> None:
    color = AZUL if punto.get("color") == "azul" else ROJO
    draw.ellipse((cx - radio, cy - radio, cx + radio, cy + radio), fill=color, outline=color)
    texto = str(punto.get("numero") or "")
    fuente = _fuente(round(radio * 1.05))
    caja = draw.textbbox((0, 0), texto, font=fuente)
    draw.text(
        (cx - (caja[2] - caja[0]) / 2, cy - (caja[3] - caja[1]) / 2 - 1),
        texto,
        fill="white",
        font=fuente,
    )


def guardar(
    ruta: Path,
    *,
    titulo: str,
    subtitulo: str,
    ancho: float,
    alto: float,
    puntos: list[dict],
    partes: list[dict] | None = None,
    radio: int = RADIO,
) -> None:
    """ancho/alto y coordenadas en cm. La cota impresa va en pulgadas."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    margen_x, margen_y = 36, 28
    leyenda_ancho = 320
    lienzo_ancho = 980
    escala = lienzo_ancho / ancho if ancho else 1.0
    alto_dibujo = max(80.0, alto * escala)
    if alto_dibujo > 1280:
        escala *= 1280 / alto_dibujo
        alto_dibujo = alto * escala
        lienzo_ancho = ancho * escala
    ancho_img = int(margen_x * 2 + lienzo_ancho + leyenda_ancho)
    alto_img = int(margen_y * 2 + 36 + alto_dibujo + 36)
    imagen = Image.new("RGB", (ancho_img, alto_img), "white")
    draw = ImageDraw.Draw(imagen)
    fuente = _fuente(18)
    fuente_sm = _fuente(14)
    fuente_xs = _fuente(12)
    draw.text((margen_x, 8), titulo, fill=TINTA, font=fuente)
    draw.text((margen_x, 30), subtitulo, fill=SUAVE, font=fuente_xs)
    ox = margen_x
    oy = margen_y + 44
    draw.rectangle((ox, oy, ox + lienzo_ancho, oy + alto_dibujo), outline=LINEA, width=2)
    for parte in partes or []:
        _caja(draw, parte, ox, oy, alto_dibujo, escala, fuente_xs)
    for punto in puntos:
        cx = ox + float(punto["x"]) * escala
        cy = oy + alto_dibujo - float(punto["y"]) * escala
        _circulo(draw, cx, cy, punto, radio)
    _leyenda(draw, puntos, ox + lienzo_ancho + 16, oy, fuente_sm, fuente_xs, radio)
    pie = f"{ancho * CM_A_IN:.1f} in × {alto * CM_A_IN:.1f} in"
    draw.text((margen_x, oy + alto_dibujo + 10), pie, fill=SUAVE, font=fuente_xs)
    imagen.save(ruta, format="JPEG", quality=90)


def _caja(draw, parte, ox, oy, alto_dibujo, escala, fuente) -> None:
    x0 = ox + float(parte["x0"]) * escala
    x1 = ox + float(parte["x1"]) * escala
    y0 = oy + alto_dibujo - float(parte["y1"]) * escala
    y1 = oy + alto_dibujo - float(parte["y0"]) * escala
    draw.rectangle((x0, y0, x1, y1), outline=CAJA, width=1)
    nombre = str(parte.get("nombre") or "")
    if nombre:
        draw.text((x0 + 2, max(oy, y0 - 14)), nombre[:28], fill=SUAVE, font=fuente)


def _punto(draw, punto, ox, oy, alto_dibujo, escala, fuente, radio: int = RADIO) -> None:
    cx = ox + float(punto["x"]) * escala
    cy = oy + alto_dibujo - float(punto["y"]) * escala
    _circulo(draw, cx, cy, punto, radio)


def _leyenda(draw, puntos, x, y, fuente, fuente_xs, radio: int = RADIO) -> None:
    marca = round(radio * 0.75)
    draw.text((x, y), "Puntos", fill=TINTA, font=fuente)
    y += 22
    for punto in puntos:
        color = AZUL if punto.get("color") == "azul" else ROJO
        draw.ellipse((x, y + 1, x + marca, y + 1 + marca), fill=color)
        draw.text((x + marca + 6, y + 1), _linea(punto), fill=TINTA, font=fuente_xs)
        y += marca + 7


def _linea(punto: dict) -> str:
    numero = punto.get("numero")
    if punto.get("grupo") == "oculta":
        familia = NOMBRE_OCULTA.get(str(punto.get("columna") or ""), "")
        pieza = re.sub(r"_\d+$", "", str(punto.get("pieza") or ""))
        texto = f"{numero}  debajo de {familia}" if familia else f"{numero}  debajo de"
        return f"{texto} · {pieza}" if pieza else texto
    if punto.get("grupo") == "aleatoria":
        return f"{numero}  aleatoria"
    banda = punto.get("banda") or ""
    columna = punto.get("columna") or ""
    return f"{numero}  {banda} · {columna}"


def _fuente(tamaño: int):
    for ruta in (
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
    ):
        if Path(ruta).is_file():
            try:
                return ImageFont.truetype(ruta, tamaño)
            except OSError:
                continue
    return ImageFont.load_default()
