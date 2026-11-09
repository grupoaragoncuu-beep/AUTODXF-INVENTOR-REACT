"""Acotación de maquinado desde la geometría del sólido, no desde el corte 2D.

Una pieza redonda se mira por su eje: cada diámetro, el barreno que la atraviesa
y el largo de cada escalón. Una placa se mira de frente: ancho, alto, espesor
y barrenos (diámetro, paso o distancia entre centros). No hay origen (0,0).
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from drawing_jpg import _px_cota

CM_POR_UNIDAD = {"in": 2.54, "mm": 0.1}
COAXIAL_CM = 0.08
RADIO_CM = 0.03
ARCO_LLENO = math.radians(300)
PASADO_FRACCION = 0.85
REDONDO = 0.82
MIN_LARGO_CM = 0.05

_AZUL = (20, 72, 140)
_TINTA = (28, 36, 44)
_SUAVE = (150, 158, 166)
_FONDO = (255, 255, 255)


def _v(a) -> np.ndarray:
    return np.asarray(a, dtype=float)


def _unit(a) -> np.ndarray | None:
    a = _v(a)
    n = float(np.linalg.norm(a))
    return None if n < 1e-12 else a / n


def _fmt(valor: float) -> str:
    texto = f"{abs(float(valor)):.3f}".rstrip("0").rstrip(".")
    if "." not in texto:
        texto += ".00"
    elif len(texto.split(".")[1]) == 1:
        texto += "0"
    return texto


def _a_unidad(cm: float, unidad: str) -> float:
    return float(cm) / CM_POR_UNIDAD.get(str(unidad).lower(), 2.54)


def _puntos(defn: dict) -> np.ndarray:
    trozos = [a["pts"] for a in defn.get("aristas") or [] if a.get("pts") is not None and len(a["pts"])]
    if not trozos:
        return np.zeros((0, 3))
    return _v(np.concatenate(trozos)).reshape(-1, 3)


def _circulos(defn: dict) -> list[dict]:
    """Arcos del mismo círculo (Inventor los parte) unidos en uno solo si cierran."""
    grupos: list[dict] = []
    for arista in defn.get("aristas") or []:
        crudo = arista.get("circ")
        if not crudo or float(crudo.get("barrido") or 0) < math.radians(40):
            continue
        normal = _unit(crudo["n"])
        if normal is None:
            continue
        if normal[int(np.argmax(np.abs(normal)))] < 0:
            normal = -normal
        centro = _v(crudo["c"])
        radio = float(crudo["r"])
        for grupo in grupos:
            if abs(grupo["r"] - radio) > RADIO_CM:
                continue
            if float(np.dot(grupo["n"], normal)) < 0.98:
                continue
            if float(np.linalg.norm(grupo["c"] - centro)) > RADIO_CM:
                continue
            grupo["barrido"] = min(2 * math.pi, grupo["barrido"] + float(crudo["barrido"]))
            break
        else:
            grupos.append({"c": centro, "n": normal, "r": radio, "barrido": float(crudo["barrido"])})
    return [g for g in grupos if g["barrido"] >= ARCO_LLENO]


def _base(eje: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    arriba = np.array([0.0, 1.0, 0.0])
    if abs(float(np.dot(eje, arriba))) > 0.9:
        arriba = np.array([1.0, 0.0, 0.0])
    u = _unit(np.cross(arriba, eje))
    v = _unit(np.cross(eje, u))
    return u, v


def _proyectar(pts: np.ndarray, origen, u, v) -> np.ndarray:
    d = pts - _v(origen)
    return np.stack([d @ u, d @ v], axis=1)


def _agrupar_centros(circulos: list[dict], u, v) -> list[list[dict]]:
    grupos: list[list[dict]] = []
    for circulo in circulos:
        xy = np.array([float(np.dot(circulo["c"], u)), float(np.dot(circulo["c"], v))])
        for grupo in grupos:
            ref = grupo[0]
            otro = np.array([float(np.dot(ref["c"], u)), float(np.dot(ref["c"], v))])
            if float(np.linalg.norm(xy - otro)) <= COAXIAL_CM:
                grupo.append(circulo)
                break
        else:
            grupos.append([circulo])
    return grupos


def _a_lo_largo(circulo: dict, eje: np.ndarray) -> float:
    return float(np.dot(circulo["c"], eje))


def _perfil(pasos: list[dict], t0: float, t1: float) -> list[tuple[float, float, float]]:
    """Radio exterior por tramo. El barreno pasado no es el contorno: es el hueco."""
    cuerpos = [p for p in pasos if not p.get("pasado")]
    if not cuerpos:
        return [(t0, t1, max((p["r"] for p in pasos), default=1.0))]
    marcas = sorted({t0, t1, *[p["t0"] for p in pasos], *[p["t1"] for p in pasos]})
    tramos = []
    for a, b in zip(marcas, marcas[1:]):
        if b - a < 1e-4:
            continue
        medio = (a + b) / 2
        cubre = [p for p in cuerpos if p["t0"] - 1e-3 <= medio <= p["t1"] + 1e-3]
        if not cubre:
            cubre = [
                p
                for p in cuerpos
                if min(abs(p["t0"] - a), abs(p["t1"] - a), abs(p["t0"] - b), abs(p["t1"] - b)) <= 1e-3
            ]
        if cubre:
            tramos.append((a, b, max(p["r"] for p in cubre)))
    unidos = []
    for a, b, r in tramos:
        if unidos and abs(unidos[-1][2] - r) <= RADIO_CM and abs(unidos[-1][1] - a) < 1e-3:
            unidos[-1] = (unidos[-1][0], b, unidos[-1][2])
        else:
            unidos.append((a, b, r))
    return unidos or [(t0, t1, max(p["r"] for p in cuerpos))]


def _segmentos(defn: dict, origen, u, v) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    salida = []
    for arista in defn.get("aristas") or []:
        pts = arista.get("pts")
        if pts is None or len(pts) < 2:
            continue
        xy = _proyectar(_v(pts), origen, u, v)
        for a, b in zip(xy[:-1], xy[1:]):
            if float(np.linalg.norm(a - b)) < 1e-4:
                continue
            salida.append(((float(a[0]), float(a[1])), (float(b[0]), float(b[1]))))
    return salida


def morfologia(defn: dict) -> dict | None:
    """`revolucion` si el sólido es redondo sobre un eje; si no, `placa` vista de frente."""
    pts = _puntos(defn)
    if len(pts) < 3:
        return None
    circulos = _circulos(defn)
    if circulos:
        eje = circulos[0]["n"]
        grupos_eje: dict[tuple, list[dict]] = {}
        for circulo in circulos:
            grupos_eje.setdefault(tuple(np.round(circulo["n"], 3)), []).append(circulo)
        eje = _v(max(grupos_eje, key=lambda n: max(c["r"] for c in grupos_eje[n])))
    else:
        planos = defn.get("planos") or []
        if not planos:
            return None
        eje = _unit(planos[0]["n"])
        if eje is None:
            return None
    u, v = _base(eje)
    grupos = _agrupar_centros(circulos, u, v) if circulos else []
    eje_grupo = max(grupos, key=lambda g: max(c["r"] for c in g)) if grupos else []
    if eje_grupo:
        origen = np.mean([c["c"] for c in eje_grupo], axis=0)
    else:
        origen = pts.mean(axis=0)
    t = (pts - origen) @ eje
    t0, t1 = float(t.min()), float(t.max())
    rho = np.linalg.norm((pts - origen) - t[:, None] * eje, axis=1)
    rho_max = float(rho.max()) if len(rho) else 0.0
    r_eje = max((c["r"] for c in eje_grupo), default=0.0)
    revolucion = bool(eje_grupo) and rho_max > 0 and r_eje >= REDONDO * rho_max

    if revolucion:
        otros = [c for g in grupos if g is not eje_grupo for c in g]
        return _revolucion(defn, pts, eje, origen, u, v, t0, t1, eje_grupo, otros)
    return _placa(defn, pts, eje, origen, u, v, t0, t1, circulos)


def _pasos_coaxiales(circulos: list[dict], eje, t0: float, t1: float) -> list[dict]:
    radios: list[dict] = []
    for circulo in sorted(circulos, key=lambda c: c["r"]):
        t = _a_lo_largo(circulo, eje)
        for paso in radios:
            if abs(paso["r"] - circulo["r"]) <= RADIO_CM:
                paso["t0"] = min(paso["t0"], t)
                paso["t1"] = max(paso["t1"], t)
                break
        else:
            radios.append({"r": float(circulo["r"]), "t0": t, "t1": t})
    largo = max(t1 - t0, 1e-6)
    for paso in radios:
        paso["pasado"] = (paso["t1"] - paso["t0"]) >= PASADO_FRACCION * largo and paso["r"] < 0.92 * max(
            p["r"] for p in radios
        )
        paso["escalon"] = MIN_LARGO_CM < (paso["t1"] - paso["t0"]) < PASADO_FRACCION * largo
    return radios


def _revolucion(defn, pts, eje, origen, u, v, t0, t1, coaxiales, otros) -> dict:
    pasos = _pasos_coaxiales(coaxiales, eje, t0, t1)
    barrenos = _barrenos(otros, eje, origen, u, v, t0, t1)
    return {
        "kind": "revolucion",
        "eje": eje,
        "origen": origen,
        "u": u,
        "v": v,
        "t0": t0,
        "t1": t1,
        "pasos": pasos,
        "barrenos": barrenos,
        "silueta": _perfil(pasos, t0, t1),
        "barreno_r": next((p["r"] for p in pasos if p.get("pasado")), None),
        "circulos": [
            {"x": float(np.dot(c["c"] - origen, u)), "y": float(np.dot(c["c"] - origen, v)), "r": c["r"]}
            for c in coaxiales + otros
        ],
        "segmentos": [],
    }


def _barrenos(circulos: list[dict], eje, origen, u, v, t0: float, t1: float) -> list[dict]:
    """Agujeros fuera del eje, agrupados por diámetro. Un barreno = un centro."""
    if not circulos:
        return []
    grupos = _agrupar_centros(circulos, u, v)
    por_radio: list[dict] = []
    largo = max(t1 - t0, 1e-6)
    for grupo in grupos:
        radio = float(np.median([c["r"] for c in grupo]))
        ts = [_a_lo_largo(c, eje) for c in grupo]
        centro = np.mean([c["c"] for c in grupo], axis=0) - _v(origen)
        xy = np.array([float(np.dot(centro, u)), float(np.dot(centro, v))])
        for cubo in por_radio:
            if abs(cubo["r"] - radio) <= RADIO_CM:
                cubo["centros"].append(xy)
                cubo["t0"] = min(cubo["t0"], min(ts))
                cubo["t1"] = max(cubo["t1"], max(ts))
                break
        else:
            por_radio.append({"r": radio, "centros": [xy], "t0": min(ts), "t1": max(ts)})
    for cubo in por_radio:
        radios = [float(np.linalg.norm(c)) for c in cubo["centros"]]
        media = float(np.mean(radios)) if radios else 0.0
        cubo["bcd"] = 2 * media if len(cubo["centros"]) >= 3 and media > cubo["r"] and (
            max(radios) - min(radios) <= max(0.08, 0.04 * media)
        ) else None
        cubo["pasado"] = (cubo["t1"] - cubo["t0"]) >= PASADO_FRACCION * largo
    return por_radio


def _placa(defn, pts, eje, origen, u, v, t0, t1, circulos) -> dict:
    xy = _proyectar(pts, origen, u, v)
    largo_u = float(xy[:, 0].max() - xy[:, 0].min())
    largo_v = float(xy[:, 1].max() - xy[:, 1].min())
    if largo_v > largo_u:
        u, v = v, -u
        xy = _proyectar(pts, origen, u, v)
    barrenos = _barrenos(circulos, eje, origen, u, v, t0, t1)
    # En placa el BCD se mide desde el centro de la cara, no desde un eje de revolución.
    for cubo in barrenos:
        cubo["bcd"] = None
        if len(cubo["centros"]) >= 3:
            medio = np.mean(cubo["centros"], axis=0)
            radios = [float(np.linalg.norm(c - medio)) for c in cubo["centros"]]
            media = float(np.mean(radios))
            if media > cubo["r"] and max(radios) - min(radios) <= max(0.08, 0.04 * media):
                cubo["bcd"] = 2 * media
                cubo["centro_bcd"] = medio
    return {
        "kind": "placa",
        "eje": eje,
        "origen": origen,
        "u": u,
        "v": v,
        "t0": t0,
        "t1": t1,
        "pasos": [],
        "barrenos": barrenos,
        "silueta": [],
        "circulos": [],
        "segmentos": _segmentos(defn, origen, u, v),
        "ancho": float(xy[:, 0].max() - xy[:, 0].min()) if largo_v > largo_u else largo_u,
        "alto": float(xy[:, 1].max() - xy[:, 1].min()) if largo_v > largo_u else largo_v,
    }


def _cota(kind: str, cm: float, unidad: str, **extra) -> dict:
    valor = _a_unidad(cm, unidad)
    return {"kind": kind, "cm": float(cm), "value": valor, "view": extra.pop("view"), **extra}


def cotas_de(morf: dict | None, unidad: str = "in") -> list[dict]:
    """Una cota por diámetro, barreno, escalón o tamaño de placa. Sin coordenadas de origen."""
    if not morf:
        return []
    unidad_txt = "mm" if str(unidad).lower() == "mm" else "in"
    cotas: list[dict] = []
    if morf["kind"] == "revolucion":
        for paso in morf["pasos"]:
            nombre = f"D_{_fmt(_a_unidad(2 * paso['r'], unidad))}"
            if paso["pasado"]:
                nombre += "_PASADO"
            cotas.append(
                _cota(
                    "D",
                    2 * paso["r"],
                    unidad,
                    view="frente",
                    name=nombre,
                    r=paso["r"],
                    pasado=bool(paso["pasado"]),
                    donde="eje",
                )
            )
            if paso["escalon"]:
                cotas.append(
                    _cota(
                        "STEP",
                        paso["t1"] - paso["t0"],
                        unidad,
                        view="perfil",
                        name=f"STEP_{_fmt(_a_unidad(paso['t1'] - paso['t0'], unidad))}_D{_fmt(_a_unidad(2 * paso['r'], unidad))}",
                        t0=paso["t0"],
                        t1=paso["t1"],
                        r=paso["r"],
                    )
                )
        cotas.append(
            _cota(
                "L",
                morf["t1"] - morf["t0"],
                unidad,
                view="perfil",
                name=f"L_{_fmt(_a_unidad(morf['t1'] - morf['t0'], unidad))}",
                t0=morf["t0"],
                t1=morf["t1"],
            )
        )
    else:
        cotas.append(_cota("W", morf["ancho"], unidad, view="frente", name=f"W_{_fmt(_a_unidad(morf['ancho'], unidad))}"))
        cotas.append(_cota("H", morf["alto"], unidad, view="frente", name=f"H_{_fmt(_a_unidad(morf['alto'], unidad))}"))
        cotas.append(
            _cota(
                "THK",
                morf["t1"] - morf["t0"],
                unidad,
                view="perfil",
                name=f"THK_{_fmt(_a_unidad(morf['t1'] - morf['t0'], unidad))}",
                t0=morf["t0"],
                t1=morf["t1"],
            )
        )
    for cubo in morf["barrenos"]:
        nombre = f"D_{_fmt(_a_unidad(2 * cubo['r'], unidad))}"
        if cubo["pasado"]:
            nombre += "_PASADO"
        if len(cubo["centros"]) > 1:
            nombre += "_TYP"
        cotas.append(
            _cota(
                "D",
                2 * cubo["r"],
                unidad,
                view="frente",
                name=nombre,
                r=cubo["r"],
                pasado=bool(cubo["pasado"]),
                typ=len(cubo["centros"]) > 1,
                donde="barreno",
                centros=cubo["centros"],
            )
        )
        if cubo.get("bcd"):
            cotas.append(
                _cota(
                    "BCD",
                    cubo["bcd"],
                    unidad,
                    view="frente",
                    name=f"BCD_{_fmt(_a_unidad(cubo['bcd'], unidad))}",
                    r=cubo["bcd"] / 2,
                    centros=cubo["centros"],
                    centro=cubo.get("centro_bcd"),
                )
            )
        elif len(cubo["centros"]) == 2:
            dist = float(np.linalg.norm(_v(cubo["centros"][0]) - _v(cubo["centros"][1])))
            cotas.append(
                _cota(
                    "CC",
                    dist,
                    unidad,
                    view="frente",
                    name=f"CC_{_fmt(_a_unidad(dist, unidad))}",
                    centros=cubo["centros"],
                )
            )
    for cota in cotas:
        sufijo = " PASADO" if cota.get("pasado") else ""
        if cota.get("typ"):
            sufijo += " TYP"
        prefijo = {"D": "Ø", "BCD": "BCD", "CC": "CC", "L": "L", "STEP": "STEP", "W": "W", "H": "H", "THK": "THK"}[
            cota["kind"]
        ]
        cota["label"] = f"{prefijo} {_fmt(cota['value'])}{sufijo} {unidad_txt}"
        cota["name"] = cota["name"].replace(" ", "_")
    vistos = set()
    unicas = []
    for cota in cotas:
        if cota["name"] in vistos:
            continue
        vistos.add(cota["name"])
        unicas.append(cota)
    return unicas


# ---------------------------------------------------------------- dibujo

def _fuente(px: int):
    for ruta in (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\segoeui.ttf"):
        if Path(ruta).is_file():
            return ImageFont.truetype(ruta, px)
    return ImageFont.load_default()


def _flecha(draw: ImageDraw.ImageDraw, a, b, color, ancho: int = 2) -> None:
    draw.line([a, b], fill=color, width=ancho)
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    for signo, origen in ((1, a), (-1, b)):
        p1 = (origen[0] + 9 * math.cos(ang + signo * 2.6), origen[1] + 9 * math.sin(ang + signo * 2.6))
        p2 = (origen[0] + 9 * math.cos(ang - signo * 2.6), origen[1] + 9 * math.sin(ang - signo * 2.6))
        draw.polygon([origen, p1, p2], fill=color)


def dibujar(dest: str | Path, morf: dict, cota: dict, titulo: str) -> str:
    """Un JPG: la vista (frente o perfil) y una sola cota, sin marca de origen."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if cota["view"] == "perfil" and morf["kind"] == "revolucion":
        imagen = _dibujo_perfil(morf, cota, titulo)
    elif cota["kind"] == "THK":
        imagen = _dibujo_espesor(morf, cota, titulo)
    else:
        imagen = _dibujo_frente(morf, cota, titulo)
    imagen.save(dest, "JPEG", quality=92)
    return str(dest)


def _encuadre(puntos: list[tuple[float, float]], extra: float = 0.0):
    xs = [p[0] for p in puntos] or [0.0]
    ys = [p[1] for p in puntos] or [0.0]
    x0, x1 = min(xs) - extra, max(xs) + extra
    y0, y1 = min(ys) - extra, max(ys) + extra
    if x1 - x0 < 1e-3:
        x0, x1 = x0 - 1, x1 + 1
    if y1 - y0 < 1e-3:
        y0, y1 = y0 - 1, y1 + 1
    return x0, y0, x1, y1


def _medida_cota(texto: str):
    font = _fuente(_px_cota(28))
    dummy = ImageDraw.Draw(Image.new("RGB", (4, 4)))
    box = dummy.textbbox((0, 0), texto, font=font)
    return font, max(1, box[2] - box[0]), max(1, box[3] - box[1])


def _lienzo(x0, y0, x1, y1, margenes=(80, 80, 48, 80)):
    """La pieza ocupa la zona útil. El margen, en pixeles, es para la letra."""
    ml, mr, mt, mb = margenes
    zona_x, zona_y = 1100, 760
    ancho = int(ml + mr + zona_x)
    alto = int(mt + mb + zona_y)
    escala = min(zona_x / (x1 - x0), zona_y / (y1 - y0))

    def px(x: float, y: float) -> tuple[float, float]:
        return (ml + (x - x0) * escala, mt + (y1 - y) * escala)

    imagen = Image.new("RGB", (ancho, alto), _FONDO)
    return imagen, ImageDraw.Draw(imagen), px


def _lado_libre(fx: float, fy: float, x0: float, y0: float, x1: float, y1: float) -> str:
    """Lado de la pieza más cercano al punto. Y mundo hacia arriba."""
    dist = {"izq": fx - x0, "der": x1 - fx, "arriba": y1 - fy, "abajo": fy - y0}
    return min(dist, key=dist.get)


def _margenes(lado: str, tw: int, th: int) -> tuple[int, int, int, int]:
    ml, mr, mt, mb = 56, 56, 40, 40
    if lado == "izq":
        ml = tw + 88
    elif lado == "der":
        mr = tw + 88
    elif lado == "arriba":
        mt = th + 64
    else:
        mb = th + 64
    return ml, mr, mt, mb


def _caja_pieza(px, x0, y0, x1, y1) -> tuple[float, float, float, float]:
    a, b = px(x0, y0), px(x1, y1)
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))


def _etiqueta_fuera(draw, imagen, fx, fy, lado, texto, font, tw, th, pieza) -> None:
    """Letra fuera del rectángulo de la pieza. El trazo sale del punto de la cota."""
    izq, arr, der, aba = pieza
    ancho, alto = imagen.size
    gap = 18
    if lado == "arriba":
        y = arr - gap
        x = min(max(fx, tw / 2 + 8), ancho - tw / 2 - 8)
        draw.line((fx, fy, x, y), fill=_AZUL, width=1)
        draw.text((x, y), texto, fill=_AZUL, font=font, anchor="mb")
    elif lado == "abajo":
        y = aba + gap
        x = min(max(fx, tw / 2 + 8), ancho - tw / 2 - 8)
        draw.line((fx, fy, x, y), fill=_AZUL, width=1)
        draw.text((x, y), texto, fill=_AZUL, font=font, anchor="mt")
    elif lado == "der":
        x = der + gap
        y = min(max(fy, th / 2 + 8), alto - th / 2 - 8)
        draw.line((fx, fy, x, y), fill=_AZUL, width=1)
        draw.text((x, y), texto, fill=_AZUL, font=font, anchor="lm")
    else:
        x = izq - gap
        y = min(max(fy, th / 2 + 8), alto - th / 2 - 8)
        draw.line((fx, fy, x, y), fill=_AZUL, width=1)
        draw.text((x, y), texto, fill=_AZUL, font=font, anchor="rm")


def _dibujo_frente(morf: dict, cota: dict, titulo: str) -> Image.Image:
    _ = titulo
    pts = []
    for a, b in morf.get("segmentos") or []:
        pts.extend((a, b))
    for circulo in morf.get("circulos") or []:
        pts.extend(((circulo["x"] - circulo["r"], circulo["y"] - circulo["r"]), (circulo["x"] + circulo["r"], circulo["y"] + circulo["r"])))
    for cubo in morf.get("barrenos") or []:
        for centro in cubo["centros"]:
            pts.append((float(centro[0]), float(centro[1])))
    gx0, gy0, gx1, gy1 = _encuadre(pts, extra=0.0)
    pad = max(gx1 - gx0, gy1 - gy0, 1.0) * 0.04
    font, tw, th = _medida_cota(str(cota.get("label") or ""))
    lado = "der"
    if cota["kind"] == "H":
        lado = "izq"
    elif cota["kind"] == "W":
        lado = "abajo"
    elif cota["kind"] == "BCD":
        centro = cota.get("centro") or (0.0, 0.0)
        rr = max(float(cota.get("r") or 0), 0.0)
        cx, cy = float(centro[0]), float(centro[1])
        gx0, gy0 = min(gx0, cx - rr), min(gy0, cy - rr)
        gx1, gy1 = max(gx1, cx + rr), max(gy1, cy + rr)
        lado = _lado_libre(cx + rr, cy, gx0, gy0, gx1, gy1)
    elif cota["kind"] == "D" and cota.get("donde") == "barreno" and cota.get("centros"):
        centro = cota["centros"][0]
        lado = _lado_libre(float(centro[0]), float(centro[1]), gx0, gy0, gx1, gy1)
    elif cota["kind"] == "D":
        rr = max(float(cota.get("r") or 0), 0.0)
        lado = _lado_libre(rr, 0.0, min(gx0, -rr), min(gy0, -rr), max(gx1, rr), max(gy1, rr))
    elif cota["kind"] == "CC" and cota.get("centros"):
        a, b = cota["centros"]
        lado = _lado_libre(
            (float(a[0]) + float(b[0])) / 2,
            (float(a[1]) + float(b[1])) / 2,
            gx0, gy0, gx1, gy1,
        )
    x0, y0, x1, y1 = gx0 - pad, gy0 - pad, gx1 + pad, gy1 + pad
    imagen, draw, px = _lienzo(x0, y0, x1, y1, _margenes(lado, tw, th))
    for a, b in morf.get("segmentos") or []:
        draw.line([px(*a), px(*b)], fill=_TINTA, width=2)
    foco_r = float(cota.get("r") or -1)
    if morf["kind"] == "revolucion":
        _centro(draw, px, 0.0, 0.0, 18)
    for circulo in morf.get("circulos") or []:
        activo = cota["kind"] == "D" and cota.get("donde") == "eje" and abs(circulo["r"] - foco_r) <= RADIO_CM and abs(circulo["x"]) < 1e-3 and abs(circulo["y"]) < 1e-3
        _circulo(draw, px, circulo["x"], circulo["y"], circulo["r"], _AZUL if activo else _TINTA, 4 if activo else 2)
    for cubo in morf.get("barrenos") or []:
        activo = cota["kind"] == "D" and cota.get("donde") == "barreno" and abs(cubo["r"] - foco_r) <= RADIO_CM
        for centro in cubo["centros"]:
            _circulo(draw, px, float(centro[0]), float(centro[1]), cubo["r"], _AZUL if activo else _TINTA, 4 if activo else 2)
    pieza = _caja_pieza(px, gx0, gy0, gx1, gy1)
    izq, arr, der, aba = pieza
    if cota["kind"] == "D" and cota.get("donde") == "eje":
        _flecha(draw, px(-foco_r, 0.0), px(foco_r, 0.0), _AZUL, 3)
        sx, sy = px(*_salida(0.0, 0.0, foco_r, lado))
        _etiqueta_fuera(draw, imagen, sx, sy, lado, cota["label"], font, tw, th, pieza)
    elif cota["kind"] == "D" and cota.get("donde") == "barreno":
        centro = cota["centros"][0]
        cx, cy = float(centro[0]), float(centro[1])
        _flecha(draw, px(cx - foco_r, cy), px(cx + foco_r, cy), _AZUL, 3)
        sx, sy = px(*_salida(cx, cy, foco_r, lado))
        _etiqueta_fuera(draw, imagen, sx, sy, lado, cota["label"], font, tw, th, pieza)
    elif cota["kind"] == "BCD":
        centro = cota.get("centro")
        cx = float(centro[0]) if centro is not None else 0.0
        cy = float(centro[1]) if centro is not None else 0.0
        _circulo(draw, px, cx, cy, foco_r, _AZUL, 2)
        _flecha(draw, px(cx - foco_r, cy), px(cx + foco_r, cy), _AZUL, 3)
        sx, sy = px(*_salida(cx, cy, foco_r, lado))
        _etiqueta_fuera(draw, imagen, sx, sy, lado, cota["label"], font, tw, th, pieza)
    elif cota["kind"] == "CC":
        a, b = cota["centros"]
        _flecha(draw, px(float(a[0]), float(a[1])), px(float(b[0]), float(b[1])), _AZUL, 3)
        mx = (float(a[0]) + float(b[0])) / 2
        my = (float(a[1]) + float(b[1])) / 2
        sx, sy = px(mx, my)
        _etiqueta_fuera(draw, imagen, sx, sy, lado, cota["label"], font, tw, th, pieza)
    elif cota["kind"] == "W":
        dim_y = aba + 28
        _flecha(draw, (izq, dim_y), (der, dim_y), _AZUL, 3)
        draw.line((izq, aba, izq, dim_y), fill=_AZUL, width=1)
        draw.line((der, aba, der, dim_y), fill=_AZUL, width=1)
        draw.text(((izq + der) / 2, dim_y + 12), cota["label"], fill=_AZUL, font=font, anchor="mt")
    elif cota["kind"] == "H":
        dim_x = izq - 28
        _flecha(draw, (dim_x, arr), (dim_x, aba), _AZUL, 3)
        draw.line((izq, arr, dim_x, arr), fill=_AZUL, width=1)
        draw.line((izq, aba, dim_x, aba), fill=_AZUL, width=1)
        draw.text((dim_x - 14, (arr + aba) / 2), cota["label"], fill=_AZUL, font=font, anchor="rm")
    return imagen


def _salida(cx: float, cy: float, r: float, lado: str) -> tuple[float, float]:
    """Punto del borde de la cota por donde sale la letra. Y mundo hacia arriba."""
    r = max(float(r), 0.0)
    if lado == "der":
        return cx + r, cy
    if lado == "izq":
        return cx - r, cy
    if lado == "arriba":
        return cx, cy + r
    return cx, cy - r


def _dibujo_perfil(morf: dict, cota: dict, titulo: str) -> Image.Image:
    _ = titulo
    t0, t1 = morf["t0"], morf["t1"]
    tramos = morf.get("silueta") or [(t0, t1, max((p["r"] for p in morf["pasos"]), default=1.0))]
    rho_max = max(r for _a, _b, r in tramos)
    pts = [(t0, -rho_max), (t1, rho_max)]
    x0, y0, x1, y1 = _encuadre(pts, extra=max(rho_max * 0.25, 0.3))
    y0 -= rho_max * 0.45
    font, _tw, th = _medida_cota(str(cota.get("label") or ""))
    imagen, draw, px = _lienzo(x0, y0, x1, y1, (60, 60, 40, th + 72))
    contorno = []
    for a, b, r in tramos:
        contorno.append((a, r))
        contorno.append((b, r))
    superior = [px(t, r) for t, r in contorno]
    inferior = [px(t, -r) for t, r in contorno]
    if len(superior) >= 2:
        draw.line(superior, fill=_TINTA, width=3)
        draw.line(inferior, fill=_TINTA, width=3)
        draw.line([superior[0], inferior[0]], fill=_TINTA, width=3)
        draw.line([superior[-1], inferior[-1]], fill=_TINTA, width=3)
    draw.line([px(t0, 0), px(t1, 0)], fill=_SUAVE, width=1)
    if morf.get("barreno_r"):
        rb = float(morf["barreno_r"])
        draw.line([px(t0, rb), px(t1, rb)], fill=_SUAVE, width=2)
        draw.line([px(t0, -rb), px(t1, -rb)], fill=_SUAVE, width=2)
    foco = (cota.get("t0", t0), cota.get("t1", t1))
    ydim = -rho_max * 1.35
    _flecha(draw, px(foco[0], ydim), px(foco[1], ydim), _AZUL, 3)
    y_hombro = float(cota["r"]) if cota.get("r") else rho_max
    draw.line([px(foco[0], y_hombro), px(foco[0], ydim)], fill=_AZUL, width=1)
    draw.line([px(foco[1], y_hombro), px(foco[1], ydim)], fill=_AZUL, width=1)
    p0, p1 = px(foco[0], ydim), px(foco[1], ydim)
    draw.text(((p0[0] + p1[0]) / 2, max(p0[1], p1[1]) + 14), cota["label"], fill=_AZUL, font=font, anchor="mt")
    return imagen


def _dibujo_espesor(morf: dict, cota: dict, titulo: str) -> Image.Image:
    _ = titulo
    largo = max(float(morf.get("ancho") or 1), float(morf.get("alto") or 1))
    thk = max(morf["t1"] - morf["t0"], 0.05)
    font, tw, th_px = _medida_cota(str(cota.get("label") or ""))
    x0, y0, x1, y1 = -thk * 0.5, -thk * 0.45, largo + thk * 0.15, thk * 1.45
    imagen, draw, px = _lienzo(x0, y0, x1, y1, (tw + 88, 36, max(48, th_px), max(48, th_px)))
    a, b = px(0, 0), px(largo, thk)
    izq, arr = min(a[0], b[0]), min(a[1], b[1])
    aba = max(a[1], b[1])
    draw.rectangle([izq, arr, max(a[0], b[0]), aba], outline=_TINTA, width=3)
    dim_x = izq - 28
    _flecha(draw, (dim_x, aba), (dim_x, arr), _AZUL, 3)
    draw.line((dim_x, arr, izq, arr), fill=_AZUL, width=1)
    draw.line((dim_x, aba, izq, aba), fill=_AZUL, width=1)
    draw.text((dim_x - 14, (arr + aba) / 2), cota["label"], fill=_AZUL, font=font, anchor="rm")
    return imagen


def _circulo(draw, px, cx, cy, r, color, ancho: int) -> None:
    x0, y0 = px(cx - r, cy - r)
    x1, y1 = px(cx + r, cy + r)
    draw.ellipse([min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)], outline=color, width=ancho)


def _centro(draw, px, cx, cy, radio_px: float) -> None:
    c = px(cx, cy)
    draw.line([(c[0] - radio_px, c[1]), (c[0] + radio_px, c[1])], fill=_SUAVE, width=1)
    draw.line([(c[0], c[1] - radio_px), (c[0], c[1] + radio_px)], fill=_SUAVE, width=1)

