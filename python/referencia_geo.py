"""COTAS_POR_REFERENCIA desde geometría exacta (snapshot), sin capturas de Inventor.

El snapshot (`referencia_snapshot.capturar`) trae, en cm y en coordenadas de pieza:
trazos de aristas (vértices sobre la curva real) y facetas por .ipt, y por instancia
su matriz, caja mundo y muro. Aquí todo es Python puro: marco de la placa, origen IL
en la piel exterior, rasgo de cada accesorio (círculo exacto o mínimos X/Y), vista de
frente con ocultas quitadas por z-buffer y un JPG por cota.
"""

from __future__ import annotations

import gzip
import json
import math
from pathlib import Path

import numpy as np

CM_POR_UNIDAD = {"in": 2.54, "mm": 0.1}
ARRIBA_MUNDO = (0.0, 1.0, 0.0)
PIEL_CM = 0.05
FRENTE_CM = 0.05
CIRC_RESIDUO_CM = 0.002
PASO_MAX_GRADOS = 50.0
CIRC_PARALELO = 0.98
CIRC_LLENA = 0.85
CIRC_CUADRADA = 0.15
ANCHO_PX = 1600
MARGEN_IN = 0.55
VISIBLE_CM = 0.03
CONTACTO_CM = 0.3
MARGEN_RECT_CM = 0.5
ESPESOR_MAX_CM = 3.0
FRACCION_PLACA = 0.15


# ---------------------------------------------------------------- vectores

def _v(a) -> np.ndarray:
    return np.asarray(a, dtype=float)


def _unit(a) -> np.ndarray | None:
    a = _v(a)
    n = float(np.linalg.norm(a))
    return None if n < 1e-12 else a / n


def transformar(m, pts) -> np.ndarray:
    """m = 3×4 (filas de occ.Transformation), pts = (N,3) en cm de pieza."""
    m = _v(m)
    pts = _v(pts).reshape(-1, 3)
    return pts @ m[:, :3].T + m[:, 3]


def rotar(m, vec) -> np.ndarray:
    return _v(m)[:, :3] @ _v(vec)


# ---------------------------------------------------------------- aristas

def cadenas(coords, idx) -> list[np.ndarray]:
    """Trazos de CalculateStrokes → una polilínea por arista.

    `idx` son pares 1-based. En un sólido cada vértice real une 3+ aristas, así que
    se corta en grado ≠ 2; los vértices interiores del trazo tienen grado 2.
    """
    pts = _v(coords).reshape(-1, 3)
    pares = np.asarray(idx, dtype=int).reshape(-1, 2) - 1
    vecinos: dict[int, list[int]] = {}
    for a, b in pares:
        if a == b:
            continue
        vecinos.setdefault(int(a), []).append(int(b))
        vecinos.setdefault(int(b), []).append(int(a))
    usados: set[tuple[int, int]] = set()
    out: list[np.ndarray] = []

    def tomar(a: int, b: int) -> bool:
        k = (a, b) if a < b else (b, a)
        if k in usados:
            return False
        usados.add(k)
        return True

    def recorrer(inicio: int, sig: int) -> list[int]:
        cad = [inicio, sig]
        prev, cur = inicio, sig
        while len(vecinos.get(cur, [])) == 2 and cur != inicio:
            nxt = vecinos[cur][0] if vecinos[cur][0] != prev else vecinos[cur][1]
            if not tomar(cur, nxt):
                break
            cad.append(nxt)
            prev, cur = cur, nxt
        return cad

    for nodo, vs in vecinos.items():
        if len(vs) == 2:
            continue
        for sig in vs:
            if tomar(nodo, sig):
                out.append(pts[recorrer(nodo, sig)])
    for nodo, vs in vecinos.items():
        for sig in vs:
            if tomar(nodo, sig):
                out.append(pts[recorrer(nodo, sig)])
    return out


def ajustar_circulo(pts) -> dict | None:
    """Círculo/arco si los puntos son coplanares y equidistantes de un centro."""
    p = _v(pts)
    if len(p) >= 2 and np.linalg.norm(p[0] - p[-1]) < 1e-6:
        p = p[:-1]
    if len(p) < 3:
        return None
    c0 = p.mean(axis=0)
    _u, s, vt = np.linalg.svd(p - c0)
    if s[1] < 1e-6:
        return None
    n = vt[2]
    if s[2] > 1e-4 * max(s[0], 1e-9) + 1e-7:
        return None
    e1, e2 = vt[0], vt[1]
    q = np.stack([(p - c0) @ e1, (p - c0) @ e2], axis=1)
    a = np.column_stack([2 * q, np.ones(len(q))])
    b = (q ** 2).sum(axis=1)
    sol, *_ = np.linalg.lstsq(a, b, rcond=None)
    cx, cy = sol[0], sol[1]
    r = math.sqrt(max(sol[2] + cx * cx + cy * cy, 0.0))
    if r < 1e-4:
        return None
    resid = np.abs(np.hypot(q[:, 0] - cx, q[:, 1] - cy) - r)
    if float(resid.max()) > max(CIRC_RESIDUO_CM, r * 1e-4):
        return None
    ang = np.unwrap(np.arctan2(q[:, 1] - cy, q[:, 0] - cx))
    if float(np.abs(np.diff(ang)).max()) > math.radians(PASO_MAX_GRADOS):
        return None
    barrido = float(abs(ang[-1] - ang[0]))
    cerrado = np.linalg.norm(_v(pts)[0] - _v(pts)[-1]) < 1e-6
    if cerrado:
        barrido = 2 * math.pi
    elif barrido < math.radians(20):
        return None
    centro = c0 + cx * e1 + cy * e2
    return {"c": centro, "n": n, "r": r, "barrido": barrido}


def preparar_def(raw: dict) -> dict:
    """Snapshot crudo de un .ipt → aristas con círculo ajustado, triángulos y planos."""
    aristas = []
    for cad in cadenas(raw.get("sv") or [], raw.get("si") or []):
        aristas.append({"pts": cad, "circ": ajustar_circulo(cad) if len(cad) >= 4 else None})
    fv = _v(raw.get("fv") or []).reshape(-1, 3)
    fi = np.asarray(raw.get("fi") or [], dtype=int).reshape(-1, 3) - 1
    tris = fv[fi] if len(fv) and len(fi) else np.zeros((0, 3, 3))
    return {"aristas": aristas, "tris": tris, "planos": raw.get("planos") or planos_de_facetas(tris)}


def planos_de_facetas(tris: np.ndarray, minimo: float = 0.1) -> list[dict]:
    """Caras planas desde triángulos coplanares (normal + offset), ≥ `minimo` del área mayor."""
    if not len(tris):
        return []
    cr = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    dos_a = np.linalg.norm(cr, axis=1)
    ok = dos_a > 1e-12
    if not ok.any():
        return []
    n = cr[ok] / dos_a[ok][:, None]
    p = tris[ok, 0]
    area = dos_a[ok] / 2
    d = (n * p).sum(axis=1)
    grupos: dict[tuple, list] = {}
    for ni, di, ai, pi in zip(np.round(n * 1000).astype(int), np.round(d * 100).astype(int), area, p):
        g = grupos.setdefault((ni[0], ni[1], ni[2], di), [0.0, pi])
        g[0] += float(ai)
    if not grupos:
        return []
    amax = max(g[0] for g in grupos.values())
    out = [
        {"n": [k[0] / 1000.0, k[1] / 1000.0, k[2] / 1000.0], "p": [float(x) for x in g[1]], "area": g[0]}
        for k, g in grupos.items()
        if g[0] >= minimo * amax
    ]
    for item in out:
        item["n"] = [float(x) for x in _unit(item["n"])]
    return sorted(out, key=lambda item: -item["area"])


def _pts_def(defn: dict) -> np.ndarray:
    pts = [a["pts"] for a in defn["aristas"]]
    if pts:
        return np.concatenate(pts)
    return defn["tris"].reshape(-1, 3) if len(defn["tris"]) else np.zeros((0, 3))


# ---------------------------------------------------------------- marco

def _offsets_paralelos(defn: dict, m, n: np.ndarray, fraccion: float = 0.5) -> list[float]:
    planos = defn.get("planos") or []
    if not planos:
        return []
    amax = max(float(p["area"]) for p in planos)
    out = []
    for p in planos:
        if float(p["area"]) < fraccion * amax:
            continue
        nw = _unit(rotar(m, p["n"]))
        if nw is not None and abs(float(np.dot(nw, n))) > 0.99:
            out.append(float(np.dot(transformar(m, [p["p"]])[0], n)))
    return out


def marco_muro(placa_def: dict, m, centro_tanque, arriba=ARRIBA_MUNDO, extra: list[tuple] | None = None) -> dict | None:
    """Normal hacia afuera (cara plana mayor), Y mundo arriba, plano exterior y origen IL.

    `extra` = otras placas (def, m) del mismo muro: si su cara mayor es coplanar con la
    exterior, su piel entra al rectángulo IL.
    """
    planos = placa_def.get("planos") or []
    pts_todos = transformar(m, _pts_def(placa_def))
    if not len(pts_todos):
        return None
    centro_placa = pts_todos.mean(axis=0)
    if planos:
        n = _unit(rotar(m, planos[0]["n"]))
    else:
        n = _eje_delgado(pts_todos)
    if n is None:
        return None
    if centro_tanque is not None and float(np.dot(n, centro_placa - _v(centro_tanque))) < 0:
        n = -n
    ofs = _offsets_paralelos(placa_def, m, n)
    exterior = max(ofs) if ofs else float((pts_todos @ n).max())
    v = _unit(_v(arriba) - n * float(np.dot(arriba, n)))
    if v is None:
        v = _unit(_v((1.0, 0.0, 0.0)) - n * float(n[0]))
    if v is None:
        return None
    u = _unit(np.cross(v, n))
    v = _unit(np.cross(n, u))
    pieles = [pts_todos[np.abs(pts_todos @ n - exterior) <= PIEL_CM]]
    for defn_x, m_x in extra or []:
        ofs_x = _offsets_paralelos(defn_x, m_x, n)
        if not ofs_x or min(abs(o - exterior) for o in ofs_x) > 1.0:
            continue
        pts_x = transformar(m_x, _pts_def(defn_x))
        pieles.append(pts_x[np.abs(pts_x @ n - exterior) <= 1.0])
    piel = np.concatenate([p for p in pieles if len(p)]) if any(len(p) for p in pieles) else pts_todos
    if len(piel) < 3:
        piel = pts_todos
    pu, pv = piel @ u, piel @ v
    return {
        "n": n,
        "u": u,
        "v": v,
        "exterior": exterior,
        "u0": float(pu.min()),
        "v0": float(pv.min()),
        "span_u": float(pu.max() - pu.min()),
        "span_v": float(pv.max() - pv.min()),
    }


def _eje_delgado(pts: np.ndarray) -> np.ndarray | None:
    _u, _s, vt = np.linalg.svd(pts - pts.mean(axis=0), full_matrices=False)
    return _unit(vt[-1])


def a_marco(marco: dict, pts) -> np.ndarray:
    """Mundo (cm) → (x, y, s) con x,y desde el IL de la placa y s = altura sobre la piel."""
    p = _v(pts).reshape(-1, 3)
    return np.stack(
        [p @ marco["u"] - marco["u0"], p @ marco["v"] - marco["v0"], p @ marco["n"] - marco["exterior"]],
        axis=1,
    )


def fuera_rect(marco: dict, x: float, y: float) -> float:
    du = max(0.0, -x, x - marco["span_u"])
    dv = max(0.0, -y, y - marco["span_v"])
    return du + dv


def dueno(marcos: dict, punto) -> str | None:
    mejor, mejor_s = None, None
    for cara, mc in marcos.items():
        x, y, s = a_marco(mc, punto)[0]
        score = abs(s) + 3.0 * fuera_rect(mc, x, y)
        if mejor_s is None or score < mejor_s:
            mejor, mejor_s = cara, score
    return mejor


# ---------------------------------------------------------------- rasgos

def rasgo(defn: dict, m, marco: dict) -> dict | None:
    """Huella del accesorio delante de la piel: caja exacta y, si es redondo de frente, su círculo."""
    xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    smin = math.inf
    circulos = []
    for arista in defn["aristas"]:
        loc = a_marco(marco, transformar(m, arista["pts"]))
        if len(loc):
            # Incluye lo que cruza la piel: el punto más atrás, no solo la muestra de enfrente.
            smin = min(smin, float(loc[:, 2].min()))
        delante = loc[loc[:, 2] >= -FRENTE_CM]
        if len(delante):
            xs.append(delante[:, 0])
            ys.append(delante[:, 1])
        c = arista.get("circ")
        if not c:
            continue
        nw = _unit(rotar(m, c["n"]))
        cw = transformar(m, [c["c"]])[0]
        lc = a_marco(marco, cw)[0]
        if lc[2] < -FRENTE_CM:
            continue
        r = float(c["r"])
        ext_x = r * math.sqrt(max(0.0, 1.0 - float(np.dot(nw, marco["u"])) ** 2))
        ext_y = r * math.sqrt(max(0.0, 1.0 - float(np.dot(nw, marco["v"])) ** 2))
        if c["barrido"] >= 2 * math.pi - 1e-6:
            xs.append(np.array([lc[0] - ext_x, lc[0] + ext_x]))
            ys.append(np.array([lc[1] - ext_y, lc[1] + ext_y]))
        if abs(float(np.dot(nw, marco["n"]))) >= CIRC_PARALELO and c["barrido"] >= math.pi * 0.5:
            circulos.append((float(lc[0]), float(lc[1]), r, float(c["barrido"])))
    if not xs:
        return None
    allx, ally = np.concatenate(xs), np.concatenate(ys)
    xmin, xmax, ymin, ymax = float(allx.min()), float(allx.max()), float(ally.min()), float(ally.max())
    w, h = xmax - xmin, ymax - ymin
    out = {"xmin": xmin, "xmax": xmax, "ymin": ymin, "ymax": ymax, "cx": (xmin + xmax) / 2, "cy": (ymin + ymax) / 2, "smin": smin}
    mayor = _circulo_mayor(circulos)
    lado = max(w, h, 1e-9)
    redondo = (
        mayor is not None
        and 2 * mayor[2] >= CIRC_LLENA * lado
        and abs(w - h) <= CIRC_CUADRADA * lado
    )
    out["circ"] = bool(redondo)
    if redondo:
        out["cx"], out["cy"], out["r"] = mayor
    out["x"] = out["cx"] if redondo else xmin
    out["y"] = out["cy"] if redondo else ymin
    return out


def _circulo_mayor(circulos: list[tuple]) -> tuple | None:
    """Une arcos del mismo círculo (Inventor parte círculos en dos) y devuelve el de mayor radio."""
    grupos: list[list] = []
    for cx, cy, r, barrido in circulos:
        for g in grupos:
            if math.hypot(g[0] - cx, g[1] - cy) < 0.02 and abs(g[2] - r) < 0.02:
                g[3] += barrido
                break
        else:
            grupos.append([cx, cy, r, barrido])
    llenos = [g for g in grupos if g[3] >= math.pi * 1.5]
    if not llenos:
        return None
    g = max(llenos, key=lambda item: item[2])
    return (g[0], g[1], g[2])


# ---------------------------------------------------------------- muros y piezas

def preparar(snap: dict) -> tuple[dict, dict]:
    defs = {k: preparar_def(v) for k, v in (snap.get("defs") or {}).items()}
    occs = {o["key"]: o for o in snap.get("occs") or []}
    return defs, occs


def _area_laminar(defn: dict, m=None) -> float:
    """Área de la cara plana mayor si tiene cara opuesta paralela a ≤ ESPESOR_MAX_CM (lámina,
    aunque esté doblada); si no, 0."""
    planos = defn.get("planos") or []
    if not planos:
        return 0.0
    a = planos[0]
    na = _v(a["n"])
    da = float(np.dot(na, a["p"]))
    for b in planos[1:]:
        nb = _v(b["n"])
        if float(np.dot(na, nb)) > -0.99 or float(b["area"]) < 0.5 * float(a["area"]):
            continue
        if abs(float(np.dot(na, b["p"])) - da) <= ESPESOR_MAX_CM:
            return float(a["area"])
    return 0.0


def marcos_de(snap: dict, defs: dict, occs: dict) -> dict[str, dict]:
    """Un marco por muro: placa ancla (confirmada o la lámina mayor de la bolsa) + placas coplanares."""
    centro = snap.get("centro_tanque")
    por_cara: dict[str, list[dict]] = {}
    for occ in occs.values():
        cara = str(occ.get("cara") or "").upper()
        if cara and occ["def"] in defs:
            por_cara.setdefault(cara, []).append(occ)
    areas: dict[str, float] = {}

    def area(o: dict) -> float:
        if o["key"] not in areas:
            areas[o["key"]] = _area_laminar(defs[o["def"]], o["m"])
        return areas[o["key"]]

    out = {}
    tomadas: set[str] = set()
    pendientes = []
    for cara, miembros in por_cara.items():
        placas = [o for o in miembros if o.get("placa")]
        if not placas:
            pendientes.append(cara)
            continue
        ancla = max(placas, key=lambda o: (area(o), (defs[o["def"]]["planos"] or [{"area": 0}])[0]["area"]))
        resto = [(defs[o["def"]], o["m"]) for o in placas if o["key"] != ancla["key"]]
        mc = marco_muro(defs[ancla["def"]], ancla["m"], centro, extra=resto)
        if mc is not None:
            mc["ancla"] = ancla["key"]
            mc["placas"] = [o["key"] for o in placas]
            out[cara] = mc
            tomadas.update(mc["placas"])
    if pendientes:
        laminas = [o for o in occs.values() if o["def"] in defs and o["key"] not in tomadas and area(o) > 0]
        amax = max((area(o) for o in laminas), default=0.0)
        grandes = [o for o in laminas if area(o) >= FRACCION_PLACA * amax]
        for cara in pendientes:
            mc = _ancla_por_contacto(por_cara[cara], grandes, defs, centro, tomadas)
            if mc is not None:
                out[cara] = mc
                tomadas.add(mc["ancla"])
    for cara, signo in (("TOP", 1.0), ("BASE", -1.0)):
        if cara in out or centro is None:
            continue
        mc = _ancla_por_orientacion(occs, defs, centro, signo, tomadas, area)
        if mc is not None:
            out[cara] = mc
            tomadas.add(mc["ancla"])
    return out


def _ancla_por_orientacion(occs: dict, defs: dict, centro, signo: float, tomadas: set[str], area) -> dict | None:
    """TOP/BASE sin bolsa: lámina grande libre con normal ±Y mundo, del lado correcto del tanque."""
    arriba = _v(ARRIBA_MUNDO) * signo
    mejor, mejor_a = None, 0.0
    for o in occs.values():
        if o["key"] in tomadas or o["def"] not in defs:
            continue
        a = area(o)
        if a <= mejor_a:
            continue
        planos = defs[o["def"]]["planos"]
        n = _unit(rotar(o["m"], planos[0]["n"]))
        p = transformar(o["m"], [planos[0]["p"]])[0]
        if abs(float(np.dot(n, arriba))) < 0.99 or float(np.dot(p - _v(centro), arriba)) <= 0:
            continue
        mejor, mejor_a = o, a
    if mejor is None:
        return None
    mc = marco_muro(defs[mejor["def"]], mejor["m"], centro)
    if mc is not None:
        mc["ancla"] = mejor["key"]
        mc["placas"] = [mejor["key"]]
    return mc


def _ancla_por_contacto(miembros: list[dict], candidatos: list[dict], defs: dict, centro, tomadas: set[str]) -> dict | None:
    """Muro sin placa confirmada: la lámina grande cuya cara exterior tocan más miembros de la bolsa."""
    mejor, mejor_n = None, 0
    for cand in candidatos:
        if cand["key"] in tomadas:
            continue
        mc = marco_muro(defs[cand["def"]], cand["m"], centro)
        if mc is None:
            continue
        n = 0
        for o in miembros:
            if o["key"] == cand["key"]:
                continue
            r = rasgo(defs[o["def"]], o["m"], mc)
            if r and r["smin"] <= CONTACTO_CM and fuera_rect(mc, r["cx"], r["cy"]) <= MARGEN_RECT_CM:
                n += 1
        if n > mejor_n:
            mejor, mejor_n = mc, n
            mejor["ancla"] = cand["key"]
            mejor["placas"] = [cand["key"]]
    return mejor


def piezas_cara(cara: str, snap: dict, defs: dict, occs: dict, marcos: dict, unidad: str) -> list[dict]:
    marco = marcos.get(cara)
    if marco is None:
        return []
    k = 1.0 / CM_POR_UNIDAD.get(unidad, 2.54)
    anclas = {k for mc in marcos.values() for k in mc.get("placas", [mc["ancla"]])}
    rows = []
    for occ in occs.values():
        cara_occ = str(occ.get("cara") or "").upper()
        if occ["key"] in anclas or occ.get("placa"):
            continue
        # La bolsa confirmada no cierra la cara: lo sin bolsa sigue si toca esta piel.
        if cara_occ and cara_occ != cara:
            continue
        defn = defs.get(occ["def"])
        if defn is None:
            continue
        r = rasgo(defn, occ["m"], marco)
        if r is None:
            continue
        if not cara_occ and (r["smin"] > CONTACTO_CM or fuera_rect(marco, r["cx"], r["cy"]) > MARGEN_RECT_CM):
            continue
        centro_mundo = (
            marco["u"] * (r["cx"] + marco["u0"])
            + marco["v"] * (r["cy"] + marco["v0"])
            + marco["n"] * marco["exterior"]
        )
        if len(marcos) > 1 and dueno(marcos, centro_mundo) != cara:
            continue
        fila = {kk: (vv * k if isinstance(vv, float) else vv) for kk, vv in r.items()}
        fila.update({"key": occ["key"], "name": occ.get("name"), "tipo": occ.get("tipo") or "TIPO"})
        rows.append(fila)
    return rows


# ---------------------------------------------------------------- dibujo

def lienzo(marco: dict, unidad: str, extra=None):
    """Escala px y función (x, y en unidad) → pixel. Encuadre: placa + margen."""
    k = CM_POR_UNIDAD.get(unidad, 2.54)
    margen = MARGEN_IN * 2.54 / k
    span_u = marco["span_u"] / k
    span_v = marco["span_v"] / k
    x0, y0, x1, y1 = -margen, -margen, span_u + margen, span_v + margen
    if extra:
        x0 = max(min(x0, extra[0] - margen), -0.25 * span_u)
        y0 = max(min(y0, extra[1] - margen), -0.25 * span_v)
        x1 = min(max(x1, extra[2] + margen), 1.25 * span_u)
        y1 = min(max(y1, extra[3] + margen), 1.25 * span_v)
    escala = ANCHO_PX / max(x1 - x0, 1e-6)
    w = ANCHO_PX
    h = max(240, int(round((y1 - y0) * escala)))

    def px(x: float, y: float) -> tuple[float, float]:
        return ((float(x) - x0) * escala, (y1 - float(y)) * escala)

    return w, h, escala, px


def vista_hlr(marco: dict, piezas_dibujo: list[tuple], unidad: str, w: int, h: int, px) -> np.ndarray:
    """Máscara (h, w) de líneas visibles: aristas que no quedan detrás de ninguna faceta."""
    k = CM_POR_UNIDAD.get(unidad, 2.54)
    zbuf = np.full((h, w), -np.inf)
    escala_px = px(1.0, 0.0)[0] - px(0.0, 0.0)[0]
    x_off, y_off = px(0.0, 0.0)

    def a_px(loc: np.ndarray) -> np.ndarray:
        return np.stack([x_off + loc[:, 0] / k * escala_px, y_off - loc[:, 1] / k * escala_px, loc[:, 2]], axis=1)

    for defn, m in piezas_dibujo:
        tris = defn["tris"]
        if not len(tris):
            continue
        loc = a_px(a_marco(marco, transformar(m, tris.reshape(-1, 3)))).reshape(-1, 3, 3)
        _rasterizar(zbuf, loc)
    zcmp = zbuf.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            np.minimum(zcmp, np.roll(np.roll(zbuf, dy, axis=0), dx, axis=1), out=zcmp)
    tinta = np.zeros((h, w), dtype=bool)
    for defn, m in piezas_dibujo:
        for arista in defn["aristas"]:
            loc = a_px(a_marco(marco, transformar(m, arista["pts"])))
            _trazar_visible(tinta, zcmp, loc, VISIBLE_CM)
    return tinta


def _rasterizar(zbuf: np.ndarray, tris: np.ndarray) -> None:
    h, w = zbuf.shape
    if not len(tris):
        return
    lo = tris[:, :, :2].min(axis=1)
    hi = tris[:, :, :2].max(axis=1)
    fuera = (hi[:, 0] < 0) | (hi[:, 1] < 0) | (lo[:, 0] >= w) | (lo[:, 1] >= h)
    tris, lo, hi = tris[~fuera], lo[~fuera], hi[~fuera]
    lado = (np.ceil(hi) - np.floor(lo)).max(axis=1)
    hecho = np.zeros(len(tris), dtype=bool)
    for b in (4, 8, 16, 32):
        sel = ~hecho & (lado < b)
        if sel.any():
            _rasterizar_lote(zbuf, tris[sel], np.floor(lo[sel]).astype(int), b)
            hecho |= sel
    for t in tris[~hecho]:
        _rasterizar_renglones(zbuf, t)


def _rasterizar_renglones(zbuf: np.ndarray, t: np.ndarray) -> None:
    """Triángulo grande: tramo x por renglón, solo los píxeles cubiertos (astillas largas baratas)."""
    h, w = zbuf.shape
    m = np.column_stack([t[:, 0], t[:, 1], np.ones(3)])
    if abs(float(np.linalg.det(m))) < 1e-9:
        return
    a, b, c = np.linalg.solve(m, t[:, 2])
    y0 = max(int(math.floor(t[:, 1].min())), 0)
    y1 = min(int(math.ceil(t[:, 1].max())), h - 1)
    if y1 < y0:
        return
    yc = np.arange(y0, y1 + 1) + 0.5
    xl = np.full(len(yc), np.inf)
    xr = np.full(len(yc), -np.inf)
    for i, j in ((0, 1), (1, 2), (2, 0)):
        (px, py), (qx, qy) = t[i, :2], t[j, :2]
        if abs(qy - py) < 1e-12:
            continue
        sel = (yc - py) * (yc - qy) <= 0
        x = px + (yc[sel] - py) * (qx - px) / (qy - py)
        xl[sel] = np.minimum(xl[sel], x)
        xr[sel] = np.maximum(xr[sel], x)
    ok = np.isfinite(xl)
    if not ok.any():
        return
    c0 = np.where(ok, np.clip(np.ceil(np.where(ok, xl, 0) - 0.5), 0, w), 0).astype(np.int64)
    c1 = np.where(ok, np.clip(np.floor(np.where(ok, xr, -1) - 0.5), -1, w - 1), -1).astype(np.int64)
    n = np.maximum(c1 - c0 + 1, 0)
    total = int(n.sum())
    if total == 0:
        return
    filas = np.repeat(np.arange(y0, y1 + 1), n)
    inicio = np.repeat(c0 - np.concatenate([[0], np.cumsum(n)[:-1]]), n)
    cols = inicio + np.arange(total)
    z = a * (cols + 0.5) + b * (filas + 0.5) + c
    np.maximum.at(zbuf, (filas, cols), z)


def _rasterizar_lote(zbuf: np.ndarray, tris: np.ndarray, x0y0: np.ndarray, b: int, bloque: int = 4096) -> None:
    """Triángulos con caja < b px: rejilla b×b por triángulo, todo vectorizado."""
    h, w = zbuf.shape
    oy, ox = np.mgrid[0:b, 0:b]
    ox = ox.ravel()
    oy = oy.ravel()
    for i in range(0, len(tris), bloque):
        t = tris[i : i + bloque]
        base = x0y0[i : i + bloque]
        gx = base[:, 0:1] + ox[None, :]
        gy = base[:, 1:2] + oy[None, :]
        px = gx + 0.5
        py = gy + 0.5
        ax, ay, az = t[:, 0, 0:1], t[:, 0, 1:2], t[:, 0, 2:3]
        bx, by, bz = t[:, 1, 0:1], t[:, 1, 1:2], t[:, 1, 2:3]
        cx, cy, cz = t[:, 2, 0:1], t[:, 2, 1:2], t[:, 2, 2:3]
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        den = np.where(np.abs(den) < 1e-9, np.nan, den)
        l1 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / den
        l2 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / den
        l3 = 1.0 - l1 - l2
        dentro = (l1 >= -1e-3) & (l2 >= -1e-3) & (l3 >= -1e-3) & (gx >= 0) & (gx < w) & (gy >= 0) & (gy < h)
        z = l1 * az + l2 * bz + l3 * cz
        # Facetas de canto (área ~0) no cubren píxeles: se marcan por sus vértices.
        if dentro.any():
            np.maximum.at(zbuf, (gy[dentro], gx[dentro]), z[dentro])
        v = t.reshape(-1, 3)
        xi = np.floor(v[:, 0]).astype(int)
        yi = np.floor(v[:, 1]).astype(int)
        ok = (xi >= 0) & (xi < w) & (yi >= 0) & (yi < h)
        np.maximum.at(zbuf, (yi[ok], xi[ok]), v[ok, 2])


def _trazar_visible(tinta: np.ndarray, zbuf: np.ndarray, loc: np.ndarray, eps: float) -> None:
    h, w = tinta.shape
    for a, b in zip(loc[:-1], loc[1:]):
        n = int(max(abs(b[0] - a[0]), abs(b[1] - a[1]))) + 2
        t = np.linspace(0.0, 1.0, n)
        x = a[0] + (b[0] - a[0]) * t
        y = a[1] + (b[1] - a[1]) * t
        z = a[2] + (b[2] - a[2]) * t
        xi = np.floor(x).astype(int)
        yi = np.floor(y).astype(int)
        ok = (xi >= 0) & (xi < w) & (yi >= 0) & (yi < h)
        xi, yi, z = xi[ok], yi[ok], z[ok]
        if not len(xi):
            continue
        vis = z >= zbuf[yi, xi] - eps
        tinta[yi[vis], xi[vis]] = True


def imagen_base(tinta: np.ndarray):
    from PIL import Image

    gruesa = tinta.copy()
    gruesa[1:, :] |= tinta[:-1, :]
    gruesa[:, 1:] |= tinta[:, :-1]
    rgb = np.full(tinta.shape + (3,), 255, dtype=np.uint8)
    rgb[gruesa] = (28, 36, 44)
    return Image.fromarray(rgb, mode="RGB")


# ---------------------------------------------------------------- salida

def leer_snapshot(path: str | Path) -> dict:
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def exportar(
    snap: dict,
    dest_ref: str | Path,
    job: str,
    unidad: str = "in",
    files: list[str] | None = None,
    errors: list[str] | None = None,
    caras: list[str] | None = None,
    qty: int = 1,
    progreso=None,
) -> dict[str, int]:
    """Las caras del snapshot → COTAS_POR_REFERENCIA/{cara}/{tipo}/JPG. Devuelve tipos por cara."""
    import shutil

    from caras_referencia import (
        MIN_COTA,
        TOL,
        _archivo,
        _dibujar_cotas_ref,
        _dibujar_origen_il,
        _escribir_camara,
        _fmt_val,
        _id_pieza,
        _misma_cota,
        _safe,
    )
    from drawing_jpg import _letra

    files = files if files is not None else []
    errors = errors if errors is not None else []
    dest_ref = Path(dest_ref)
    defs, occs = preparar(snap)
    marcos = marcos_de(snap, defs, occs)
    resultado: dict[str, int] = {}
    orden = [c for c in ("TOP", "SEGM1", "SEGM2", "SEGM3", "SEGM4", "BASE") if c in marcos]
    if caras:
        orden = [c for c in orden if c in {str(x).upper() for x in caras}]
    for indice, cara in enumerate(orden, start=1):
        if callable(progreso):
            progreso(indice, len(orden), cara)
        marco = marcos[cara]
        piezas = piezas_cara(cara, snap, defs, occs, marcos, unidad)
        dest_cara = dest_ref / cara
        if dest_cara.is_dir():
            shutil.rmtree(dest_cara, ignore_errors=True)
        dest_cara.mkdir(parents=True, exist_ok=True)
        extra = None
        if piezas:
            extra = (
                min(p["xmin"] for p in piezas),
                min(p["ymin"] for p in piezas),
                max(p["xmax"] for p in piezas),
                max(p["ymax"] for p in piezas),
            )
        w, h, _escala, px_vista = lienzo(marco, unidad, extra)
        dibujo = [(defs[occs[k]["def"]], occs[k]["m"]) for k in marco.get("placas", [marco["ancla"]])]
        claves = {p["key"] for p in piezas}
        for key in claves:
            o = occs[key]
            dibujo.append((defs[o["def"]], o["m"]))
        tinta = vista_hlr(marco, dibujo, unidad, w, h, px_vista)
        base = imagen_base(tinta)
        from PIL import Image

        # Margen para la letra de la cota (2.5×): no recortar el texto.
        from drawing_jpg import _px_cota

        letra = _px_cota(18)
        extra_l, extra_t, extra_b = max(130, letra * 11), 44, max(88, 56 + letra)
        lienzo_img = Image.new("RGB", (base.size[0] + extra_l, base.size[1] + extra_t + extra_b), (255, 255, 255))
        lienzo_img.paste(base, (extra_l, extra_t))

        def px(x: float, y: float) -> tuple[float, float]:
            p = px_vista(x, y)
            return (p[0] + extra_l, p[1] + extra_t)

        span_u = marco["span_u"] / CM_POR_UNIDAD.get(unidad, 2.54)
        span_v = marco["span_v"] / CM_POR_UNIDAD.get(unidad, 2.54)
        try:
            vista = lienzo_img.copy()
            _dibujar_origen_il(vista, px, span_u=span_u, span_v=span_v, unit=unidad)
            vista.save(dest_cara / "VISTA_ALAMBRICA.jpg", "JPEG", quality=92)
            files.append(str(dest_cara / "VISTA_ALAMBRICA.jpg"))
        except Exception as ex:
            errors.append(f"{cara}: vista alambrica {ex}")
        _escribir_camara(
            dest_cara,
            cara=cara,
            look=[float(x) for x in marco["n"]],
            u_axis=[float(x) for x in marco["u"]],
            v_axis=[float(x) for x in marco["v"]],
            ox=0.0,
            oy=0.0,
            span_u=span_u,
            span_v=span_v,
            origen="IL",
            hijos=len(piezas),
            piezas=len(piezas),
            modo="geometria",
            tipos=sorted({p["tipo"] for p in piezas}),
        )
        if not piezas:
            errors.append(f"{cara}: sin hijos que acotar (no se cota la placa madre)")
            resultado[cara] = 0
            continue
        grupos: dict[str, list] = {}
        for pieza in piezas:
            grupos.setdefault(pieza["tipo"], []).append(pieza)
        for tipo, miembros in grupos.items():
            dest_tipo = dest_cara / _safe(tipo)
            dest_tipo.mkdir(parents=True, exist_ok=True)
            orden_m = sorted(miembros, key=lambda p: (p["cx"], p["cy"]))
            letras = {_id_pieza(p, i): _letra(i) for i, p in enumerate(orden_m)}
            vistos: set[tuple] = set()
            for pieza in miembros:
                kx = "XCENTRO" if pieza["circ"] else "XMIN"
                ky = "YCENTRO" if pieza["circ"] else "YMIN"
                for kind, valor in ((kx, pieza["x"]), (ky, pieza["y"])):
                    if abs(valor) < MIN_COTA:
                        continue
                    key = (kind, round(valor / TOL) * TOL)
                    if key in vistos:
                        continue
                    vistos.add(key)
                    foco = [o for o in miembros if _misma_cota(o, kind, valor)]
                    typ = len(foco) > 1
                    marca = f"{kind}_TYP_{_fmt_val(valor)}" if typ else f"{kind}_{_fmt_val(valor)}"
                    label = f"{kind}={_fmt_val(valor)}{' TYP' if typ else ''} {unidad}"
                    dest_jpg = dest_tipo / _archivo(job, tipo, marca)
                    try:
                        img = lienzo_img.copy()
                        _dibujar_cotas_ref(
                            img,
                            px,
                            title=f"{cara}  {tipo}  {marca}  qty {qty}",
                            kind=kind,
                            valor=float(valor),
                            label=label,
                            unit=unidad,
                            foco=foco,
                            miembros=miembros,
                            letras=letras,
                        )
                        img.save(dest_jpg, "JPEG", quality=92)
                        files.append(str(dest_jpg))
                    except Exception as ex:
                        errors.append(f"{cara}/{tipo} {marca}: {ex}")
        resultado[cara] = len(grupos)
    return resultado


if __name__ == "__main__":
    import sys

    snap_path = Path(sys.argv[1])
    snap = leer_snapshot(snap_path)
    salida = snap_path.parent
    f: list[str] = []
    e: list[str] = []
    print(exportar(snap, salida, snap.get("job") or "JOB", snap.get("unidad") or "in", f, e))
    print(f"{len(f)} JPG", *e, sep="\n")
