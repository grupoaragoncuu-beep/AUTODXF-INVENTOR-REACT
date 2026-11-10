"""Juntas de soldadura a partir de las caras del tanque. Sin plano de Inventor.

Las caras entran en milímetros. Un cordón hermético es la arista compartida
entre dos muros. Un accesorio es una pieza apoyada en esa cara.
"""

from __future__ import annotations

import math

PARES = (
    ("BASE", "SEGM1"),
    ("BASE", "SEGM2"),
    ("BASE", "SEGM3"),
    ("BASE", "SEGM4"),
    ("TOP", "SEGM1"),
    ("TOP", "SEGM2"),
    ("TOP", "SEGM3"),
    ("TOP", "SEGM4"),
    ("SEGM1", "SEGM2"),
    ("SEGM2", "SEGM3"),
    ("SEGM3", "SEGM4"),
    ("SEGM4", "SEGM1"),
)

_VISTA = ("SEGM1", "SEGM2", "SEGM3", "SEGM4", "BASE", "TOP")


def marco_derecho(normal, puntos: list[tuple[float, float, float]], canto=None) -> dict | None:
    """Cara de frente: el canto de la placa queda horizontal o vertical en la foto."""
    n = _norm(_vector(normal) or (0.0, 0.0, 0.0))
    limpios = [punto for punto in (_vector(item) for item in puntos) if punto is not None]
    if n is None or len(limpios) < 3:
        return None
    if canto is not None:
        delta = _vector(canto)
        if delta is not None:
            delta = _resta(delta, _escala(n, _dot(delta, n)))
        borde = _norm(delta) if delta is not None else None
    else:
        borde = _borde_mas_largo(limpios, n)
    if borde is None:
        return marco_cara(normal, limpios)
    otro = _norm(_cross(n, borde))
    if otro is None:
        return marco_cara(normal, limpios)
    arriba = (0.0, 1.0, 0.0)
    if abs(_dot(borde, arriba)) >= abs(_dot(otro, arriba)) and abs(_dot(borde, arriba)) > 0.4:
        v = borde if _dot(borde, arriba) >= 0 else _opuesto(borde)
        u = _norm(_cross(v, n))
    elif abs(_dot(otro, arriba)) > 0.4:
        v = otro if _dot(otro, arriba) >= 0 else _opuesto(otro)
        u = _norm(_cross(v, n))
    else:
        u = borde if _dot(borde, (1.0, 0.0, 0.0)) >= 0 else _opuesto(borde)
        v = _norm(_cross(n, u))
    if u is None or v is None:
        return marco_cara(normal, limpios)
    origen = limpios[0]
    uv = [(_dot(_resta(punto, origen), u), _dot(_resta(punto, origen), v)) for punto in limpios]
    xs = [item[0] for item in uv]
    ys = [item[1] for item in uv]
    return {
        "normal": n,
        "u": u,
        "v": v,
        "origen": origen,
        "puntos": limpios,
        "outline": [(min(xs), min(ys)), (max(xs), min(ys)), (max(xs), max(ys)), (min(xs), max(ys))],
    }


def cordones(junta: dict) -> list[dict]:
    """Filete 3D: triángulo de cateto extruido a lo largo del cordón. Milímetros."""
    frame = junta.get("frame") or {}
    soldadura = junta.get("weld") or {}
    huella = soldadura.get("footprint")
    if not frame.get("u") or not isinstance(huella, (list, tuple)) or len(huella) < 4:
        return []
    cateto = float(soldadura.get("leg") or 6)
    otro_cateto = float(soldadura.get("other") or cateto)
    if junta.get("kind") == "hermetico":
        return _cordon_hermetico(junta, frame, huella, cateto, otro_cateto)
    return _cordon_accesorio(junta, frame, huella, cateto, int(soldadura.get("sides") or 1) >= 2, otro_cateto)


def marco_cara(normal, puntos: list[tuple[float, float, float]]) -> dict | None:
    """Rectángulo de la cara en su plano. Y de la foto sigue el alto del tanque."""
    n = _norm(_vector(normal) or (0.0, 0.0, 0.0))
    limpios = [_vector(punto) for punto in puntos]
    if n is None or any(punto is None for punto in limpios) or len(limpios) < 3:
        return None
    arriba = (0.0, 1.0, 0.0)
    if abs(_dot(arriba, n)) > 0.85:
        arriba = (1.0, 0.0, 0.0)
    escala = _dot(arriba, n)
    v = _norm(_resta(arriba, (n[0] * escala, n[1] * escala, n[2] * escala)))
    u = _norm(_cross(v, n)) if v is not None else None
    if u is None or v is None:
        return None
    origen = limpios[0]
    uv = [(_dot(_resta(punto, origen), u), _dot(_resta(punto, origen), v)) for punto in limpios]
    xs = [item[0] for item in uv]
    ys = [item[1] for item in uv]
    return {
        "normal": n,
        "u": u,
        "v": v,
        "origen": origen,
        "puntos": limpios,
        "outline": [(min(xs), min(ys)), (max(xs), min(ys)), (max(xs), max(ys)), (min(xs), max(ys))],
    }


def simbolo(kind: str, largo_mm: float, cara: str = "") -> dict:
    """Cateto de taller, en mm. Hermético: filete a dos caras, 100-300. Base y tapa usan 6/8.

    Un tanque Vantran no usa esta tabla: `aplicar_pauta_vantran` la sustituye
    por la de los planos (1/4, 5/16, 3/8 y paso 4-20).
    """
    if kind == "hermetico":
        otro = 8 if str(cara).upper() in {"BASE", "TOP"} else 6
        return {"leg": "6", "other": str(otro), "pitch": "100-300", "sides": 2, "typ": True}
    largo = float(largo_mm or 0)
    if 0 < largo < 80:
        return {"leg": "3", "other": "3", "pitch": "", "sides": 2, "typ": True}
    if 0 < largo < 160:
        return {"leg": "5", "other": "5", "pitch": "", "sides": 2, "typ": False}
    return {"leg": "6", "other": "", "pitch": "", "sides": 1, "typ": True}


def aplicar_pauta_vantran(juntas: list[dict]) -> list[dict]:
    """Sustituye el cateto de taller por la pauta de los planos Vantran.

    Los dos planos repiten lo mismo: brida, niple y oil boss a 1/4"; unión de
    paredes y unión de pared con base a 1/4"; cáncamo a 3/8"; tierra a 1/4".
    El marco de la base va a 5/16" completo por fuera y 5/16" a 4-20 por dentro.
    Lo que el plano no nombra conserva el cateto de taller.
    """
    for junta in juntas:
        soldadura = junta.get("weld")
        if not isinstance(soldadura, dict):
            continue
        pauta = _pauta_vantran(junta)
        if pauta:
            soldadura.update(pauta)
    return juntas


def _pauta_vantran(junta: dict) -> dict:
    texto = f"{junta.get('title') or ''} {junta.get('id') or ''}".casefold()
    if junta.get("kind") == "hermetico":
        return {"leg": "6", "other": "6", "pitch": "", "sides": 2, "typ": True}
    if any(marca in texto for marca in ("tank-base", "tank_base", "cuadrobase", "cuadro base", "plaquita")):
        return {"leg": "8", "other": "8", "pitch": "", "pitch_other": "4-20", "sides": 2, "typ": True}
    if any(marca in texto for marca in ("lifting lug", "lifting_lug", "d3000")):
        return {"leg": "9.525", "other": "", "pitch": "", "sides": 1, "typ": True}
    if any(marca in texto for marca in ("cover", " lid", "tapa")) and "cellar" not in texto:
        return {"leg": "8", "other": "", "pitch": "4-20", "sides": 1, "typ": True}
    if any(
        marca in texto
        for marca in ("flange", "nipple", "oil boss", "oil_boss", "oil gauge", "oil_gauge", "ground", "tierra", "boss")
    ):
        return {"leg": "6", "other": "", "pitch": "", "sides": 1, "typ": True}
    if "jacking" in texto:
        return {"leg": "6", "other": "", "pitch": "", "sides": 1, "typ": True}
    if "parking" in texto:
        return {"leg": "3", "other": "", "pitch": "", "sides": 1, "typ": True}
    return {}


def armar_juntas(muros: dict, accesorios: list[dict], holgura_mm: float = 40.0) -> list[dict]:
    centro_tanque = _centro_de_muros(muros)
    juntas: list[dict] = []
    for izquierda, derecha in PARES:
        a = muros.get(izquierda)
        b = muros.get(derecha)
        if not a or not b or not _costura_permitida(izquierda, derecha, muros):
            continue
        junta = _hermetica(a, b, izquierda, derecha, holgura_mm)
        if junta:
            junta["centro_tanque"] = centro_tanque
            junta["placas_tanque"] = [muro.get("occ") for muro in muros.values() if muro.get("occ") is not None]
            juntas.append(junta)
    for item in accesorios:
        for cara in _caras_de_apoyo(item, muros):
            muro = muros.get(cara)
            if not muro:
                continue
            copia = dict(item)
            copia["cara"] = cara
            junta = _accesorio(muro, copia, holgura_mm)
            if junta:
                junta["centro_tanque"] = centro_tanque
                juntas.append(junta)
    return juntas


def _nombre_placa(muro) -> str:
    if not muro:
        return ""
    occ = muro.get("occ")
    if occ is not None:
        try:
            return str(occ.Name)
        except Exception:
            pass
    return str(muro.get("nombre") or "")


def _tapa_sin_cellar(muro) -> bool:
    """Una tapa o lid sin collar no se suelda al muro. El cellar sí."""
    texto = _nombre_placa(muro).casefold()
    if not texto:
        return False
    if any(marca in texto for marca in ("cellar", "collar", "cuello")):
        return False
    return any(marca in texto for marca in ("lid", "cover", "tapa"))


def _costura_permitida(izquierda: str, derecha: str, muros: dict) -> bool:
    """Una tapa suelta no se suelda. La base sigue cerrando con los cuatro segmentos."""
    if "TOP" not in {izquierda, derecha}:
        return True
    return not _tapa_sin_cellar(muros.get("TOP"))


_APOYO_MM = 12.0


def _caras_de_apoyo(item: dict, muros: dict) -> list[str]:
    """Solo el segmento donde va la pieza, y solo si de verdad lo toca.

    Un accesorio no se suelda a otro accesorio ni a un muro de al lado.
    """
    asignada = str(item.get("cara") or "").upper()
    muro = muros.get(asignada)
    if muro is None or not _apoya_en(item, muro):
        return []
    return [asignada]


def _largo_de_apoyo(occ, muro: dict) -> float:
    """Cuánto de la pieza está pegado a esa placa. Sirve para elegir su segmento."""
    if occ is None or muro is None:
        return 0.0
    aristas = _aristas_mm(occ)
    if not aristas:
        return 0.0
    mayor = 0.0
    for origen, normal in _planos_paralelos(muro.get("occ"), muro.get("normal")):
        tocadas = _banda_de_contacto(aristas, origen, normal)
        mayor = max(mayor, sum(_largo_vector(_resta(fin, inicio)) for inicio, fin in tocadas))
    return mayor


def _hay_apoyo(aristas, circulos, planos) -> bool:
    """La pieza toca la placa por una arista o por el círculo de una brida."""
    for origen, normal in planos:
        if aristas and _banda_de_contacto(aristas, origen, normal):
            return True
        if _anillos_exteriores(circulos, origen, normal, 12.0):
            return True
    return False


def _apoya_en(item: dict, muro: dict) -> bool:
    occ = item.get("occ")
    host = muro.get("occ")
    if occ is not None and host is not None:
        planos = list(_planos_paralelos(host, muro.get("normal")))
        return _hay_apoyo(_aristas_mm(occ), _circulos_mm(occ), planos)
    puntos = item.get("puntos") or _esquinas(item.get("caja"))
    if not _cerca(puntos, muro, _APOYO_MM):
        return False
    return _solapa_contorno(puntos, muro) >= 8.0


def _solapa_contorno(puntos, muro: dict) -> float:
    huella = _huella(puntos, muro)
    outline = muro.get("outline") or []
    if not huella or len(outline) < 2:
        return 0.0
    xs = [float(punto[0]) for punto in outline]
    ys = [float(punto[1]) for punto in outline]
    u0 = max(float(huella[0]), min(xs))
    u1 = min(float(huella[2]), max(xs))
    v0 = max(float(huella[1]), min(ys))
    v1 = min(float(huella[3]), max(ys))
    if u1 - u0 < 8.0 or v1 - v0 < 8.0:
        return 0.0
    return max(u1 - u0, v1 - v0)


def _centro_de_muros(muros: dict):
    """El interior del tanque. Sirve para no dejar el filete hermético por dentro."""
    puntos = []
    for muro in muros.values():
        for punto in muro.get("puntos") or []:
            vector = _vector(punto)
            if vector is not None:
                puntos.append(vector)
    if not puntos:
        return None
    return tuple(sum(punto[eje] for punto in puntos) / len(puntos) for eje in range(3))


def _hermetica(a: dict, b: dict, nombre_a: str, nombre_b: str, holgura: float) -> dict | None:
    na = _vector(a.get("normal"))
    nb = _vector(b.get("normal"))
    if na is None or nb is None or abs(_dot(na, nb)) > 0.5:
        return None
    if not _cerca(a.get("puntos") or [], b, holgura) or not _cerca(b.get("puntos") or [], a, holgura):
        return None
    direccion = _norm(_cross(na, nb))
    if direccion is None:
        return None
    largo = _solape(a.get("puntos") or [], b.get("puntos") or [], direccion)
    if largo < 20:
        return None
    vista, otra = _quien_se_ve(nombre_a, nombre_b)
    muro = a if vista == nombre_a else b
    spec = simbolo("hermetico", largo, otra if otra in {"BASE", "TOP"} else vista)
    otro_muro = b if muro is a else a
    return {
        "id": f"{vista}_{otra}",
        "title": f"{vista} / {otra}",
        "cara": vista,
        "outline": list(muro.get("outline") or []),
        "kind": "hermetico",
        "frame": _frame(muro),
        "frame_otro": _frame(otro_muro),
        "outline_otro": list(otro_muro.get("outline") or []),
        "host": muro.get("occ"),
        "otro": otro_muro.get("occ"),
        "pieza": None,
        "centro": None,
        "caja": None,
        "weld": {
            "mark": "",
            "length": _largo(largo),
            "anchor": (0.5, 0.04),
            "footprint": _huella_hermetica(muro, otro_muro),
            "tone": "hermetico",
            **spec,
        },
    }


def _accesorio(muro: dict, item: dict, holgura: float) -> dict | None:
    _ = holgura
    puntos = item.get("puntos") or _esquinas(item.get("caja"))
    largo = _tramo_en_plano(puntos, muro)
    if largo < 8:
        return None
    cara = str(item.get("cara") or muro.get("cara") or "")
    spec = simbolo("accesorio", largo, cara)
    nombre = str(item.get("nombre") or "Accesorio")
    return {
        "id": f"{cara}_{nombre}",
        "title": f"{cara} / {nombre}",
        "cara": cara,
        "outline": list(muro.get("outline") or []),
        "kind": "accesorio",
        "frame": _frame(muro),
        "host": muro.get("occ"),
        "otro": None,
        "pieza": item.get("occ"),
        "centro": item.get("centro"),
        "caja": item.get("caja"),
        "weld": {
            "mark": "",
            "length": _largo(largo),
            "anchor": _ancla(item.get("centro"), muro),
            "footprint": _huella(puntos, muro),
            "tone": "accesorio",
            **spec,
        },
    }


def _cordon_accesorio(junta, frame, huella, cateto, ambos, otro_cateto) -> list[dict]:
    """Un filete por arista de la pieza que de verdad toca la placa.

    El filete va en la cara donde está la pieza. Si se elige la de atrás, el
    cordón queda dentro del tanque y la cota no lo ve.
    """
    normal_muro = _norm(_vector(frame.get("normal"))) or (0.0, 0.0, 1.0)
    candidatos = list(_planos_paralelos(junta.get("host"), normal_muro))
    if not candidatos:
        candidatos = [_plano_de_contacto(frame, junta.get("host"), junta.get("centro"))]
    grupos = _aristas_por_cuerpo(junta.get("pieza"))
    circulos = _circulos_mm(junta.get("pieza"))
    opciones = []
    for origen, normal in candidatos:
        aristas = []
        for crudas in grupos:
            tocadas = _banda_de_contacto(crudas, origen, normal)
            aristas.extend(_solo_cordones_largos(_unir_colineales(_contorno_exterior(tocadas, normal), normal)))
        anillos = _anillos_exteriores(circulos, origen, normal, 12.0)
        opciones.append((origen, normal, aristas, anillos))
    if str(junta.get("cara") or "").upper() == "BASE" and _pieza_del_lado_del_tanque(
        opciones, junta.get("centro"), junta.get("centro_tanque")
    ):
        hacia_tanque = _caras_hacia_el_tanque(opciones, junta.get("centro_tanque"))
        if hacia_tanque:
            opciones = hacia_tanque
    elegido = _mejor_contacto(opciones, junta.get("centro"))
    if elegido is None:
        return []
    origen, normal, aristas, anillos = elegido
    if aristas:
        anillos = []
    centro = _vector(junta.get("centro"))
    if centro is not None and _dot(_resta(centro, origen), normal) < 0:
        normal = _opuesto(normal)
    piezas = []
    for indice, (inicio, fin) in enumerate(aristas):
        inicio = _al_plano(inicio, origen, normal)
        fin = _al_plano(fin, origen, normal)
        nombre = junta["id"] if indice == 0 else f"{junta['id']}_{indice + 1}"
        piezas.extend(
            _filetes_de_arista(
                nombre,
                "accesorio",
                inicio,
                fin,
                normal,
                junta.get("centro"),
                cateto,
                ambos and len(aristas) == 1,
                otro_cateto,
            )
        )
    for indice, anillo in enumerate(anillos):
        nombre = junta["id"] if not piezas and indice == 0 else f"{junta['id']}_R{indice + 1}"
        piezas.append(_filete_anillo(nombre, "accesorio", anillo["centro"], normal, anillo["radio"], cateto))
    return piezas


def _cordon_hermetico(junta, frame, huella, cateto, otro_cateto) -> list[dict]:
    """Un filete sobre la arista más externa de la junta. Las dos patas salen del tanque."""
    otro = junta.get("frame_otro") or {}
    n1 = _vector(frame.get("normal"))
    n2 = _vector(otro.get("normal"))
    if n1 is None or n2 is None:
        return []
    centro = _vector(junta.get("centro_tanque"))
    planos_a = _planos_paralelos(junta.get("host"), n1)
    planos_b = _planos_paralelos(junta.get("otro"), n2)
    raiz = _raiz_externa(junta, frame, otro, centro)
    if raiz is not None:
        (inicio, fin), pata_1, pata_2 = raiz
        largo = _largo_vector(_resta(fin, inicio))
        return [_filete(junta["id"], "hermetico", inicio, _resta(fin, inicio), pata_2, pata_1, cateto, largo)]
    cara_a = _elegir_plano_hermetico(planos_a, n1, centro)
    cara_b = _elegir_plano_hermetico(planos_b, n2, centro)
    tramo = None
    if cara_a is not None and cara_b is not None:
        tramo = _eje_de_planos(frame, junta.get("outline") or [], cara_a, otro, junta.get("outline_otro") or [], cara_b)
    if tramo is None:
        tramo = _eje_compartido(frame, junta.get("outline") or [], otro, junta.get("outline_otro") or [])
    if tramo is None:
        u0, v0, u1, v1 = (float(huella[0]), float(huella[1]), float(huella[2]), float(huella[3]))
        esquina = _mundo(frame, u0, v0)
        fin = _mundo(frame, u1, v1)
    else:
        esquina, fin = tramo
    elegida = _arista_mas_afuera(_aristas_de(junta.get("host")) + _aristas_de(junta.get("otro")), esquina, fin, centro)
    if elegida is not None:
        esquina, fin = elegida
    direccion = _norm(_resta(fin, esquina))
    if direccion is None:
        return []
    largo = _largo_vector(_resta(fin, esquina))
    if largo < 20:
        return []
    return _filete_por_fuera(junta["id"], "hermetico", esquina, fin, n1, centro, cateto)


_DENTRO = 30978


def _raiz_externa(junta, frame, otro, centro):
    """Rincón real entre las dos placas, el más afuera. Inventor dice dónde hay metal."""
    host, otra = junta.get("host"), junta.get("otro")
    cuerpos_a, cuerpos_b = _lista_cuerpos(host), _lista_cuerpos(otra)
    if not cuerpos_a or not cuerpos_b:
        return None
    tanque = [cuerpo for occ in junta.get("placas_tanque") or [] for cuerpo in _lista_cuerpos(occ)]

    def material(punto):
        if _metal(cuerpos_a, punto):
            return "a"
        if _metal(cuerpos_b, punto):
            return "b"
        return None

    def abierto(punto, rumbo):
        if not tanque:
            return True
        paso = 25.0
        distancia = paso
        while distancia <= 4000.0:
            if _metal(tanque, _suma_vec(punto, _escala(rumbo, distancia))):
                return False
            distancia += paso
        return True

    aristas = _aristas_de(host) + _aristas_de(otra)
    raiz = _raiz_por_cuadrantes(aristas, frame.get("normal"), otro.get("normal"), centro, material, abierto)
    if raiz is not None:
        return raiz
    return _boca_de_ranura(aristas, frame.get("normal"), otro.get("normal"), centro, material)


def _ejes_de_junta(n1, n2):
    n1, n2 = _norm(_vector(n1)), _norm(_vector(n2))
    if n1 is None or n2 is None:
        return None
    direccion = _norm(_cross(n1, n2))
    e2 = _norm(_resta(n2, _escala(n1, _dot(n2, n1))))
    if direccion is None or e2 is None:
        return None
    return direccion, n1, e2


def _cuadrantes(medio, e1, e2, material, radio):
    salida = {}
    for s1 in (1.0, -1.0):
        for s2 in (1.0, -1.0):
            prueba = _suma_vec(medio, _escala(_suma_vec(_escala(e1, s1), _escala(e2, s2)), radio * 0.7071))
            salida[(s1, s2)] = material(prueba)
    return salida


def _aristas_de_junta(aristas, direccion, centro, piso):
    """Aristas largas paralelas al cordón, de la más lejana del centro a la más cercana."""
    salida = []
    for a, b in aristas:
        eje = _norm(_resta(b, a))
        if eje is None or abs(_dot(eje, direccion)) < 0.995 or _largo_vector(_resta(b, a)) < piso:
            continue
        medio = _escala(_suma_vec(a, b), 0.5)
        afuera = _resta(medio, centro)
        lejos = _largo_vector(_resta(afuera, _escala(eje, _dot(afuera, eje))))
        salida.append((lejos, (a, b), medio))
    salida.sort(key=lambda item: -item[0])
    return salida


def _raiz_por_cuadrantes(aristas, n1, n2, centro, material, abierto=None, radio: float = 1.5, piso: float = 150.0):
    """Raíz = arista con metal de las dos placas en tres cuadrantes y aire en uno.

    Un canto convexo tiene un solo cuadrante con metal; una cara lisa, dos. El
    filete va en el cuadrante de aire, con una pata sobre cada placa. Si desde
    ese aire no se sale del tanque, el rincón es interior y no se publica.
    """
    ejes = _ejes_de_junta(n1, n2)
    centro = _vector(centro)
    if ejes is None or centro is None:
        return None
    direccion, e1, e2 = ejes
    for _lejos, arista, medio in _aristas_de_junta(aristas, direccion, centro, piso):
        cuadrantes = _cuadrantes(medio, e1, e2, material, radio)
        aire = [clave for clave, quien in cuadrantes.items() if quien is None]
        placas = {quien for quien in cuadrantes.values() if quien is not None}
        if len(aire) != 1 or len(placas) < 2:
            continue
        s1, s2 = aire[0]
        rumbo = _norm(_suma_vec(_escala(e1, s1), _escala(e2, s2)))
        if abierto is not None and not abierto(_suma_vec(medio, _escala(rumbo, radio)), rumbo):
            continue
        return arista, _escala(e1, s1), _escala(e2, s2)
    return None


def _boca_de_ranura(aristas, n1, n2, centro, material, radio: float = 1.5, piso: float = 150.0, alcance: float = 30.0):
    """Sin rincón externo (ceja doblada bajo la tapa): canto de una placa con la otra justo enfrente.

    El filete se apoya en la cara del canto que mira a la otra placa y llena la boca.
    """
    ejes = _ejes_de_junta(n1, n2)
    centro = _vector(centro)
    if ejes is None or centro is None:
        return None
    direccion, e1, e2 = ejes
    for _lejos, arista, medio in _aristas_de_junta(aristas, direccion, centro, piso):
        cuadrantes = _cuadrantes(medio, e1, e2, material, radio)
        llenos = [(clave, quien) for clave, quien in cuadrantes.items() if quien is not None]
        if len(llenos) != 1:
            continue
        (m1, m2), dueno = llenos[0]
        s1, s2 = (-m1, m2) if dueno == "a" else (m1, -m2)
        if cuadrantes.get((s1, s2)) is not None:
            continue
        rumbo = _norm(_suma_vec(_escala(e1, s1), _escala(e2, s2)))
        otra = "b" if dueno == "a" else "a"
        distancia = 2.0
        alcanza = False
        while distancia <= alcance:
            if material(_suma_vec(medio, _escala(rumbo, distancia))) == otra:
                alcanza = True
                break
            distancia += 2.0
        if alcanza:
            return arista, _escala(e1, s1), _escala(e2, s2)
    return None


def _lista_cuerpos(occ) -> list:
    cuerpos = _cuerpos(occ) if occ is not None else None
    if cuerpos is None:
        return []
    salida = []
    try:
        for indice in range(1, int(cuerpos.Count) + 1):
            salida.append(cuerpos.Item(indice))
    except Exception:
        return salida
    return salida


def _metal(cuerpos, punto) -> bool:
    for cuerpo in cuerpos:
        try:
            resultado = cuerpo.IsPointInside([punto[0] / 10.0, punto[1] / 10.0, punto[2] / 10.0])
            estado = resultado[0] if isinstance(resultado, tuple) else resultado
            if int(estado) == _DENTRO:
                return True
        except Exception:
            continue
    return False


def _caras_con_aire(planos, centro):
    """La piel más lejos del centro tiene el aire hacia afuera; las demás, hacia el tanque."""

    def separacion(plano) -> float:
        origen, cara = plano
        return abs(_dot(_resta(origen, centro), _norm(cara) or cara))

    externa = max(planos, key=separacion)
    return [(plano[0], plano[1], plano is not externa) for plano in planos]


def _aristas_de(occ) -> list[tuple]:
    if occ is None:
        return []
    return _aristas_mm(occ)


def _arista_mas_afuera(aristas, inicio, fin, centro, holgura: float = 120.0):
    """La arista larga paralela al cruce y más lejos del centro. Esa es la esquina externa."""
    direccion = _norm(_resta(fin, inicio))
    centro = _vector(centro)
    origen = _vector(inicio)
    if direccion is None or centro is None or origen is None:
        return None
    largo = _largo_vector(_resta(fin, inicio))
    piso = max(200.0, largo * 0.35)
    bajo = _dot(origen, direccion)
    alto = _dot(fin, direccion)
    if alto < bajo:
        bajo, alto = alto, bajo
    mejor = None
    mejor_lejos = -1.0
    for a, b in aristas:
        eje = _norm(_resta(b, a))
        medida = _largo_vector(_resta(b, a))
        if eje is None or abs(_dot(eje, direccion)) < 0.98 or medida < piso:
            continue
        punto = _escala(_suma_vec(a, b), 0.5)
        if _distancia_a_recta(punto, origen, direccion) > holgura:
            continue
        axial = _dot(punto, direccion)
        if axial < bajo - 50.0 or axial > alto + 50.0:
            continue
        lejos = _largo_vector(_resta(punto, centro))
        if lejos > mejor_lejos:
            mejor_lejos = lejos
            mejor = (a, b)
    return mejor


def _distancia_a_recta(punto, origen, direccion) -> float:
    delta = _resta(punto, origen)
    axial = _dot(delta, direccion)
    return _largo_vector(_resta(delta, _escala(direccion, axial)))


def _elegir_plano_hermetico(planos, normal_frame, centro):
    """Muro: la piel más lejos del centro. Base y tapa: la cara que mira al tanque."""
    centro = _vector(centro)
    normal = _norm(_vector(normal_frame))
    if not planos or centro is None or normal is None:
        return None

    def separacion(plano) -> float:
        origen, cara = plano
        eje = _norm(cara) or normal
        return abs(_dot(_resta(origen, centro), eje))

    horizontal = abs(normal[1]) > 0.85
    origen, cara = min(planos, key=separacion) if horizontal else max(planos, key=separacion)
    return origen, cara, horizontal


def _eje_de_planos(frame, outline, cara, otro, outline_otro, cara_otra):
    """Cruce de las dos caras del cordón, recortado al solape de las placas."""
    primero = _frame_sobre_plano(frame, cara[0], cara[1])
    segundo = _frame_sobre_plano(otro, cara_otra[0], cara_otra[1])
    if primero is None or segundo is None:
        return None
    return _eje_compartido(primero, outline, segundo, outline_otro)


def _frame_sobre_plano(frame, origen_plano, normal_plano):
    normal = _norm(_vector(normal_plano))
    origen = _vector(frame.get("origen"))
    plano = _vector(origen_plano)
    if normal is None or origen is None or plano is None or not frame.get("u") or not frame.get("v"):
        return None
    distancia = _dot(_resta(origen, plano), normal)
    return {**frame, "origen": _resta(origen, _escala(normal, distancia)), "normal": normal}


def _filete_en_aire(nombre, color, inicio, fin, cara_a, cara_b, centro, cateto) -> list[dict]:
    """Las dos patas quedan en el aire de la esquina, sobre las dos caras."""
    aire_a = _normal_de_aire(cara_a[1], cara_a[0], centro, cara_a[2])
    aire_b = _normal_de_aire(cara_b[1], cara_b[0], centro, cara_b[2])
    direccion = _norm(_resta(fin, inicio))
    if aire_a is None or aire_b is None or direccion is None:
        return []
    largo = _largo_vector(_resta(fin, inicio))
    if largo < 8:
        return []
    lado = _pata_sobre_la_cara(aire_b, aire_a, direccion)
    arriba = _pata_sobre_la_cara(aire_a, aire_b, direccion)
    if lado is None or arriba is None:
        return []
    return [_filete(nombre, color, inicio, direccion, arriba, lado, cateto, largo)]


def _normal_de_aire(normal, origen, centro, aire_hacia_el_centro):
    eje = _norm(_vector(normal))
    punto = _vector(origen)
    medio = _vector(centro)
    if eje is None or punto is None or medio is None:
        return None
    hacia_centro = _dot(_resta(medio, punto), eje) >= 0
    if hacia_centro == bool(aire_hacia_el_centro):
        return eje
    return _opuesto(eje)


def _pata_sobre_la_cara(aire_otra, normal_esta, direccion):
    """Sobre esta cara, perpendicular al cordón, hacia el aire de la otra."""
    vector = _resta(aire_otra, _escala(direccion, _dot(aire_otra, direccion)))
    vector = _resta(vector, _escala(normal_esta, _dot(vector, normal_esta)))
    vector = _norm(vector)
    if vector is None:
        return None
    if _dot(vector, aire_otra) < 0:
        vector = _opuesto(vector)
    return vector


def _eje_compartido(frame, outline, otro, outline_otro):
    n1 = _vector(frame.get("normal"))
    n2 = _vector(otro.get("normal"))
    o1 = _vector(frame.get("origen"))
    o2 = _vector(otro.get("origen"))
    if n1 is None or n2 is None or o1 is None or o2 is None or len(outline) < 2 or len(outline_otro) < 2:
        return None
    if abs(_dot(n1, n2)) >= 0.2:
        return None
    direccion = _norm(_cross(n1, n2))
    if direccion is None:
        return None
    esquina = _resta(o1, _escala(n2, _dot(_resta(o1, o2), n2)))
    puntos_a = [_mundo(frame, float(p[0]), float(p[1])) for p in outline]
    puntos_b = [_mundo(otro, float(p[0]), float(p[1])) for p in outline_otro]
    da = [_dot(p, direccion) for p in puntos_a]
    db = [_dot(p, direccion) for p in puntos_b]
    bajo = max(min(da), min(db))
    alto = min(max(da), max(db))
    if alto - bajo < 20:
        return None
    base = _dot(esquina, direccion)
    return (
        _suma_vec(esquina, _escala(direccion, bajo - base)),
        _suma_vec(esquina, _escala(direccion, alto - base)),
    )


def _suma_vec(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _solo_externos(aristas, centro) -> list[tuple]:
    """De un mismo canto, el filete de afuera. El de adentro no se publica."""
    centro = _vector(centro)
    if centro is None or len(aristas) < 2:
        return aristas
    vivos = []
    usados = [False] * len(aristas)
    for indice, arista in enumerate(aristas):
        if usados[indice]:
            continue
        direccion = _norm(_resta(arista[1], arista[0]))
        if direccion is None:
            usados[indice] = True
            vivos.append(arista)
            continue
        grupo = [indice]
        medio = _escala(_suma_vec(arista[0], arista[1]), 0.5)
        largo = _largo_vector(_resta(arista[1], arista[0]))
        for otro_indice in range(indice + 1, len(aristas)):
            if usados[otro_indice]:
                continue
            otra = aristas[otro_indice]
            otra_dir = _norm(_resta(otra[1], otra[0]))
            if otra_dir is None or abs(_dot(direccion, otra_dir)) < 0.985:
                continue
            otro_medio = _escala(_suma_vec(otra[0], otra[1]), 0.5)
            delta = _resta(otro_medio, medio)
            axial = _dot(delta, direccion)
            lateral = _largo_vector(_resta(delta, _escala(direccion, axial)))
            otro_largo = _largo_vector(_resta(otra[1], otra[0]))
            if lateral > 25.0 or abs(axial) > max(largo, otro_largo):
                continue
            grupo.append(otro_indice)
        for marca in grupo:
            usados[marca] = True

        def lejos(candidato: int) -> float:
            a, b = aristas[candidato]
            punto = _escala(_suma_vec(a, b), 0.5)
            return _largo_vector(_resta(punto, centro))

        vivos.append(aristas[max(grupo, key=lejos)])
    return vivos


def _filete_por_fuera(nombre, color, inicio, fin, normal_placa, centro_tanque, cateto) -> list[dict]:
    """El triángulo queda en la esquina exterior. Las dos patas apuntan fuera del tanque."""
    normal = _norm(_vector(normal_placa))
    direccion = _norm(_resta(fin, inicio))
    if normal is None or direccion is None:
        return []
    largo = _largo_vector(_resta(fin, inicio))
    if largo < 8:
        return []
    medio = _escala(_suma_vec(inicio, fin), 0.5)
    centro = _vector(centro_tanque)
    afuera = _resta(medio, centro) if centro is not None else normal
    en_plano = _resta(afuera, _escala(normal, _dot(afuera, normal)))
    en_plano = _resta(en_plano, _escala(direccion, _dot(en_plano, direccion)))
    lado = _norm(en_plano)
    if lado is None:
        lado = _norm(_cross(normal, direccion))
    if lado is None:
        return []
    if _dot(lado, afuera) < 0:
        lado = _opuesto(lado)
    arriba = normal if _dot(normal, afuera) >= 0 else _opuesto(normal)
    return [_filete(nombre, color, inicio, direccion, arriba, lado, cateto, largo)]


def _filetes_de_arista(nombre, color, inicio, fin, normal_placa, centro_pieza, cateto, ambos, otro_cateto) -> list[dict]:
    """Triángulo en la esquina: una pata sobre la placa, saliendo de la pieza, y la otra hacia la pieza."""
    normal = _norm(_vector(normal_placa))
    direccion = _norm(_resta(fin, inicio))
    if normal is None or direccion is None:
        return []
    largo = _largo_vector(_resta(fin, inicio))
    if largo < 8:
        return []
    medio = _escala(_suma_vec(inicio, fin), 0.5)
    centro = _vector(centro_pieza)
    hacia = _resta(centro, medio) if centro is not None else None
    if hacia is not None:
        hacia = _resta(hacia, _escala(normal, _dot(hacia, normal)))
        hacia = _resta(hacia, _escala(direccion, _dot(hacia, direccion)))
    if hacia is None or _largo_vector(hacia) < 1.0:
        lado = _norm(_cross(normal, direccion))
    else:
        lado = _norm(_escala(hacia, -1.0))
    if lado is None:
        return []
    if centro is not None and _dot(_resta(centro, medio), normal) < 0:
        arriba = _opuesto(normal)
    else:
        arriba = normal
    piezas = [_filete(nombre, color, inicio, direccion, arriba, lado, cateto, largo)]
    if ambos:
        piezas.append(_filete(f"{nombre}_B", color, inicio, direccion, arriba, _opuesto(lado), otro_cateto, largo))
    return piezas


def _solo_cordones_largos(aristas) -> list[tuple]:
    """El canto corto de un ángulo (el espesor) no es un cordón.

    Un marco cerrado sí conserva sus cuatro lados, aunque uno sea más corto.
    """
    if len(aristas) < 2:
        return aristas
    largos = [_largo_vector(_resta(fin, inicio)) for inicio, fin in aristas]
    if len(aristas) >= 4:
        return [arista for arista, largo in zip(aristas, largos) if largo >= 25.0]
    mayor = max(largos)
    piso = max(25.0, mayor * 0.35)
    return [arista for arista, largo in zip(aristas, largos) if largo >= piso]


def _largo_contacto(opcion) -> float:
    _origen, _normal, aristas, anillos = opcion
    largo = sum(_largo_vector(_resta(fin, inicio)) for inicio, fin in aristas)
    largo += sum(2.0 * math.pi * float(anillo["radio"]) for anillo in anillos)
    return largo


def _mejor_contacto(opciones, centro=None):
    """La cara que la pieza toca. La de atrás mete el filete dentro del tanque."""
    candidatos = [opcion for opcion in opciones if _largo_contacto(opcion) > 0.0]
    if not candidatos:
        return None
    centro = _vector(centro)
    if centro is None:
        return max(candidatos, key=_largo_contacto)

    def distancia(opcion) -> float:
        origen, normal, _aristas, _anillos = opcion
        eje = _norm(_vector(normal)) or (0.0, 0.0, 1.0)
        return abs(_dot(_resta(centro, origen), eje))

    return min(candidatos, key=lambda opcion: (distancia(opcion), -_largo_contacto(opcion)))


def _planos_paralelos(host, normal_muro) -> list[tuple]:
    """Caras del muro paralelas a la placa: exterior, interior y refuerzos."""
    if host is None:
        return []
    clave = id(host)
    guardado = _PLANOS_MURO.get(clave)
    if guardado is not None:
        return guardado
    normal_muro = _norm(_vector(normal_muro))
    if normal_muro is None:
        _PLANOS_MURO[clave] = []
        return []
    cuerpos = _cuerpos(host)
    if cuerpos is None:
        _PLANOS_MURO[clave] = []
        return []
    centro, matriz = _contexto_mm(host)
    grupos = []
    crudas = []
    try:
        total = int(cuerpos.Count)
    except Exception:
        total = 0
    for cuerpo in range(1, total + 1):
        try:
            caras = cuerpos.Item(cuerpo).Faces
            cantidad = int(caras.Count)
        except Exception:
            continue
        for indice in range(1, cantidad + 1):
            try:
                cara = caras.Item(indice)
                if int(cara.SurfaceType) != 5890:
                    continue
                geometria = cara.Geometry
                raiz = geometria.RootPoint
                vector = geometria.Normal
                area = float(cara.Evaluator.Area)
            except Exception:
                continue
            crudas.append(
                (
                    (float(raiz.X), float(raiz.Y), float(raiz.Z)),
                    (float(vector.X), float(vector.Y), float(vector.Z)),
                    area,
                )
            )
    aplicar = _usar_matriz(host, [punto for punto, _normal, _area in crudas], matriz)
    for crudo, normal, area in crudas:
        origen = _mm_ensamble(crudo, centro, matriz, aplicar)
        if aplicar and matriz:
            normal = (
                matriz[0][0] * normal[0] + matriz[0][1] * normal[1] + matriz[0][2] * normal[2],
                matriz[1][0] * normal[0] + matriz[1][1] * normal[1] + matriz[1][2] * normal[2],
                matriz[2][0] * normal[0] + matriz[2][1] * normal[1] + matriz[2][2] * normal[2],
            )
        normal = _norm(normal)
        if normal is None or abs(_dot(normal, normal_muro)) < 0.97:
            continue
        altura = _dot(origen, normal_muro)
        grupo = None
        for candidato in grupos:
            if abs(candidato["altura"] - altura) <= 1.0:
                grupo = candidato
                break
        if grupo is None:
            grupos.append({"altura": altura, "area": area, "origen": origen, "normal": normal})
        elif area > grupo["area"]:
            grupo["area"] = area
            grupo["origen"] = origen
            grupo["normal"] = normal
    planos = [(grupo["origen"], grupo["normal"]) for grupo in grupos]
    _PLANOS_MURO[clave] = planos
    return planos


_PLANOS_MURO: dict = {}
_ARISTAS_MM: dict = {}
_ARISTAS_CUERPO: dict = {}


def _plano_de_contacto(frame, host, centro_pieza):
    """La cara de la placa que mira hacia la pieza, no la de atrás."""
    normal = _norm(_vector(frame.get("normal"))) or (0.0, 0.0, 1.0)
    origen = _vector(frame.get("origen")) or (0.0, 0.0, 0.0)
    centro = _vector(centro_pieza)
    if host is None or centro is None:
        return origen, normal
    try:
        caja = host.RangeBox
        alturas = []
        for x in (float(caja.MinPoint.X), float(caja.MaxPoint.X)):
            for y in (float(caja.MinPoint.Y), float(caja.MaxPoint.Y)):
                for z in (float(caja.MinPoint.Z), float(caja.MaxPoint.Z)):
                    alturas.append(_dot((x * 10.0, y * 10.0, z * 10.0), normal))
    except Exception:
        return origen, normal
    if not alturas:
        return origen, normal
    bajo, alto = min(alturas), max(alturas)
    if _dot(centro, normal) >= (bajo + alto) / 2.0:
        altura, sentido = alto, normal
    else:
        altura, sentido = bajo, _opuesto(normal)
    return _suma_vec(origen, _escala(normal, altura - _dot(origen, normal))), sentido


def _aristas_sobre_plano(occ, origen, normal, holgura: float) -> list[tuple]:
    """Aristas de la pieza que están pegadas al plano. Milímetros."""
    return _cerca_del_plano(_aristas_mm(occ), origen, normal, holgura)


def _aristas_mm(occ) -> list[tuple]:
    return [arista for grupo in _aristas_por_cuerpo(occ) for arista in grupo]


def _es_ensamble_occ(occ) -> bool:
    try:
        return int(occ.DefinitionDocumentType) == 12291
    except Exception:
        return False


def _clave_occ(occ):
    """Nombre y caja. El envoltorio COM se recicla y su id() mezcla dos piezas."""
    try:
        caja = occ.RangeBox
        return (
            str(occ.Name),
            round(float(caja.MinPoint.X), 3),
            round(float(caja.MinPoint.Y), 3),
            round(float(caja.MinPoint.Z), 3),
            round(float(caja.MaxPoint.X), 3),
            round(float(caja.MaxPoint.Y), 3),
            round(float(caja.MaxPoint.Z), 3),
        )
    except Exception:
        return None


def _aristas_por_cuerpo(occ) -> list[list[tuple]]:
    """Aristas rectas por sólido. Un ensamble cuenta como una sola pieza."""
    if occ is None:
        return []
    clave = _clave_occ(occ)
    guardado = _ARISTAS_CUERPO.get(clave) if clave is not None else None
    if guardado is not None:
        return guardado
    if _es_ensamble_occ(occ):
        grupos = []
        try:
            hijos = occ.SubOccurrences
            total = int(hijos.Count)
        except Exception:
            total = 0
        for indice in range(1, total + 1):
            try:
                hijo = hijos.Item(indice)
                if bool(hijo.Suppressed):
                    continue
            except Exception:
                continue
            grupos.extend(_aristas_por_cuerpo(hijo))
        if clave is not None:
            _ARISTAS_CUERPO[clave] = grupos
        return grupos
    crudas = []
    cuerpos = _cuerpos(occ)
    if cuerpos is None:
        return []
    try:
        total = int(cuerpos.Count)
    except Exception:
        return []
    for cuerpo in range(1, total + 1):
        del_cuerpo = []
        try:
            aristas = cuerpos.Item(cuerpo).Edges
            cantidad = int(aristas.Count)
        except Exception:
            continue
        tope = min(cantidad, 8000)
        for indice in range(1, tope + 1):
            try:
                arista = aristas.Item(indice)
                if not _es_recta(arista):
                    continue
                pa = arista.StartVertex.Point
                pb = arista.StopVertex.Point
            except Exception:
                continue
            del_cuerpo.append(((float(pa.X), float(pa.Y), float(pa.Z)), (float(pb.X), float(pb.Y), float(pb.Z))))
        if del_cuerpo:
            crudas.append(del_cuerpo)
    if not crudas:
        return []
    centro, matriz = _contexto_mm(occ)
    puntos = [punto for grupo in crudas for arista in grupo for punto in arista]
    aplicar = _usar_matriz(occ, puntos, matriz)
    salida = []
    for grupo in crudas:
        convertido = []
        for crudo_a, crudo_b in grupo:
            inicio = _mm_ensamble(crudo_a, centro, matriz, aplicar)
            fin = _mm_ensamble(crudo_b, centro, matriz, aplicar)
            if _largo_vector(_resta(fin, inicio)) < 8.0:
                continue
            convertido.append((inicio, fin))
        if convertido:
            salida.append(convertido)
    if clave is not None:
        _ARISTAS_CUERPO[clave] = salida
        _ARISTAS_MM[clave] = [arista for grupo in salida for arista in grupo]
    return salida


def _es_recta(arista) -> bool:
    """Una cuerda de arco no es un cordón. El barreno se quedaba con una barra atravesada."""
    try:
        geometria = arista.Geometry
    except Exception:
        return False
    try:
        float(geometria.Radius)
        return False
    except Exception:
        pass
    try:
        return geometria.Direction is not None
    except Exception:
        return False


def _banda_de_contacto(aristas, origen, normal, techo: float = 12.0, banda: float = 2.5) -> list[tuple]:
    """Aristas paralelas a la placa, en la tanda más pegada.

    Un marco puede quedar a un espesor de la cara. 2.5 mm fijos lo dejaba sin
    filete; la tanda cercana, hasta 12 mm, sí entra. La arista de atrás del
    perfil, más lejos, no.
    """
    normal = _norm(_vector(normal))
    origen = _vector(origen)
    if normal is None or origen is None:
        return []
    medidas = []
    for inicio, fin in aristas:
        lejos = max(
            abs(_dot(_resta(inicio, origen), normal)),
            abs(_dot(_resta(fin, origen), normal)),
        )
        if lejos > techo:
            continue
        medidas.append((lejos, inicio, fin))
    if not medidas:
        return []
    piso = min(item[0] for item in medidas)
    return [(inicio, fin) for lejos, inicio, fin in medidas if lejos <= piso + banda]


def _pieza_del_lado_del_tanque(opciones, centro_pieza, centro_tanque) -> bool:
    """Una solera colgada bajo la placa toca la cara de abajo. Ahí no se descarta.

    El canto que iría al piso queda fuera por la banda de 12 mm. Una pieza
    apoyada encima sí sigue usando la cara más cercana al tanque.
    """
    pieza = _vector(centro_pieza)
    tanque = _vector(centro_tanque)
    if pieza is None or tanque is None:
        return True
    pares = []
    for origen, normal, aristas, anillos in opciones:
        if not aristas and not anillos:
            continue
        raiz = _vector(origen)
        eje = _norm(_vector(normal))
        if raiz is None or eje is None:
            continue
        pares.append((abs(_dot(_resta(pieza, raiz), eje)), abs(_dot(_resta(tanque, raiz), eje))))
    if not pares:
        return True
    cerca_pieza = min(item[0] for item in pares)
    cerca_tanque = min(item[1] for item in pares)
    return any(distancia_pieza <= cerca_pieza + 2.0 and distancia_tanque <= cerca_tanque + 2.0 for distancia_pieza, distancia_tanque in pares)


def _caras_hacia_el_tanque(opciones, centro_tanque):
    """La cara de abajo de la base es el piso. El filete va en la más cercana al tanque."""
    centro = _vector(centro_tanque)
    if centro is None:
        return []
    medidas = []
    for origen, normal, aristas, anillos in opciones:
        if not aristas and not anillos:
            continue
        eje = _norm(_vector(normal))
        raiz = _vector(origen)
        if eje is None or raiz is None:
            continue
        distancia = abs(_dot(_resta(centro, raiz), eje))
        medidas.append((distancia, (origen, normal, aristas, anillos)))
    if not medidas:
        return []
    cerca = min(item[0] for item in medidas)
    return [opcion for distancia, opcion in medidas if distancia <= cerca + 2.0]


def _contorno_exterior(aristas, normal) -> list[tuple]:
    """La ranura del cáncamo no se suelda. La solera interna del bastidor sí.

    El casco quita la ranura y la horquilla, que quedan dentro del perímetro.
    Una barra del entramado también cae dentro, pero es larga y tiene la otra
    arista de su cara a unos milímetros. Esa pareja se conserva.
    """
    if len(aristas) < 3:
        return aristas
    eje = _norm(_vector(normal)) or (0.0, 0.0, 1.0)
    u, v = _ejes_de_plano(eje)
    if u is None or v is None:
        return aristas
    planos = []
    for inicio, fin in aristas:
        planos.append((_dot(inicio, u), _dot(inicio, v)))
        planos.append((_dot(fin, u), _dot(fin, v)))
    casco = _casco_convexo(planos)
    if len(casco) < 3:
        return aristas
    salida = []
    interiores = []
    for inicio, fin in aristas:
        medio = _escala(_suma_vec(inicio, fin), 0.5)
        punto = (_dot(medio, u), _dot(medio, v))
        punta = (_dot(fin, u), _dot(fin, v))
        if _sobre_el_casco(punto, casco) <= 2.0:
            salida.append((inicio, fin))
        else:
            interiores.append((inicio, fin, punto, punta))
    salida.extend(_barras_interiores(interiores, casco))
    return salida or aristas


def _barras_interiores(interiores, casco) -> list[tuple]:
    """La solera que cruza por dentro del marco, no la ranura del cáncamo."""
    salida = []
    usadas = set()
    for indice, (inicio, fin, punto, punta) in enumerate(interiores):
        if indice in usadas:
            continue
        if _largo_vector(_resta(fin, inicio)) < 400.0:
            continue
        if _sobre_el_casco(punto, casco) < 40.0:
            continue
        direccion = _norm((punta[0] - punto[0], punta[1] - punto[1], 0.0))
        if direccion is None:
            continue
        for otro, (inicio_b, fin_b, punto_b, punta_b) in enumerate(interiores):
            if otro <= indice or otro in usadas:
                continue
            if _largo_vector(_resta(fin_b, inicio_b)) < 400.0:
                continue
            if _sobre_el_casco(punto_b, casco) < 40.0:
                continue
            otra = _norm((punta_b[0] - punto_b[0], punta_b[1] - punto_b[1], 0.0))
            if otra is None or abs(direccion[0] * otra[0] + direccion[1] * otra[1]) < 0.985:
                continue
            delta = (punto_b[0] - punto[0], punto_b[1] - punto[1])
            avance = abs(delta[0] * direccion[0] + delta[1] * direccion[1])
            lateral = abs(delta[0] * direccion[1] - delta[1] * direccion[0])
            if lateral < 6.0 or lateral > 45.0 or avance > 80.0:
                continue
            usadas.add(indice)
            usadas.add(otro)
            salida.append((inicio, fin))
            salida.append((inicio_b, fin_b))
            break
    return salida


def _ejes_de_plano(normal):
    guia = (0.0, 0.0, 1.0) if abs(normal[2]) < 0.9 else (0.0, 1.0, 0.0)
    u = _norm(_cross(guia, normal))
    v = _norm(_cross(normal, u)) if u is not None else None
    return u, v


def _casco_convexo(puntos) -> list[tuple]:
    unicos = sorted({(round(punto[0], 2), round(punto[1], 2)) for punto in puntos})
    if len(unicos) <= 2:
        return unicos

    def cruz(origen, a, b) -> float:
        return (a[0] - origen[0]) * (b[1] - origen[1]) - (a[1] - origen[1]) * (b[0] - origen[0])

    inferior = []
    for punto in unicos:
        while len(inferior) >= 2 and cruz(inferior[-2], inferior[-1], punto) <= 0:
            inferior.pop()
        inferior.append(punto)
    superior = []
    for punto in reversed(unicos):
        while len(superior) >= 2 and cruz(superior[-2], superior[-1], punto) <= 0:
            superior.pop()
        superior.append(punto)
    return inferior[:-1] + superior[:-1]


def _sobre_el_casco(punto, casco) -> float:
    mejor = None
    total = len(casco)
    for indice, origen in enumerate(casco):
        fin = casco[(indice + 1) % total]
        distancia = _distancia_segmento_2d(punto, origen, fin)
        if mejor is None or distancia < mejor:
            mejor = distancia
    return mejor if mejor is not None else 0.0


def _distancia_segmento_2d(punto, inicio, fin) -> float:
    delta = (fin[0] - inicio[0], fin[1] - inicio[1])
    largo = delta[0] ** 2 + delta[1] ** 2
    if largo <= 1e-9:
        return ((punto[0] - inicio[0]) ** 2 + (punto[1] - inicio[1]) ** 2) ** 0.5
    avance = ((punto[0] - inicio[0]) * delta[0] + (punto[1] - inicio[1]) * delta[1]) / largo
    avance = min(1.0, max(0.0, avance))
    proy = (inicio[0] + delta[0] * avance, inicio[1] + delta[1] * avance)
    return ((punto[0] - proy[0]) ** 2 + (punto[1] - proy[1]) ** 2) ** 0.5


def _cerca_del_plano(aristas, origen, normal, holgura: float) -> list[tuple]:
    normal = _norm(_vector(normal))
    origen = _vector(origen)
    if normal is None or origen is None:
        return []
    salida = []
    for inicio, fin in aristas:
        if abs(_dot(_resta(inicio, origen), normal)) > holgura:
            continue
        if abs(_dot(_resta(fin, origen), normal)) > holgura:
            continue
        salida.append((inicio, fin))
    return salida


def _cuerpos(occ):
    for origen in (
        lambda: occ.SurfaceBodies,
        lambda: occ.Definition.SurfaceBodies,
    ):
        try:
            cuerpos = origen()
            if int(cuerpos.Count) > 0:
                return cuerpos
        except Exception:
            continue
    return None


def _contexto_mm(occ):
    """Centro de la caja (cm) y matriz de la instancia, una sola vez por pieza."""
    try:
        caja = occ.RangeBox
        centro = (
            (float(caja.MinPoint.X) + float(caja.MaxPoint.X)) / 2.0,
            (float(caja.MinPoint.Y) + float(caja.MaxPoint.Y)) / 2.0,
            (float(caja.MinPoint.Z) + float(caja.MaxPoint.Z)) / 2.0,
        )
    except Exception:
        centro = None
    try:
        from referencia_snapshot import _matriz

        matriz = _matriz(occ)
    except Exception:
        matriz = None
    return centro, matriz


def _aplicar_matriz(punto, matriz) -> tuple:
    return (
        matriz[0][0] * punto[0] + matriz[0][1] * punto[1] + matriz[0][2] * punto[2] + matriz[0][3],
        matriz[1][0] * punto[0] + matriz[1][1] * punto[1] + matriz[1][2] * punto[2] + matriz[1][3],
        matriz[2][0] * punto[0] + matriz[2][1] * punto[1] + matriz[2][2] * punto[2] + matriz[2][3],
    )


def _conviene_matriz(puntos, minimo, maximo, matriz) -> bool:
    """True solo si los puntos están en la pieza y la matriz los mete en el ensamble.

    La misma barra se decide entera. Si cada vértice elige por su cuenta, el
    extremo lejano se traslada y el cercano no: el filete sale de la placa.
    """
    if not matriz or not puntos or minimo is None or maximo is None:
        return False

    def dentro(punto) -> bool:
        return all(minimo[eje] - 1.0 <= punto[eje] <= maximo[eje] + 1.0 for eje in range(3))

    crudos = sum(1 for punto in puntos if dentro(punto))
    if crudos * 2 >= len(puntos):
        return False
    movidos = sum(1 for punto in puntos if dentro(_aplicar_matriz(punto, matriz)))
    return movidos > crudos


_USAR_MATRIZ: dict = {}


def _usar_matriz(occ, puntos, matriz) -> bool:
    if occ is None:
        return False
    clave = _clave_occ(occ)
    guardado = _USAR_MATRIZ.get(clave) if clave is not None else None
    if guardado is not None:
        return guardado
    minimo, maximo = _caja_cm(occ)
    flag = _conviene_matriz(puntos, minimo, maximo, matriz)
    if clave is not None:
        _USAR_MATRIZ[clave] = flag
    return flag


def _caja_cm(occ):
    try:
        caja = occ.RangeBox
        minimo = (float(caja.MinPoint.X), float(caja.MinPoint.Y), float(caja.MinPoint.Z))
        maximo = (float(caja.MaxPoint.X), float(caja.MaxPoint.Y), float(caja.MaxPoint.Z))
    except Exception:
        return None, None
    return minimo, maximo


def _mm_ensamble(punto, centro, matriz, aplicar: bool = False) -> tuple:
    """Pasa la arista a milímetros del ensamble. Inventor entrega centímetros."""
    _ = centro
    if aplicar and matriz:
        punto = _aplicar_matriz(punto, matriz)
    return (punto[0] * 10.0, punto[1] * 10.0, punto[2] * 10.0)


def _factor_mm(occ, punto) -> float:
    """La caja del ensamble está en cm. La arista puede venir en cm o en mm."""
    try:
        caja = occ.RangeBox
        centro = (
            (float(caja.MinPoint.X) + float(caja.MaxPoint.X)) / 2.0,
            (float(caja.MinPoint.Y) + float(caja.MaxPoint.Y)) / 2.0,
            (float(caja.MinPoint.Z) + float(caja.MaxPoint.Z)) / 2.0,
        )
    except Exception:
        return 10.0
    directo = _largo_vector(_resta(punto, centro))
    si_fuera_mm = _largo_vector(_resta(tuple(valor / 10.0 for valor in punto), centro))
    return 10.0 if directo <= si_fuera_mm else 1.0


def _unir_colineales(segmentos, normal) -> list[tuple]:
    """Une tramos partidos de la misma arista. No junta dos cordones paralelos separados."""
    normal = _norm(_vector(normal)) or (0.0, 0.0, 1.0)
    grupos = []
    for inicio, fin in segmentos:
        direccion = _norm(_resta(fin, inicio))
        if direccion is None:
            continue
        medio = _escala(_suma_vec(inicio, fin), 0.5)
        grupo = None
        for candidato in grupos:
            if abs(_dot(direccion, candidato["direccion"])) < 0.985:
                continue
            delta = _resta(medio, candidato["medio"])
            eje = candidato["direccion"]
            lateral = _resta(delta, _escala(eje, _dot(delta, eje)))
            lateral = _resta(lateral, _escala(normal, _dot(lateral, normal)))
            if _largo_vector(lateral) <= 3.0:
                grupo = candidato
                break
        if grupo is None:
            grupos.append({"direccion": direccion, "medio": medio, "segmentos": [(inicio, fin)]})
        else:
            grupo["segmentos"].append((inicio, fin))
    unidos = []
    for grupo in grupos:
        eje = grupo["direccion"]
        base = grupo["segmentos"][0][0]
        intervalos = []
        for inicio, fin in grupo["segmentos"]:
            a = _dot(_resta(inicio, base), eje)
            b = _dot(_resta(fin, base), eje)
            intervalos.append((min(a, b), max(a, b)))
        intervalos.sort()
        bloques = []
        for bajo, alto in intervalos:
            if not bloques or bajo > bloques[-1][1] + 3.0:
                bloques.append([bajo, alto])
            else:
                bloques[-1][1] = max(bloques[-1][1], alto)
        for bajo, alto in bloques:
            unidos.append((_suma_vec(base, _escala(eje, bajo)), _suma_vec(base, _escala(eje, alto))))
    return unidos


def _arista_de_huella(frame, huella, origen, normal) -> list[tuple]:
    if not isinstance(huella, (list, tuple)) or len(huella) < 4:
        return []
    u0, v0, u1, v1 = (float(huella[0]), float(huella[1]), float(huella[2]), float(huella[3]))
    if abs(u1 - u0) >= abs(v1 - v0):
        inicio = _mundo(frame, min(u0, u1), v0)
        fin = _mundo(frame, max(u0, u1), v0)
    else:
        inicio = _mundo(frame, u0, min(v0, v1))
        fin = _mundo(frame, u0, max(v0, v1))
    return [(_al_plano(inicio, origen, normal), _al_plano(fin, origen, normal))]


def _al_plano(punto, origen, normal):
    punto = _vector(punto)
    origen = _vector(origen)
    normal = _norm(_vector(normal))
    if punto is None or origen is None or normal is None:
        return punto
    return _resta(punto, _escala(normal, _dot(_resta(punto, origen), normal)))


def _centro_contorno(frame, outline):
    if not frame or not outline:
        return None
    xs = [float(punto[0]) for punto in outline]
    ys = [float(punto[1]) for punto in outline]
    return _mundo(frame, (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)


def _anillos_exteriores(circulos, origen, normal, holgura: float) -> list[dict]:
    """El círculo que toca la placa. El de la cara de afuera de la brida no se suelda."""
    normal = _norm(_vector(normal))
    origen = _vector(origen)
    if normal is None or origen is None:
        return []
    grupos = []
    for circulo in circulos:
        eje = _norm(_vector(circulo.get("normal")))
        centro = _vector(circulo.get("centro"))
        if eje is None or centro is None or abs(_dot(eje, normal)) < 0.97:
            continue
        distancia = abs(_dot(_resta(centro, origen), normal))
        if distancia > holgura:
            continue
        radio = float(circulo.get("radio") or 0)
        if radio < 4.0:
            continue
        proyeccion = _resta(centro, _escala(normal, _dot(_resta(centro, origen), normal)))
        grupo = None
        for candidato in grupos:
            if _largo_vector(_resta(proyeccion, candidato["proyeccion"])) <= 2.0:
                grupo = candidato
                break
        if grupo is None:
            grupos.append({"proyeccion": proyeccion, "items": [(distancia, radio, centro)]})
        else:
            grupo["items"].append((distancia, radio, centro))
    anillos = []
    for grupo in grupos:
        cerca = min(item[0] for item in grupo["items"])
        en_placa = [item for item in grupo["items"] if item[0] <= cerca + 2.5]
        _distancia, radio, centro = max(en_placa, key=lambda item: item[1])
        anillos.append({"centro": centro, "radio": radio})
    return anillos


def _circulos_mm(occ) -> list[dict]:
    """Círculos cerrados de la pieza, en milímetros. Un arco de esquina no entra."""
    if occ is None:
        return []
    if _es_ensamble_occ(occ):
        circulos = []
        try:
            hijos = occ.SubOccurrences
            total = int(hijos.Count)
        except Exception:
            return circulos
        for indice in range(1, total + 1):
            try:
                hijo = hijos.Item(indice)
                if bool(hijo.Suppressed):
                    continue
            except Exception:
                continue
            circulos.extend(_circulos_mm(hijo))
        return circulos
    cuerpos = _cuerpos(occ)
    if cuerpos is None:
        return []
    try:
        total = int(cuerpos.Count)
    except Exception:
        return []
    centro_caja, matriz = _contexto_mm(occ)
    crudos = []
    for cuerpo in range(1, total + 1):
        try:
            aristas = cuerpos.Item(cuerpo).Edges
            cantidad = int(aristas.Count)
        except Exception:
            continue
        for indice in range(1, min(cantidad, 8000) + 1):
            try:
                arista = aristas.Item(indice)
                geometria = arista.Geometry
                radio = float(geometria.Radius)
                crudo = geometria.Center
                vector = geometria.Normal
                pa = arista.StartVertex.Point
                pb = arista.StopVertex.Point
            except Exception:
                continue
            crudos.append(
                (
                    (float(crudo.X), float(crudo.Y), float(crudo.Z)),
                    (float(pa.X), float(pa.Y), float(pa.Z)),
                    (float(pb.X), float(pb.Y), float(pb.Z)),
                    (float(vector.X), float(vector.Y), float(vector.Z)),
                    radio,
                )
            )
    aplicar = _usar_matriz(occ, [centro for centro, _a, _b, _normal, _radio in crudos], matriz)
    salida = []
    for crudo, pa, pb, normal, radio in crudos:
        centro = _mm_ensamble(crudo, centro_caja, matriz, aplicar)
        inicio = _mm_ensamble(pa, centro_caja, matriz, aplicar)
        fin = _mm_ensamble(pb, centro_caja, matriz, aplicar)
        if _largo_vector(_resta(fin, inicio)) > 1.5:
            continue
        if aplicar and matriz:
            normal = (
                matriz[0][0] * normal[0] + matriz[0][1] * normal[1] + matriz[0][2] * normal[2],
                matriz[1][0] * normal[0] + matriz[1][1] * normal[1] + matriz[1][2] * normal[2],
                matriz[2][0] * normal[0] + matriz[2][1] * normal[1] + matriz[2][2] * normal[2],
            )
        normal = _norm(normal)
        if normal is None:
            continue
        salida.append({"centro": centro, "normal": normal, "radio": radio * 10.0})
    return salida


def _filete_anillo(nombre, color, centro, eje, radio, cateto) -> dict:
    return {
        "nombre": nombre,
        "color": color,
        "forma": "anillo",
        "centro": centro,
        "normal": _norm(eje) or eje,
        "radio": float(radio),
        "cateto": float(cateto),
    }


def _filete(nombre, color, esquina, direccion, normal, lado, cateto, largo) -> dict:
    return {
        "nombre": nombre,
        "color": color,
        "esquina": esquina,
        "direccion": _norm(direccion) or direccion,
        "normal": _norm(normal) or normal,
        "lado": _norm(lado) or lado,
        "cateto": float(cateto),
        "largo": float(largo),
    }


def _sobre_la_cara(junta, frame, esquina, hacia):
    """El filete nace en la cara que toca la pieza y crece hacia afuera del espesor."""
    host = junta.get("host")
    normal = _norm(_vector(frame.get("normal")))
    centro = _vector(junta.get("centro"))
    if host is None or normal is None or centro is None:
        return esquina, hacia
    try:
        caja = host.RangeBox
        alturas = []
        for x in (float(caja.MinPoint.X), float(caja.MaxPoint.X)):
            for y in (float(caja.MinPoint.Y), float(caja.MaxPoint.Y)):
                for z in (float(caja.MinPoint.Z), float(caja.MaxPoint.Z)):
                    alturas.append(_dot((x * 10.0, y * 10.0, z * 10.0), normal))
    except Exception:
        return esquina, hacia
    if not alturas:
        return esquina, hacia
    bajo, alto = min(alturas), max(alturas)
    altura = _dot(esquina, normal)
    if _dot(centro, normal) >= (bajo + alto) / 2.0:
        destino, sentido = alto, normal
    else:
        destino, sentido = bajo, _opuesto(normal)
    esquina = _suma_vec(esquina, _escala(normal, destino - altura))
    return esquina, sentido


def _hacia_pieza(frame, centro):
    normal = _vector(frame.get("normal")) or (0.0, 0.0, 1.0)
    origen = _vector(frame.get("origen"))
    punto = _vector(centro)
    if origen is None or punto is None:
        return normal
    if _dot(_resta(punto, origen), normal) < 0:
        return _opuesto(normal)
    return normal


def _mundo(frame, u, v):
    origen = frame["origen"]
    uu = frame["u"]
    vv = frame["v"]
    return (
        origen[0] + uu[0] * u + vv[0] * v,
        origen[1] + uu[1] * u + vv[1] * v,
        origen[2] + uu[2] * u + vv[2] * v,
    )


def _borde_mas_largo(puntos, normal):
    mejor = None
    largo = 0.0
    total = len(puntos)
    for indice in range(total):
        delta = _resta(puntos[(indice + 1) % total], puntos[indice])
        delta = _resta(delta, _escala(normal, _dot(delta, normal)))
        medida = _largo_vector(delta)
        if medida > largo:
            candidato = _norm(delta)
            if candidato is not None:
                mejor = candidato
                largo = medida
    return mejor


def _escala(vector, factor: float):
    return (vector[0] * factor, vector[1] * factor, vector[2] * factor)


def _opuesto(vector):
    return (-vector[0], -vector[1], -vector[2])


def _largo_vector(vector) -> float:
    return math.sqrt(_dot(vector, vector))


def _frame(muro: dict) -> dict:
    return {
        "normal": muro.get("normal"),
        "u": muro.get("u"),
        "v": muro.get("v"),
        "origen": muro.get("origen"),
    }


def _quien_se_ve(a: str, b: str) -> tuple[str, str]:
    """La esquina vertical se acota en el segmento 2 o 4. El 1 y el 3 no se la quedan.

    El cordón con la base sigue en su propio segmento.
    """
    cabezal = {"SEGM2", "SEGM4"}
    if a in cabezal and b not in cabezal:
        return a, b
    if b in cabezal and a not in cabezal:
        return b, a
    orden = {nombre: index for index, nombre in enumerate(_VISTA)}
    if orden.get(a, 9) <= orden.get(b, 9):
        return a, b
    return b, a


def _solape(puntos_a, puntos_b, direccion) -> float:
    da = [_dot(punto, direccion) for punto in puntos_a]
    db = [_dot(punto, direccion) for punto in puntos_b]
    if not da or not db:
        return 0.0
    bajo = max(min(da), min(db))
    alto = min(max(da), max(db))
    return max(0.0, alto - bajo)


def _cerca(puntos, muro: dict, holgura: float) -> bool:
    normal = _vector(muro.get("normal"))
    origen = _vector(muro.get("origen"))
    if normal is None or origen is None or not puntos:
        return False
    return min(abs(_dot(_resta(punto, origen), normal)) for punto in puntos) <= holgura


def _toca_caja(caja, muro: dict, holgura: float) -> bool:
    if not caja:
        return False
    return _cerca(_esquinas(caja), muro, holgura)


def _huella(puntos, muro: dict) -> tuple[float, float, float, float] | None:
    u = _vector(muro.get("u"))
    v = _vector(muro.get("v"))
    origen = _vector(muro.get("origen"))
    if u is None or v is None or origen is None:
        return None
    coords = []
    for punto in puntos:
        valor = _vector(punto)
        if valor is None:
            continue
        delta = _resta(valor, origen)
        coords.append((_dot(delta, u), _dot(delta, v)))
    if len(coords) < 2:
        return None
    us = [item[0] for item in coords]
    vs = [item[1] for item in coords]
    return (min(us), min(vs), max(us), max(vs))


def _huella_hermetica(muro: dict, otro: dict) -> tuple[float, float, float, float] | None:
    """La arista compartida, proyectada a la cara. La tapa queda arriba; la base, abajo."""
    frame = _frame(muro)
    tramo = _eje_compartido(frame, muro.get("outline") or [], _frame(otro), otro.get("outline") or [])
    if tramo is None:
        return _borde(muro.get("outline") or [])
    return _huella_de_tramo(frame, tramo[0], tramo[1]) or _borde(muro.get("outline") or [])


def _huella_de_tramo(frame, inicio, fin) -> tuple[float, float, float, float] | None:
    u = _vector(frame.get("u"))
    v = _vector(frame.get("v"))
    origen = _vector(frame.get("origen"))
    if u is None or v is None or origen is None:
        return None
    coords = []
    for punto in (inicio, fin):
        valor = _vector(punto)
        if valor is None:
            continue
        delta = _resta(valor, origen)
        coords.append((_dot(delta, u), _dot(delta, v)))
    if len(coords) < 2:
        return None
    us = [item[0] for item in coords]
    vs = [item[1] for item in coords]
    return (min(us), min(vs), max(us), max(vs))


def _borde(outline: list) -> tuple[float, float, float, float] | None:
    if len(outline) < 2:
        return None
    xs = [float(punto[0]) for punto in outline]
    ys = [float(punto[1]) for punto in outline]
    return (min(xs), min(ys), max(xs), min(ys))


def _tramo_en_plano(puntos, muro: dict) -> float:
    u = _vector(muro.get("u"))
    v = _vector(muro.get("v"))
    if u is None or v is None or len(puntos) < 2:
        return 0.0
    us = [_dot(punto, u) for punto in puntos]
    vs = [_dot(punto, v) for punto in puntos]
    return max(max(us) - min(us), max(vs) - min(vs))


def _ancla(centro, muro: dict) -> tuple[float, float]:
    outline = muro.get("outline") or []
    u = _vector(muro.get("u"))
    v = _vector(muro.get("v"))
    origen = _vector(muro.get("origen"))
    punto = _vector(centro)
    if u is None or v is None or origen is None or punto is None or len(outline) < 2:
        return (0.5, 0.5)
    x = _dot(_resta(punto, origen), u)
    y = _dot(_resta(punto, origen), v)
    xs = [item[0] for item in outline]
    ys = [item[1] for item in outline]
    ancho = max(max(xs) - min(xs), 1.0)
    alto = max(max(ys) - min(ys), 1.0)
    return (
        min(1.0, max(0.0, (x - min(xs)) / ancho)),
        min(1.0, max(0.0, (y - min(ys)) / alto)),
    )


def _esquinas(caja) -> list[tuple[float, float, float]]:
    if not caja or len(caja) < 2:
        return []
    a, b = caja[0], caja[1]
    return [(x, y, z) for x in (a[0], b[0]) for y in (a[1], b[1]) for z in (a[2], b[2])]


def _largo(mm: float) -> str:
    return f"{mm:.0f} mm"


def _vector(value):
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return None
    return (float(value[0]), float(value[1]), float(value[2]))


def _resta(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(value):
    largo = math.sqrt(_dot(value, value))
    if largo < 1e-9:
        return None
    return (value[0] / largo, value[1] / largo, value[2] / largo)
