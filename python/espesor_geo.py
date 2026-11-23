"""Puntos de espesor de pintura. Cálculo puro, sin Inventor y sin base de datos.

Thermox y Poliuretano miden la cara interna. Zinc y Macro mide la cara externa.
El texto del plan manda 9 en tapa y 9 en base para Thermox y Poliuretano.
La figura de Poliuretano del Word marcaba 4; eso queda como aviso, no como recorte.
"""

from __future__ import annotations

ESQUEMAS = ("thermox", "zinc_macro", "poliuretano")

# Fracción del ancho (desde la izquierda) y del alto (desde abajo).
FILA = {"superior": 0.84, "media": 0.50, "inferior": 0.16}
COL = {"izquierda": 0.14, "medio": 0.50, "derecha": 0.86}

# Reparto fijo. El plan dice «aleatorias»; el mismo tanque tiene que salir igual.
ALEATORIAS = {
    4: ((0.18, 0.74), (0.55, 0.80), (0.76, 0.52), (0.40, 0.24)),
    9: (
        (0.16, 0.84),
        (0.46, 0.76),
        (0.74, 0.86),
        (0.24, 0.56),
        (0.52, 0.48),
        (0.78, 0.58),
        (0.18, 0.22),
        (0.48, 0.16),
        (0.74, 0.28),
    ),
}

OCULTAS = ("jacking", "brace", "cartabon", "valvula")
NOMBRE_OCULTA = {
    "jacking": "Jacking Pad",
    "brace": "brace",
    "cartabon": "cartabón",
    "valvula": "válvula",
}


OPUESTO = {
    "SEGM1": "SEGM3",
    "SEGM3": "SEGM1",
    "SEGM2": "SEGM4",
    "SEGM4": "SEGM2",
    "TOP": "BASE",
    "BASE": "TOP",
}


def interior_de(cara: dict, caras: list[dict]) -> tuple[float, float, float, float]:
    """Rectángulo (u0, u1, v0, v1) del hueco del tanque visto en esta cara: lo cierran las otras pieles."""
    u, v = cara["u"], cara["v"]
    a = float(cara["u0"])
    b = a + float(cara["ancho"])
    c = float(cara["v0"])
    d = c + float(cara["alto"])
    for otra in caras:
        if otra is cara or otra.get("normal") is None or otra.get("plano") is None:
            continue
        plano = float(otra["plano"])
        du = float(_dot(otra["normal"], u))
        dv = float(_dot(otra["normal"], v))
        if du > 0.9:
            b = max(b, plano)
        elif du < -0.9:
            a = min(a, -plano)
        if dv > 0.9:
            d = max(d, plano)
        elif dv < -0.9:
            c = min(c, -plano)
    return a, b, c, d


def claro_de(cara: dict, caras: list[dict]) -> float | None:
    """Distancia de esta piel a la contraria, medida sobre la normal."""
    contraria = next((otra for otra in caras if otra.get("codigo") == OPUESTO.get(cara.get("codigo"))), None)
    if contraria is None or cara.get("plano") is None or contraria.get("plano") is None:
        return None
    claro = float(cara["plano"]) + float(contraria["plano"])
    return claro if claro > 20.0 else None


def contenida(xs: list[float], ys: list[float], interior, margen: float = 8.0) -> bool:
    """La pieza vive dentro del hueco del tanque; lo que sobresale de las pieles es de afuera."""
    a, b, c, d = interior
    return min(xs) >= a - margen and max(xs) <= b + margen and min(ys) >= c - margen and max(ys) <= d + margen


def lado_vista(esquema: str) -> str:
    """Thermox y Poliuretano: alzado desde dentro. Zinc y Macro: desde fuera."""
    if esquema == "zinc_macro":
        return "fuera"
    return "dentro"


def entra_en_alzado(
    d0: float,
    d1: float,
    plano: float,
    lado: str,
    holgura: float = 8.0,
    hasta: float | None = None,
) -> bool:
    """d0/d1 son la profundidad sobre la normal que apunta afuera. Mayor = más afuera.

    Por dentro entra la piel y lo que vive hacia el interior.
    Una boquilla, un registro o una escalera cuyo centro está afuera no entra.
    `hasta` es el plano de la media sección: lo que queda entero en la mitad
    del muro contrario no se fotografía.
    """
    lo, hi = (float(d0), float(d1)) if float(d0) <= float(d1) else (float(d1), float(d0))
    plano = float(plano)
    centro = (lo + hi) / 2.0
    if lado == "dentro":
        if centro > plano + 2.0:
            return False
        if hasta is not None:
            return hi >= float(hasta)
        return hi >= plano - max(float(holgura), 120.0)
    if hi < plano - float(holgura):
        return False
    return lo <= plano + 35.0


def clase_oculta(nombre: str) -> str | None:
    texto = str(nombre or "").casefold()
    if "jacking" in texto:
        return "jacking"
    if "cartab" in texto or "cartag" in texto or "gusset" in texto:
        return "cartabon"
    if "valv" in texto:
        return "valvula"
    if "brace" in texto:
        return "brace"
    return None


def plan_cara(
    esquema: str,
    clase: str,
    ancho: float,
    alto: float,
    partes: list[dict] | None = None,
) -> tuple[list[dict], list[str]]:
    """Puntos en la cara. x desde la izquierda, y desde abajo, mismas unidades que ancho/alto."""
    if esquema not in ESQUEMAS:
        raise ValueError(f"Esquema desconocido: {esquema}")
    if clase not in {"muro", "top", "base"}:
        raise ValueError(f"Cara desconocida: {clase}")
    ancho = float(ancho)
    alto = float(alto)
    partes = list(partes or [])
    avisos: list[str] = []
    if clase == "muro":
        puntos = _muro(esquema, ancho, alto)
        if esquema == "poliuretano":
            avisos.extend(ajustar_braces(puntos, partes, alto))
            ocultos, faltan = puntos_ocultos(partes, ancho, alto)
            puntos.extend(ocultos)
            avisos.extend(faltan)
    else:
        puntos = _aleatorias(esquema, ancho, alto)
        if esquema == "poliuretano":
            avisos.append(
                "Tapa y base llevan 9 puntos, como el texto del plan. "
                "La figura del Word marcaba 4."
            )
    _numerar(puntos)
    return puntos, avisos


def ajustar_braces(puntos: list[dict], partes: list[dict], alto: float) -> list[str]:
    """El centro de media e inferior se sienta en el brace de esa banda."""
    braces = [parte for parte in partes if clase_oculta(parte.get("nombre") or "") == "brace"]
    avisos: list[str] = []
    usados: set[int] = set()
    for punto in puntos:
        if punto.get("columna") != "brace":
            continue
        mejor = None
        mejor_d = None
        for indice, parte in enumerate(braces):
            if indice in usados:
                continue
            centro = _centro(parte)
            if _banda(centro[1], alto) != punto["banda"]:
                continue
            dist = abs(centro[1] - float(punto["y"]))
            if mejor_d is None or dist < mejor_d:
                mejor, mejor_d = indice, dist
        if mejor is None:
            punto["aviso"] = "Sin brace en esta banda; el punto queda al centro."
            avisos.append(f"Sin brace en la banda {punto['banda']}.")
            continue
        usados.add(mejor)
        parte = braces[mejor]
        punto["y"] = _centro(parte)[1]
        punto["pieza"] = str(parte.get("nombre") or "")
        punto["aviso"] = ""
    return avisos


def puntos_ocultos(partes: list[dict], ancho: float, alto: float) -> tuple[list[dict], list[str]]:
    """Un punto debajo de cada familia: Jacking Pad, brace, cartabón, válvula."""
    grupos: dict[str, list[dict]] = {clave: [] for clave in OCULTAS}
    for parte in partes:
        clave = clase_oculta(parte.get("nombre") or "")
        if clave:
            grupos[clave].append(parte)
    puntos: list[dict] = []
    faltan: list[str] = []
    for clave in OCULTAS:
        opciones = grupos[clave]
        if not opciones:
            faltan.append(f"Sin {NOMBRE_OCULTA[clave]}.")
            continue
        parte = max(opciones, key=_area)
        x, y = _debajo(parte, ancho, alto)
        puntos.append(
            {
                "x": x,
                "y": y,
                "banda": "oculta",
                "columna": clave,
                "color": "azul",
                "grupo": "oculta",
                "pieza": str(parte.get("nombre") or ""),
                "aviso": "",
            }
        )
    return puntos, faltan


def _muro(esquema: str, ancho: float, alto: float) -> list[dict]:
    filas = ("superior", "media") if esquema == "zinc_macro" else ("superior", "media", "inferior")
    columnas = ("izquierda", "derecha") if esquema == "zinc_macro" else ("izquierda", "medio", "derecha")
    puntos = []
    for banda in filas:
        for columna in columnas:
            nombre = columna
            if esquema == "poliuretano" and columna == "medio" and banda in {"media", "inferior"}:
                nombre = "brace"
            puntos.append(
                {
                    "x": COL[columna] * ancho,
                    "y": FILA[banda] * alto,
                    "banda": banda,
                    "columna": nombre,
                    "color": "rojo",
                    "grupo": "externa" if esquema == "zinc_macro" else "interna",
                    "pieza": "",
                    "aviso": "",
                }
            )
    return puntos


def _aleatorias(esquema: str, ancho: float, alto: float) -> list[dict]:
    cantidad = 4 if esquema == "zinc_macro" else 9
    puntos = []
    for fx, fy in ALEATORIAS[cantidad]:
        puntos.append(
            {
                "x": fx * ancho,
                "y": fy * alto,
                "banda": "aleatoria",
                "columna": "",
                "color": "rojo",
                "grupo": "aleatoria",
                "pieza": "",
                "aviso": "",
            }
        )
    return puntos


def _numerar(puntos: list[dict]) -> None:
    rojo = 0
    azul = 0
    for punto in puntos:
        if punto["color"] == "azul":
            azul += 1
            punto["numero"] = azul
        else:
            rojo += 1
            punto["numero"] = rojo


def _debajo(parte: dict, ancho: float, alto: float) -> tuple[float, float]:
    cx, _cy = _centro(parte)
    y = float(parte["y0"]) - 0.045 * alto
    if y < 0.06 * alto:
        alto_parte = max(float(parte["y1"]) - float(parte["y0"]), 0.02 * alto)
        y = float(parte["y0"]) + 0.25 * alto_parte
    return _adentro(cx, ancho), _adentro(y, alto)


def _adentro(valor: float, total: float) -> float:
    if total <= 0:
        return 0.0
    return min(max(float(valor), 0.06 * total), 0.94 * total)


def _centro(parte: dict) -> tuple[float, float]:
    return (
        (float(parte["x0"]) + float(parte["x1"])) / 2,
        (float(parte["y0"]) + float(parte["y1"])) / 2,
    )


def _area(parte: dict) -> float:
    return abs(float(parte["x1"]) - float(parte["x0"])) * abs(float(parte["y1"]) - float(parte["y0"]))


def agrupar_muros(placas: list[dict]) -> dict[str, list[dict]]:
    """Agrupa placas por los 4 muros, la tapa y la base. No usa la cámara.

    Cada lista queda con la placa mayor primero. Dos chapas de la misma pared
    van juntas.
    """
    vertical: list[dict] = []
    horizontal: list[dict] = []
    for placa in placas:
        normal = _unit(placa.get("normal"))
        if normal is None or placa.get("centro") is None:
            continue
        (horizontal if abs(normal[1]) >= 0.65 else vertical).append(placa)
    if not vertical:
        return {}
    frente = _unit(max(vertical, key=lambda placa: float(placa.get("area") or 0)).get("normal"))
    if frente is None:
        return {}
    izquierda = _unit(_cross(frente, (0.0, 1.0, 0.0)))
    if izquierda is None:
        return {}
    ejes = {
        "SEGM1": frente,
        "SEGM3": _scale(frente, -1.0),
        "SEGM2": izquierda,
        "SEGM4": _scale(izquierda, -1.0),
    }
    grupos: dict[str, list[dict]] = {codigo: [] for codigo in ejes}
    for placa in vertical:
        normal = _unit(placa.get("normal"))
        if normal is None:
            continue
        mejor = None
        score = 0.7
        for codigo, eje in ejes.items():
            alineado = _dot(normal, eje)
            if alineado > score:
                mejor, score = codigo, alineado
        if mejor:
            grupos[mejor].append(placa)
    if horizontal:
        orden = sorted(horizontal, key=lambda placa: float(placa["centro"][1]))
        bajo = float(orden[0]["centro"][1])
        alto = float(orden[-1]["centro"][1])
        corte = bajo + max(15.0, 0.35 * (alto - bajo))
        grupos["BASE"] = [placa for placa in orden if float(placa["centro"][1]) <= corte]
        grupos["TOP"] = [placa for placa in orden if float(placa["centro"][1]) > corte]
    for miembros in grupos.values():
        miembros.sort(key=lambda placa: float(placa.get("area") or 0), reverse=True)
    return {codigo: miembros for codigo, miembros in grupos.items() if miembros}


def _unit(valor) -> tuple[float, float, float] | None:
    if not isinstance(valor, (list, tuple)) or len(valor) < 3:
        return None
    x, y, z = float(valor[0]), float(valor[1]), float(valor[2])
    largo = (x * x + y * y + z * z) ** 0.5
    if largo < 1e-9:
        return None
    return (x / largo, y / largo, z / largo)


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _scale(a, k: float) -> tuple[float, float, float]:
    return (a[0] * k, a[1] * k, a[2] * k)


def _banda(y: float, alto: float) -> str:
    t = y / alto if alto else 0.0
    if t >= 2 / 3:
        return "superior"
    if t >= 1 / 3:
        return "media"
    return "inferior"
