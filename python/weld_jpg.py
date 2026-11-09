"""JPG de soldadura. La cara, el detalle y la isométrica salen del ensamble.

Python solo compone la hoja: fondo blanco, el largo al lado de la pieza
y el símbolo de filete junto al detalle.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

from drawing_jpg import _font, _measure

_FONDO = (255, 255, 255)
_LINEA = "#1C2833"
_SIMBOLO = "#1A5276"
_TEXTO = "#1B2631"
_AZUL = (15, 75, 190)
_NARANJA = (230, 110, 15)
# La cámara encuadra la placa con este margen. El círculo usa el mismo factor.
MARGEN_FOTO = 1.08


def save_weld_jpg(
    dest: str | Path,
    *,
    title: str,
    outline: list[tuple[float, float]],
    welds: list[dict],
    frontal: Image.Image | None = None,
    detalle: Image.Image | None = None,
    iso: Image.Image | None = None,
    width: int = 1760,
    height: int = 980,
) -> str:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    weld = welds[0] if welds else {}
    image = Image.new("RGB", (width, height), _FONDO)
    ancho_uv = max((float(p[0]) for p in outline), default=1.0) - min((float(p[0]) for p in outline), default=0.0)
    alto_uv = max((float(p[1]) for p in outline), default=1.0) - min((float(p[1]) for p in outline), default=0.0)
    frente = _pegar_frente(image, frontal, (28, 28, 860, height - 72), horizontal=ancho_uv >= alto_uv, enderezar=False)
    circulo = _recorte(_nitidez(_limpiar(detalle or _vacio(), suave=True)), 480, 72)
    iso_img = _recorte(_nitidez(_limpiar(iso or _vacio(), suave=True)), 400, 64)
    image.paste(circulo, (1040, 28))
    image.paste(iso_img, (1120, height - 64 - iso_img.height))
    draw = ImageDraw.Draw(image)
    _cota_en_cara(draw, outline, weld, frente)
    _filete(
        draw,
        1040 + circulo.width + 12,
        36 + circulo.height // 2,
        leg=str(weld.get("leg") or ""),
        pitch=str(weld.get("pitch") or str(weld.get("length") or "").replace(" mm", "")),
        both=int(weld.get("sides") or 1) >= 2,
        typ=bool(weld.get("typ")),
        other=str(weld.get("other") or ""),
    )
    font = _font(26, bold=True)
    label = title or "Cordón"
    draw.text((36, height - 48), label, fill=_TEXTO, font=font)
    image.save(dest, "JPEG", quality=95, optimize=True)
    return str(dest)


def _vacio() -> Image.Image:
    return Image.new("RGB", (320, 320), (196, 196, 196))


def _es_fondo(rojo: int, verde: int, azul: int) -> bool:
    """Cielo claro de Inventor. El filete azul (15, 75, 190) no es fondo: el rojo queda bajo."""
    if rojo >= 246 and verde >= 246 and azul >= 246:
        return True
    return min(rojo, verde) >= 160 and azul > rojo + 6 and azul + 4 >= verde and azul >= 180


def _nitidez(imagen: Image.Image) -> Image.Image:
    from PIL import ImageEnhance, ImageFilter

    imagen = ImageEnhance.Contrast(imagen).enhance(1.18)
    imagen = ImageEnhance.Color(imagen).enhance(1.25)
    return imagen.filter(ImageFilter.UnsharpMask(radius=1.4, percent=110, threshold=2))


def _limpiar(imagen: Image.Image, suave: bool = False) -> Image.Image:
    """El fondo azul de Inventor pasa a blanco. El gris del material se queda."""
    imagen = imagen.convert("RGB")
    umbral = 252 if suave else 242
    datos = []
    for rojo, verde, azul in imagen.getdata():
        if suave:
            fondo = _es_fondo(rojo, verde, azul)
        else:
            fondo = azul > rojo + 12 and azul >= verde
        if fondo or (rojo >= umbral and verde >= umbral and azul >= umbral):
            datos.append(_FONDO)
        else:
            datos.append((rojo, verde, azul))
    imagen.putdata(datos)
    if suave:
        return imagen
    contenido = imagen.convert("L").point(lambda valor: 255 if valor < umbral else 0)
    caja = contenido.getbbox()
    if caja:
        imagen = imagen.crop(caja)
    return imagen


def _enderezar(imagen: Image.Image, horizontal: bool) -> Image.Image:
    destino = 0.0 if horizontal else 90.0
    angulo = _eje_placa(imagen)
    if angulo is None:
        return imagen
    delta = angulo - destino
    while delta > 90.0:
        delta -= 180.0
    while delta < -90.0:
        delta += 180.0
    if abs(delta) < 1.2:
        return imagen
    return _limpiar(imagen.rotate(delta, expand=True, fillcolor=_FONDO, resample=Image.Resampling.BICUBIC))


def _eje_placa(imagen: Image.Image) -> float | None:
    """Ángulo del canto, no del relleno. En una placa casi cuadrada el relleno apunta a la diagonal."""
    canto = _angulo_canto(imagen)
    if canto is not None:
        return canto
    return _angulo_puntos(_relleno(imagen))


def _placa(pixeles, x: int, y: int) -> bool:
    rojo, verde, azul = pixeles[x, y]
    return abs(rojo - verde) < 12 and abs(verde - azul) < 12 and 90 < rojo < 215


def _angulo_canto(imagen: Image.Image) -> float | None:
    ancho, alto = imagen.size
    pixeles = imagen.load()
    paso = max(1, int(max(ancho, alto) / 220))
    columnas: dict[int, list[int]] = {}
    for y in range(0, alto, paso):
        for x in range(0, ancho, paso):
            if _placa(pixeles, x, y):
                columnas.setdefault(x, []).append(y)
    canto = []
    for x, ys in columnas.items():
        if max(ys) - min(ys) > alto * 0.2:
            canto.append((float(x), float(min(ys))))
    canto.sort()
    recorte = []
    for punto in canto:
        if len(recorte) >= 6 and punto[1] > min(previo[1] for previo in recorte[-6:]) + 24:
            break
        recorte.append(punto)
    if len(recorte) < 24:
        return None
    xs = [punto[0] for punto in recorte]
    if max(xs) - min(xs) < ancho * 0.35:
        return None
    return _angulo_puntos(recorte)


def _relleno(imagen: Image.Image) -> list[tuple[float, float]]:
    ancho, alto = imagen.size
    paso = max(1, int(max(ancho, alto) / 160))
    pixeles = imagen.load()
    puntos = []
    for y in range(0, alto, paso):
        for x in range(0, ancho, paso):
            if _placa(pixeles, x, y):
                puntos.append((float(x), float(y)))
    return puntos


def _angulo_puntos(puntos: list[tuple[float, float]]) -> float | None:
    if len(puntos) < 24:
        return None
    n = float(len(puntos))
    mx = sum(punto[0] for punto in puntos) / n
    my = sum(punto[1] for punto in puntos) / n
    cxx = sum((punto[0] - mx) ** 2 for punto in puntos) / n
    cyy = sum((punto[1] - my) ** 2 for punto in puntos) / n
    cxy = sum((punto[0] - mx) * (punto[1] - my) for punto in puntos) / n
    return math.degrees(0.5 * math.atan2(2.0 * cxy, cxx - cyy))


def _pegar_frente(
    hoja: Image.Image,
    frontal: Image.Image | None,
    caja: tuple[int, int, int, int],
    *,
    horizontal: bool = True,
    enderezar: bool = True,
) -> tuple[int, int, int, int]:
    imagen = _limpiar(frontal or _vacio(), suave=not enderezar)
    if enderezar:
        imagen = _enderezar(imagen, horizontal)
    imagen = _nitidez(imagen)
    left, top, right, bottom = caja
    ancho = max(1, right - left)
    alto = max(1, bottom - top)
    escala = min(ancho / imagen.width, alto / imagen.height)
    destino = imagen.resize((max(1, int(imagen.width * escala)), max(1, int(imagen.height * escala))), Image.Resampling.LANCZOS)
    x = left + (ancho - destino.width) // 2
    y = top + (alto - destino.height) // 2
    hoja.paste(destino, (x, y))
    return (x, y, x + destino.width, y + destino.height)


def _recorte(imagen: Image.Image, lado: int, pasos: int = 72) -> Image.Image:
    """Recorte quebrado, como la vista de detalle."""
    cuadrado = _cubrir(imagen, lado)
    borde_pts = _dientes(lado, lado / 2 - 8, pasos)
    mascara = Image.new("L", (lado, lado), 0)
    dibujo = ImageDraw.Draw(mascara)
    dibujo.polygon(borde_pts, fill=255)
    salida = Image.new("RGB", (lado, lado), _FONDO)
    salida.paste(cuadrado, mask=mascara)
    borde = ImageDraw.Draw(salida)
    borde.line(borde_pts + [borde_pts[0]], fill=_LINEA, width=2)
    return salida


def _cubrir(imagen: Image.Image, lado: int) -> Image.Image:
    escala = max(lado / imagen.width, lado / imagen.height)
    ancho = max(lado, int(imagen.width * escala))
    alto = max(lado, int(imagen.height * escala))
    grande = imagen.resize((ancho, alto), Image.Resampling.LANCZOS)
    x = (ancho - lado) // 2
    y = (alto - lado) // 2
    return grande.crop((x, y, x + lado, y + lado))


def _dientes(lado: int, radio: float, pasos: int) -> list[tuple[float, float]]:
    centro = lado / 2
    puntos = []
    for paso in range(pasos):
        angulo = 2 * math.pi * paso / pasos
        diente = 7 * math.sin(paso * 2.3) + 4 * math.sin(paso * 0.7) + (5 if paso % 7 == 0 else 0)
        alcance = radio + diente
        puntos.append((centro + math.cos(angulo) * alcance, centro + math.sin(angulo) * alcance))
    return puntos


def _cota_en_cara(draw: ImageDraw.ImageDraw, outline, weld: dict, frente: tuple[int, int, int, int]) -> None:
    huella = weld.get("footprint")
    if not isinstance(huella, (list, tuple)) or len(huella) < 4 or len(outline) < 3:
        return
    esquinas = (
        (float(huella[0]), float(huella[1])),
        (float(huella[2]), float(huella[1])),
        (float(huella[2]), float(huella[3])),
        (float(huella[0]), float(huella[3])),
    )
    puntos = [_en_frente(punto, outline, frente) for punto in esquinas]
    xs = [punto[0] for punto in puntos]
    ys = [punto[1] for punto in puntos]
    cx = (min(xs) + max(xs)) / 2
    cy = (min(ys) + max(ys)) / 2
    _trazo_cordon(draw, puntos, weld)
    radio = max(18.0, min(max(max(xs) - min(xs), max(ys) - min(ys)) * 0.65, 70.0))
    _circulo_guion(draw, cx, cy, radio)
    texto = str(weld.get("length") or "")
    if not texto:
        return
    font = _font(22)
    ancho, alto = _measure(draw, font, texto)
    etiqueta = (frente[2] + 12, cy - alto / 2)
    draw.line((cx + radio, cy, etiqueta[0], cy), fill=_LINEA, width=2)
    draw.rectangle(
        (etiqueta[0] - 4, etiqueta[1] - 3, etiqueta[0] + ancho + 8, etiqueta[1] + alto + 4),
        fill=_FONDO,
        outline=_LINEA,
    )
    draw.text(etiqueta, texto, fill=_TEXTO, font=font)


def _circulo_guion(draw: ImageDraw.ImageDraw, cx: float, cy: float, radio: float) -> None:
    pasos = 28
    for paso in range(0, pasos, 2):
        a0 = 2 * math.pi * paso / pasos
        a1 = 2 * math.pi * (paso + 1) / pasos
        draw.line(
            (
                (cx + math.cos(a0) * radio, cy + math.sin(a0) * radio),
                (cx + math.cos(a1) * radio, cy + math.sin(a1) * radio),
            ),
            fill=_LINEA,
            width=2,
        )


def _trazo_cordon(draw: ImageDraw.ImageDraw, puntos: list[tuple[float, float]], weld: dict) -> None:
    """En la cara completa un filete de 6 mm son unos píxeles. El trazo lo deja ver."""
    if str(weld.get("tone") or "") != "hermetico" or len(puntos) < 2:
        return
    mejor = None
    largo = 0.0
    for indice, origen in enumerate(puntos):
        destino = puntos[(indice + 1) % len(puntos)]
        tramo = math.hypot(destino[0] - origen[0], destino[1] - origen[1])
        if tramo > largo:
            mejor = (origen, destino)
            largo = tramo
    if mejor is None or largo < 12:
        return
    draw.line((mejor[0][0], mejor[0][1], mejor[1][0], mejor[1][1]), fill=_AZUL, width=6)


def _en_frente(punto, outline, frente: tuple[int, int, int, int]) -> tuple[float, float]:
    """El mismo encuadre que la foto: la placa queda al centro, con el margen de la cámara."""
    xs = [item[0] for item in outline]
    ys = [item[1] for item in outline]
    span_x = max(max(xs) - min(xs), 1.0)
    span_y = max(max(ys) - min(ys), 1.0)
    left, top, right, bottom = frente
    ancho = max(right - left, 1.0)
    alto = max(bottom - top, 1.0)
    escala_x = ancho / (span_x * MARGEN_FOTO)
    escala_y = alto / (span_y * MARGEN_FOTO)
    return (
        (left + right) / 2.0 + (float(punto[0]) - (min(xs) + max(xs)) / 2.0) * escala_x,
        (top + bottom) / 2.0 - (float(punto[1]) - (min(ys) + max(ys)) / 2.0) * escala_y,
    )


def _filete(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    *,
    leg: str,
    pitch: str,
    both: bool,
    typ: bool,
    other: str = "",
) -> None:
    font = _font(22)
    draw.line((x, y, x + 150, y), fill=_LINEA, width=2)
    _triangulo(draw, x + 28, y, up=True)
    if both:
        _triangulo(draw, x + 28, y, up=False)
    if leg:
        draw.text((x + 8, y - 32), leg, fill=_SIMBOLO, font=font)
        if both:
            draw.text((x + 8, y + 8), other or leg, fill=_SIMBOLO, font=font)
    if pitch:
        draw.text((x + 52, y - 32), pitch, fill=_TEXTO, font=font)
        if both:
            draw.text((x + 52, y + 8), pitch, fill=_TEXTO, font=font)
    if typ:
        draw.text((x + 168, y - 14), "TYP", fill=_TEXTO, font=font)


def _triangulo(draw: ImageDraw.ImageDraw, x: int, y: int, *, up: bool) -> None:
    if up:
        points = [(x, y), (x + 22, y), (x + 11, y - 18)]
    else:
        points = [(x, y), (x + 22, y), (x + 11, y + 18)]
    draw.polygon(points, outline=_SIMBOLO)
    draw.line(points + [points[0]], fill=_SIMBOLO, width=2)
