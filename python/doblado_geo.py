"""Cara de doblado desde la vista alámbrica del .ipt, sin piezas ensambladas encima.

El snapshot es CalculateStrokes + CalculateFacets de la lámina (el sólido grande).
Los otros cuerpos del mismo archivo —parches o bases que quedaron en el .ipt— no entran.
La ventana, el barreno y el slot salen del borde de la piel: si el interior del lazo
sigue siendo metal, es marcaje y no se cota.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

CM_POR_UNIDAD = {"in": 2.54, "mm": 0.1}
TOL_CM = 0.02
BIN_CM = 0.15
NORMAL = 0.98


def _v(a) -> np.ndarray:
    return np.asarray(a, dtype=float)


def _unit(a) -> np.ndarray | None:
    a = _v(a)
    n = float(np.linalg.norm(a))
    return None if n < 1e-12 else a / n


def elegir_lamina(raws: list[dict]) -> dict | None:
    """El sólido de chapa. Un parche chico, aunque también sea lámina, no gana."""
    if not raws:
        return None
    if len(raws) == 1:
        return raws[0]
    from referencia_geo import _area_laminar, preparar_def

    mejor, mejor_p = None, -1.0
    for raw in raws:
        defn = preparar_def(raw)
        area = float(_area_laminar(defn))
        puntaje = area if area > 0 else len(defn["tris"]) * 1e-9
        if puntaje > mejor_p:
            mejor, mejor_p = raw, puntaje
    return mejor


def definicion_lamina(doc) -> dict | None:
    """Snapshot de la lámina. No mezcla los sólidos que van montados en la pieza."""
    from referencia_geo import preparar_def
    from referencia_snapshot import _def_con_cache, cuerpos_crudos

    try:
        raws = cuerpos_crudos(doc)
    except Exception:
        raws = []
    if not raws:
        try:
            raws = [_def_con_cache(doc, {"cache": 0, "nuevas": 0})]
        except Exception:
            return None
    raw = elegir_lamina(raws)
    if raw is None or not (raw.get("fv") or raw.get("sv")):
        return None
    return preparar_def(raw)


def cara(defn: dict, unidad: str = "in", basis=None) -> dict | None:
    """Contorno y huecos de la piel, en la unidad del plano. Origen en la esquina mínima.

    `basis` = (origen, u, v) en cm de pieza, Y hacia arriba del tanque. Sin basis,
    la cara plana mayor y la Y de la pieza.
    """
    tris = defn.get("tris")
    if tris is None or len(tris) < 1:
        return None
    look, u, v, origin = _base(defn, basis)
    if look is None:
        return None
    piel, s_piel = _piel(tris, look)
    if piel is None or len(piel) < 1:
        look, u = -look, -u
        piel, s_piel = _piel(tris, look)
    if piel is None or len(piel) < 1:
        return None
    uv = _proy(piel.reshape(-1, 3), origin, u, v).reshape(-1, 3, 2)
    lazos = _lazos(uv)
    if not lazos:
        return None
    lazos.sort(key=lambda item: abs(item[0]), reverse=True)
    area0, outer = lazos[0]
    if abs(area0) < 0.05:
        return None
    if not _cubre_piel(outer, uv):
        return None
    holes_cm = []
    for area, poly in lazos[1:]:
        if abs(area) < 0.02:
            continue
        if _es_metal(poly, uv):
            continue
        holes_cm.append(poly)
    k = CM_POR_UNIDAD.get(str(unidad).lower(), 2.54)
    circulos = _circulos(defn, origin, u, v, look, s_piel, k)
    outline = [(float(p[0]) / k, float(p[1]) / k) for p in outer]
    holes = [h for poly in holes_cm for h in _huecos(poly, k, circulos)]
    outline, holes, circulos = _a_cero(outline, holes, circulos)
    xs = [p[0] for p in outline]
    ys = [p[1] for p in outline]
    largo = max(xs) - min(xs)
    ancho = max(ys) - min(ys)
    if largo < 0.2 or ancho < 0.2:
        return None
    return {
        "outline": outline,
        "holes": holes,
        "source": "alambrico",
        "measures": {
            "LENGTH": round(largo, 3),
            "WIDTH": round(ancho, 3),
            "THK": round(_espesor(tris, look) / k, 3),
        },
        "_defn": defn,
        "_marco": _marco(defn, u, v, look),
    }


def guardar_vista(defn: dict, marco: dict, dest: str | Path, unidad: str = "in") -> str:
    """VISTA_ALAMBRICA de esta lámina. Sin las ocurrencias que van montadas encima."""
    from referencia_geo import imagen_base, lienzo, vista_hlr

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if marco is None or float(marco.get("span_u") or 0) < 1e-3:
        raise RuntimeError("sin marco")
    w, h, _escala, px = lienzo(marco, unidad)
    m = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0]])
    tinta = vista_hlr(marco, [(defn, m)], unidad, w, h, px)
    imagen_base(tinta).save(dest, "JPEG", quality=92)
    return str(dest)


def _base(defn: dict, basis):
    if basis and basis[0] is not None and basis[1] is not None and basis[2] is not None:
        origin = _v(basis[0])
        u = _unit(basis[1])
        v = _unit(basis[2])
        if u is None or v is None:
            return None, None, None, None
        look = _unit(np.cross(u, v))
        if look is None:
            return None, None, None, None
        return look, u, v, origin
    planos = defn.get("planos") or []
    if not planos:
        return None, None, None, None
    look = _unit(planos[0]["n"])
    if look is None:
        return None, None, None, None
    arriba = np.array([0.0, 1.0, 0.0])
    if abs(float(np.dot(look, arriba))) > 0.9:
        arriba = np.array([1.0, 0.0, 0.0])
    v = _unit(arriba - look * float(np.dot(arriba, look)))
    u = _unit(np.cross(v, look))
    v = _unit(np.cross(look, u))
    if u is None or v is None:
        return None, None, None, None
    return look, u, v, _v(planos[0]["p"])


def _piel(tris: np.ndarray, look: np.ndarray):
    """Triángulos de la piel que mira `look`: la cara paralela de más área."""
    cr = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    dos = np.linalg.norm(cr, axis=1)
    ok = dos > 1e-8
    if not ok.any():
        return None, 0.0
    n = np.zeros_like(cr)
    n[ok] = cr[ok] / dos[ok, None]
    area = dos / 2
    centros = tris.mean(axis=1)
    alin = ok & ((n @ look) > NORMAL)
    if not alin.any():
        return None, 0.0
    off = np.round((centros @ look) / BIN_CM) * BIN_CM
    mejor_a, mejor_off = -1.0, None
    for clave in np.unique(np.round(off[alin], 5)):
        sel = alin & (np.abs(off - clave) < 1e-6)
        a = float(area[sel].sum())
        if a > mejor_a + 1e-6 or (abs(a - mejor_a) <= 1e-6 and (mejor_off is None or clave > mejor_off)):
            mejor_a, mejor_off = a, float(clave)
    sel = alin & (np.abs(off - mejor_off) < 1e-6)
    return tris[sel], float(mejor_off)


def _proy(pts: np.ndarray, origin, u, v) -> np.ndarray:
    d = _v(pts).reshape(-1, 3) - _v(origin)
    return np.stack([d @ u, d @ v], axis=1)


def _clave(p) -> tuple[int, int]:
    return (int(round(float(p[0]) / TOL_CM)), int(round(float(p[1]) / TOL_CM)))


def _lazos(uv: np.ndarray) -> list[tuple[float, list[tuple[float, float]]]]:
    """Bordes que solo toca un triángulo de la piel: contorno y huecos."""
    cuenta: dict[tuple, int] = {}
    xy: dict[tuple, tuple[float, float]] = {}
    for tri in uv:
        claves = [_clave(p) for p in tri]
        for p, c in zip(tri, claves):
            xy.setdefault(c, (float(p[0]), float(p[1])))
        for a, b in ((claves[0], claves[1]), (claves[1], claves[2]), (claves[2], claves[0])):
            if a == b:
                continue
            arista = (a, b) if a < b else (b, a)
            cuenta[arista] = cuenta.get(arista, 0) + 1
    borde = [a for a, n in cuenta.items() if n == 1]
    vec: dict[tuple, list[tuple]] = {}
    for a, b in borde:
        vec.setdefault(a, []).append(b)
        vec.setdefault(b, []).append(a)
    usados: set[tuple] = set()
    lazos = []

    def tomar(a, b) -> bool:
        k = (a, b) if a < b else (b, a)
        if k in usados:
            return False
        usados.add(k)
        return True

    for a, b in borde:
        if not tomar(a, b):
            continue
        cad = [a, b]
        prev, cur = a, b
        for _ in range(len(borde) + 2):
            if cur == a and len(cad) > 2:
                break
            sig = None
            for nxt in vec.get(cur, []):
                if nxt == prev:
                    continue
                if tomar(cur, nxt):
                    sig = nxt
                    break
            if sig is None:
                break
            cad.append(sig)
            prev, cur = cur, sig
        if cur != a or len(cad) < 4:
            continue
        poly = [xy[k] for k in cad[:-1]]
        lazos.append((_area(poly), poly))
    return lazos


def _area(poly: list[tuple[float, float]]) -> float:
    a = 0.0
    for i, p in enumerate(poly):
        q = poly[(i + 1) % len(poly)]
        a += p[0] * q[1] - q[0] * p[1]
    return a / 2


def _cubre_piel(outer, uv: np.ndarray) -> bool:
    pts = uv.reshape(-1, 2)
    ox = [p[0] for p in outer]
    oy = [p[1] for p in outer]
    su = float(pts[:, 0].max() - pts[:, 0].min())
    sv = float(pts[:, 1].max() - pts[:, 1].min())
    if su < 1e-3 or sv < 1e-3:
        return False
    return (max(ox) - min(ox)) >= 0.85 * su and (max(oy) - min(oy)) >= 0.85 * sv


def _es_metal(poly, uv: np.ndarray) -> bool:
    """True si el lazo es marcaje: el interior sigue cubierto por la piel."""
    muestras = _muestras(poly)
    if not muestras:
        return False
    return all(_en_malla(p, uv) for p in muestras)


def _muestras(poly) -> list[np.ndarray]:
    c = np.mean(np.asarray(poly, dtype=float), axis=0)
    puntos = [c]
    paso = max(1, len(poly) // 8)
    for p in poly[::paso]:
        puntos.append(0.75 * c + 0.25 * _v(p))
    return [p for p in puntos if _en_poligono(float(p[0]), float(p[1]), poly)]


def _en_poligono(x: float, y: float, poly) -> bool:
    dentro = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-15) + xi:
            dentro = not dentro
        j = i
    return dentro


def _en_malla(p, uv: np.ndarray) -> bool:
    a = uv[:, 0, :]
    b = uv[:, 1, :]
    c = uv[:, 2, :]
    v0 = c - a
    v1 = b - a
    v2 = _v(p) - a
    d00 = np.einsum("ij,ij->i", v0, v0)
    d01 = np.einsum("ij,ij->i", v0, v1)
    d11 = np.einsum("ij,ij->i", v1, v1)
    d02 = np.einsum("ij,ij->i", v0, v2)
    d12 = np.einsum("ij,ij->i", v1, v2)
    den = d00 * d11 - d01 * d01
    ok = np.abs(den) > 1e-10
    inv = np.zeros_like(den)
    inv[ok] = 1.0 / den[ok]
    u = (d11 * d02 - d01 * d12) * inv
    v = (d00 * d12 - d01 * d02) * inv
    return bool(np.any(ok & (u >= -1e-6) & (v >= -1e-6) & (u + v <= 1 + 1e-6)))


def _circulos(defn, origin, u, v, look, s_piel, k) -> list[dict]:
    out = []
    for arista in defn.get("aristas") or []:
        crudo = arista.get("circ")
        if not crudo or float(crudo.get("barrido") or 0) < math.radians(25):
            continue
        normal = _unit(crudo["n"])
        if normal is None or abs(float(np.dot(normal, look))) < NORMAL:
            continue
        centro = _v(crudo["c"])
        if abs(float(np.dot(centro, look)) - s_piel) > BIN_CM:
            continue
        xy = _proy(centro, origin, u, v)[0]
        out.append(
            {
                "x": float(xy[0]) / k,
                "y": float(xy[1]) / k,
                "dia": 2 * float(crudo["r"]) / k,
            }
        )
    return out


def _huecos(poly_cm, k: float, circulos: list[dict]) -> list[dict]:
    poly = [(float(p[0]) / k, float(p[1]) / k) for p in poly_cm]
    if len(poly) < 3:
        return []
    propios = [c for c in circulos if _en_poligono(c["x"], c["y"], poly) or _sobre(c, poly)]
    if propios:
        from acotacion_run import _huecos_de_lazo

        huecos = _huecos_de_lazo(propios, poly)
        if huecos:
            return huecos
    return [{"kind": "cut", "pts": poly}]


def _sobre(circulo: dict, poly) -> bool:
    x, y = float(circulo["x"]), float(circulo["y"])
    r = float(circulo["dia"]) / 2
    for px, py in poly:
        if math.hypot(px - x, py - y) <= r * 1.15 + 0.05:
            return True
    return False


def _a_cero(outline, holes, circulos):
    xs = [p[0] for p in outline]
    ys = [p[1] for p in outline]
    ox, oy = min(xs), min(ys)

    def mueve(x, y):
        return (float(x) - ox, float(y) - oy)

    outline = [mueve(x, y) for x, y in outline]
    movidos = []
    for item in holes:
        row = dict(item)
        if "x" in row and "y" in row:
            row["x"], row["y"] = mueve(row["x"], row["y"])
        for a, b in (("x0", "y0"), ("x1", "y1")):
            if a in row and b in row:
                row[a], row[b] = mueve(row[a], row[b])
        if row.get("pts"):
            row["pts"] = [mueve(p[0], p[1]) for p in row["pts"]]
        movidos.append(row)
    return outline, movidos, [mueve(c["x"], c["y"]) for c in circulos]


def _espesor(tris: np.ndarray, look: np.ndarray) -> float:
    cr = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    dos = np.linalg.norm(cr, axis=1)
    ok = dos > 1e-8
    if not ok.any():
        return 0.0
    n = np.zeros_like(cr)
    n[ok] = cr[ok] / dos[ok, None]
    paralelos = ok & (np.abs(n @ look) > NORMAL)
    if not paralelos.any():
        return 0.0
    s = tris[paralelos].mean(axis=1) @ look
    return float(s.max() - s.min())


def _marco(defn: dict, u, v, look) -> dict | None:
    trozos = [a["pts"] for a in defn.get("aristas") or [] if a.get("pts") is not None and len(a["pts"])]
    tris = defn.get("tris")
    if trozos:
        pts = np.concatenate([_v(t).reshape(-1, 3) for t in trozos])
    elif tris is not None and len(tris):
        pts = tris.reshape(-1, 3)
    else:
        return None
    uu, vv, ss = pts @ u, pts @ v, pts @ look
    return {
        "n": look,
        "u": u,
        "v": v,
        "exterior": float(ss.max()),
        "u0": float(uu.min()),
        "v0": float(vv.min()),
        "span_u": float(uu.max() - uu.min()),
        "span_v": float(vv.max() - vv.min()),
    }
