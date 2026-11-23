"""Prueba de espesor de pintura.

Lee el ensamble abierto, dibuja un JPG por cara y lo deja en JPG\\ESPESOR_PINTURA.
La corrida real copia esos JPG a DOSSIER FILES\\JPGS\\Espesor pintura y los registra
en cotas_dossier. La muestra no escribe la base.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from pathlib import Path

_HW = re.compile(r"bolt|nut|washer|screw|rivet|hw[-_]|din\d|iso\d", re.IGNORECASE)

from acotacion import ensure_dir, local_jpg_dir
from espesor_geo import (
    _cross,
    _dot,
    _scale,
    _unit,
    claro_de,
    clasificar_montadas,
    contenida,
    entra_en_alzado,
    interior_de,
    internas,
    raiz_de,
    con_ocultas,
    lado_vista,
    plan_cara,
    tamano_bitmap,
)
from espesor_jpg import (
    CM_A_IN,
    a_contorno,
    asentar_puntos,
    dibujar_trazos,
    guardar,
    guardar_foto,
    guardar_vista,
    mascara_chapa,
)

ROOT = Path(__file__).resolve().parents[1]
PROGRESS_PATH = ROOT / "config" / "espesor_progress.json"
ORDEN = ("SEGM1", "SEGM2", "SEGM3", "SEGM4", "TOP", "BASE")
TITULO = {
    "SEGM1": "SEGMENT 1",
    "SEGM2": "SEGMENT 2",
    "SEGM3": "SEGMENT 3",
    "SEGM4": "SEGMENT 4",
    "TOP": "TOP COVER",
    "BASE": "BASE",
}
ESQUEMA_NOMBRE = {
    "thermox": "THERMOX",
    "zinc_macro": "ZINC Y MACRO",
    "poliuretano": "POLIURETANO",
    "shot_blast": "SHOT BLAST",
}
CARPETA_ESQUEMA = {
    "shot_blast": "shot blast",
}
_started = 0.0


def generar(payload: dict | None = None) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    solo = bool(payload.get("solo"))
    esquema = str(payload.get("esquema") or "todas").strip().lower()
    if solo and esquema not in ESQUEMA_NOMBRE:
        return _error(f"Esquema desconocido: {esquema}")
    esquemas = (esquema,) if solo else tuple(ESQUEMA_NOMBRE)
    otc = bool(payload.get("otc"))
    muestra = bool(payload.get("muestra"))
    try:
        if muestra:
            caras = _muestra()
            nombre = "MUESTRA"
            reset_progress(len(caras) * len(esquemas), "Dibujando la muestra…")
        else:
            reset_progress(0, "Leyendo la geometría del tanque…")
            caras, nombre = leer_ensamble()
        if not caras:
            return _error("No encontré segmentos, tapa ni base en el ensamble abierto.")
        raiz = _destino(payload, nombre, esquema if solo else "")
        if solo:
            result = _dibujar(caras, raiz, esquema, otc and esquema == "poliuretano", nombre, muestra)
        else:
            result = _dibujar_todas(caras, raiz, esquemas, otc, nombre, muestra)
        if result.get("ok") and not muestra:
            result = _registrar_bd(result, raiz, payload)
        return result
    except Exception as ex:
        return _error(str(ex))


def _registrar_bd(result: dict, raiz: Path, payload: dict) -> dict:
    """Publica los JPG del job y reescribe el avance. Si la base falla, los JPG locales quedan."""
    from cotas_dossier import alimentar_espesor
    from dossier_arbol import cargar_eleccion

    eleccion = cargar_eleccion()
    job = str(payload.get("job") or eleccion.get("job") or "").strip()
    try:
        bd = alimentar_espesor(str(raiz), job=job)
    except Exception as ex:
        bd = {"ok": False, "count": 0, "message": f"BD: {ex}"}
    texto = str(result.get("message") or "").replace(" Sin escritura en la base de datos.", "")
    result["bd"] = bool(bd.get("ok"))
    result["bd_count"] = int(bd.get("count") or 0)
    result["message"] = (texto + " " + str(bd.get("message") or "")).strip()
    write_progress(
        current=1,
        total=1,
        piece="Listo",
        photos=int(result.get("fotos") or 0),
        phase="listo",
        done=True,
        result=result,
        message=result["message"],
    )
    return result


def leer_ensamble() -> tuple[list[dict], str]:
    """Un alzado por lado. El contorno son las aristas de las caras, no la caja."""
    from inventor_session import _active_assembly, _inventor, _name
    from roles_inventor import _orientar_afuera, _piezas_hoja

    inv = _inventor()
    assembly = _active_assembly(inv)
    if assembly is None:
        raise RuntimeError("Abre un ensamble (.iam) en Inventor.")
    nombre = str(_name(assembly) or "ensamble")
    write_progress(current=0, total=6, piece="Leyendo las placas…", phase="malla")
    piezas = _piezas_hoja(assembly)
    planas = [pieza for pieza in piezas if pieza.get("plana") and pieza.get("normal") and pieza.get("occ") is not None]
    _orientar_afuera(planas)
    caras = []
    for codigo, normal in _direcciones(planas):
        write_progress(current=len(caras), total=6, piece=TITULO.get(codigo, codigo), phase="contorno")
        cara = _cara_por_aristas(planas, piezas, codigo, normal)
        if cara is not None:
            caras.append(cara)
    _ampliar_extremos(caras, piezas, planas)
    for cara in caras:
        cara["partes"] = _partes_en_plano(
            piezas,
            cara["normal"],
            float(cara["plano"]),
            cara["u"],
            cara["v"],
            float(cara["u0"]),
            float(cara["v0"]),
            float(cara["ancho"]),
            float(cara["alto"]),
        )
        cara["placa"] = _placa_principal(piezas, cara)
    _marcar_tapa(caras)
    _fotografiar(inv, assembly, caras, piezas)
    for cara in caras:
        cara["estorbos"] = _estorbos_dentro(piezas, cara)
        cara["estorbos_fuera"] = _estorbos_fuera(piezas, cara)
    return caras, nombre


def _proyeccion(pieza: dict, cara: dict) -> dict | None:
    caja = pieza.get("caja")
    if not caja:
        return None
    normal, u, v = cara["normal"], cara["u"], cara["v"]
    u0, v0 = float(cara["u0"]), float(cara["v0"])
    xs, ys, ds = [], [], []
    for esquina in _esquinas_de(caja):
        ds.append(float(_dot(esquina, normal)) - float(cara["plano"]))
        xs.append(float(_dot(esquina, u)) - u0)
        ys.append(float(_dot(esquina, v)) - v0)
    return {
        "nombre": str(pieza.get("nombre_ocurrencia") or ""),
        "ruta": str(pieza.get("ruta_ocurrencia") or ""),
        "x0": min(xs),
        "x1": max(xs),
        "y0": min(ys),
        "y1": max(ys),
        "d0": min(ds),
        "d1": max(ds),
    }


def _marcar_tapa(caras: list[dict]) -> None:
    """El top cover va atornillado, no soldado: por dentro sale solo y los demás lo ocultan.

    Solo aplica si la placa del TOP vive en su propio subensamble (62285-1247-A01).
    """
    top = next((cara for cara in caras if cara.get("codigo") == "TOP"), None)
    raiz = raiz_de((top or {}).get("placa", {}).get("ruta") if top and top.get("placa") else "")
    if not raiz:
        return
    otras = {raiz_de(cara["placa"].get("ruta")) for cara in caras if cara is not top and cara.get("placa")}
    if raiz in otras:
        return
    for cara in caras:
        if cara is top:
            cara["solo_raiz"] = raiz
        else:
            cara["sin_raiz"] = raiz
            if top.get("normal") is not None and top.get("plano") is not None:
                cara["piel_tapa"] = (top["normal"], float(top["plano"]))


def _del_lado(caja: dict, cara: dict) -> bool:
    raiz = raiz_de(caja.get("ruta"))
    if cara.get("solo_raiz"):
        return raiz == cara["solo_raiz"]
    if cara.get("sin_raiz"):
        return raiz != cara["sin_raiz"]
    return True


def _placa_principal(piezas: list[dict], cara: dict) -> dict | None:
    """La placa del segmento donde se montan los accesorios: la delgada más grande pegada al plano."""
    ancho, alto = float(cara["ancho"]), float(cara["alto"])
    mejor = None
    for pieza in piezas:
        caja = _proyeccion(pieza, cara)
        if caja is None or _HW.search(caja["nombre"]):
            continue
        if caja["d1"] - caja["d0"] > 40.0 or abs(caja["d1"]) > 10.0:
            continue
        x0, x1 = max(caja["x0"], 0.0), min(caja["x1"], ancho)
        y0, y1 = max(caja["y0"], 0.0), min(caja["y1"], alto)
        if x1 <= x0 or y1 <= y0:
            continue
        area = (x1 - x0) * (y1 - y0)
        if mejor is None or area > mejor[0]:
            mejor = (area, {**caja, "x0": x0, "x1": x1, "y0": y0, "y1": y1})
    if mejor is None or mejor[0] < 0.2 * ancho * alto:
        return None
    return mejor[1]


def _estorbos_dentro(piezas: list[dict], cara: dict) -> list[dict]:
    """Lo que se ve desde dentro sobre la placa principal: refuerzos, soportes, bridas."""
    placa = cara.get("placa")
    if not placa:
        return []
    claro = float(cara.get("claro") or 0.0)
    fondo = -(claro * 0.5) if claro else -120.0
    area_placa = (placa["x1"] - placa["x0"]) * (placa["y1"] - placa["y0"])
    estorbos = []
    for pieza in piezas:
        caja = _proyeccion(pieza, cara)
        if caja is None or _HW.search(caja["nombre"]):
            continue
        if caja["nombre"] == placa["nombre"] or not _del_lado(caja, cara):
            continue
        if caja["d0"] > -0.5 or caja["d1"] < fondo:
            continue
        if caja["x1"] < placa["x0"] or caja["x0"] > placa["x1"] or caja["y1"] < placa["y0"] or caja["y0"] > placa["y1"]:
            continue
        if (caja["x1"] - caja["x0"]) * (caja["y1"] - caja["y0"]) > 0.6 * area_placa:
            continue
        estorbos.append(caja)
    return estorbos


def _estorbos_fuera(piezas: list[dict], cara: dict) -> list[dict]:
    """Lo montado por fuera de la placa: boquillas, registros, orejas. Zinc se aparta de eso."""
    placa = cara.get("placa")
    if not placa:
        return []
    area_placa = (placa["x1"] - placa["x0"]) * (placa["y1"] - placa["y0"])
    estorbos = []
    for pieza in piezas:
        caja = _proyeccion(pieza, cara)
        if caja is None or _HW.search(caja["nombre"]) or caja["nombre"] == placa["nombre"]:
            continue
        if caja["d1"] < 3.0 or caja["d0"] < -8.0 or caja["d0"] > 50.0:
            continue
        if caja["x1"] < placa["x0"] or caja["x0"] > placa["x1"] or caja["y1"] < placa["y0"] or caja["y0"] > placa["y1"]:
            continue
        if (caja["x1"] - caja["x0"]) * (caja["y1"] - caja["y0"]) > 0.6 * area_placa:
            continue
        estorbos.append(caja)
    return estorbos


def _fotografiar(inv, assembly, caras: list[dict], piezas: list[dict]) -> None:
    """Dos alzados por cara: desde fuera (Zinc y Poliuretano) y desde dentro (Thermox)."""
    if not caras:
        return
    from vista_hlr import _apagar_sombras, _estado_vista, _restaurar_vista
    from weld_vista import _fondo_blanco, _restaurar_fondo, _soltar_seleccion, _ver

    try:
        view = inv.ActiveView
        display = inv.DisplayOptions
        cam = view.Camera
    except Exception:
        return
    state = _estado_vista(view, cam, display)
    fondo = _fondo_blanco(inv)
    guardadas: list[tuple] = []
    caido = False
    try:
        pantalla = bool(inv.ScreenUpdating)
    except Exception:
        pantalla = True
    try:
        silencioso = bool(inv.SilentOperation)
    except Exception:
        silencioso = False
    try:
        try:
            display.Show3DIndicator = False
        except Exception:
            pass
        _apagar_sombras(view)
        # La pantalla se queda quieta todo el recorrido. Encenderla en cada cara
        # obliga a Inventor a reconstruir la vista y fue lo que lo saturó.
        try:
            inv.SilentOperation = True
        except Exception:
            pass
        _pantalla(inv, False)
        try:
            view.DisplayMode = 8711
        except Exception:
            pass
        hojas = assembly.ComponentDefinition.Occurrences.AllLeafOccurrences
        for indice in range(1, int(hojas.Count) + 1):
            try:
                occ = hojas.Item(indice)
                if bool(occ.Suppressed):
                    continue
                guardadas.append((occ, bool(occ.Visible)))
                occ.Visible = False
            except Exception:
                continue
        for cara in caras:
            cara["interior"] = interior_de(cara, caras)
            cara["claro"] = claro_de(cara, caras)
        for cara in caras:
            titulo = TITULO.get(cara["codigo"], cara["codigo"])
            for lado, texto in (("fuera", "por fuera"), ("dentro", "por dentro")):
                mostradas: list = []
                padres: list = []
                try:
                    if lado == "dentro":
                        if cara.get("claro"):
                            cara["retroceso"] = float(cara["claro"]) * 0.5 + 2.0
                        else:
                            cara["retroceso"] = _retroceso_interno(piezas, cara.get("normal"), cara.get("plano"))
                    for pieza in _piezas_en_alzado(piezas, cara, lado):
                        occ = pieza.get("occ")
                        if occ is not None:
                            _ver(occ, mostradas, padres)
                    if not mostradas:
                        cara[f"foto_error_{lado}"] = "Sin piezas de ese lado."
                        continue
                    _soltar_seleccion(assembly)
                    write_progress(current=0, total=len(caras), piece=f"Foto {titulo} {texto}", phase="foto")
                    try:
                        foto, ventana, solido = _foto_alzado(
                            inv, view, cara, piezas, lado, mostradas, assembly
                        )
                    except Exception as ex:
                        if _inventor_caido(ex):
                            caido = True
                            raise RuntimeError(
                                f"Inventor se cerró en la foto {titulo} {texto}. "
                                "Vuelve a abrir el ensamble y no lo uses mientras se generan las fotos."
                            ) from ex
                        cara[f"foto_error_{lado}"] = str(ex)
                        continue
                    if foto is not None and ventana is not None:
                        cara[f"foto_{lado}"] = foto
                        cara[f"solido_{lado}"] = solido
                        cara[f"ventana_{lado}"] = ventana
                    if lado == "fuera" and not cara.get("placa") and solido is None and foto is not None:
                        cara[f"sin_mascara_{lado}"] = True
                finally:
                    if not caido:
                        for occ in mostradas + padres:
                            try:
                                occ.Visible = False
                            except Exception:
                                continue
    finally:
        if not caido:
            for occ, visible in reversed(guardadas):
                try:
                    if bool(occ.Visible) != visible:
                        occ.Visible = visible
                except Exception:
                    continue
            try:
                inv.SilentOperation = silencioso
            except Exception:
                pass
            _pantalla(inv, pantalla)
            _restaurar_fondo(inv, fondo)
            try:
                _restaurar_vista(inv, inv.ActiveView, inv.TransientGeometry, display, state)
            except Exception:
                try:
                    inv.ActiveView.Update()
                except Exception:
                    pass
            _soltar_seleccion(assembly)


def _piezas_en_alzado(piezas: list[dict], cara: dict, lado: str = "fuera") -> list[dict]:
    """Por fuera: la piel y lo montado afuera. Por dentro: la piel y lo que da al interior."""
    if lado == "dentro":
        return _piezas_internas(piezas, cara)
    normal = cara.get("normal")
    u = cara.get("u")
    v = cara.get("v")
    plano = cara.get("plano")
    if normal is None or u is None or v is None or plano is None:
        return []
    u0 = float(cara["u0"])
    v0 = float(cara["v0"])
    u1 = u0 + float(cara["ancho"])
    v1 = v0 + float(cara["alto"])
    elegidas = []
    for pieza in piezas:
        if pieza.get("occ") is None or not pieza.get("caja"):
            continue
        nombre = str(pieza.get("nombre_ocurrencia") or "")
        if _HW.search(nombre):
            continue
        xs: list[float] = []
        ys: list[float] = []
        profundidades: list[float] = []
        for esquina in _esquinas_de(pieza["caja"]):
            profundidades.append(float(_dot(esquina, normal)))
            xs.append(float(_dot(esquina, u)))
            ys.append(float(_dot(esquina, v)))
        if not profundidades:
            continue
        hasta = None
        if lado == "dentro" and cara.get("claro"):
            hasta = float(plano) - float(cara["claro"]) * 0.5
        elif lado == "dentro" and cara.get("retroceso"):
            hasta = float(plano) - float(cara["retroceso"]) + 12.0
        if not entra_en_alzado(
            min(profundidades),
            max(profundidades),
            float(plano),
            lado,
            float(cara.get("holgura") or 8.0),
            hasta,
        ):
            continue
        if max(xs) < u0 - 12 or min(xs) > u1 + 12 or max(ys) < v0 - 12 or min(ys) > v1 + 12:
            continue
        if lado == "dentro" and cara.get("interior") and not contenida(xs, ys, cara["interior"]):
            continue
        elegidas.append(pieza)
    return elegidas


def _piezas_internas(piezas: list[dict], cara: dict) -> list[dict]:
    """El TOP sale solo con su subensamble. Muros y base: sin top cover, sin muro contrario,
    solo lo pegado a la piel y lo soldado a eso."""
    if cara.get("normal") is None or cara.get("plano") is None:
        return []
    ancho, alto = float(cara["ancho"]), float(cara["alto"])
    candidatas: list[dict] = []
    cajas: list[dict] = []
    for pieza in piezas:
        if pieza.get("occ") is None:
            continue
        caja = _proyeccion(pieza, cara)
        if caja is None or _HW.search(caja["nombre"]) or not _del_lado(caja, cara):
            continue
        if caja["x1"] < -60 or caja["x0"] > ancho + 60 or caja["y1"] < -60 or caja["y0"] > alto + 60:
            continue
        if cara.get("piel_tapa"):
            normal_tapa, plano_tapa = cara["piel_tapa"]
            ts = [float(_dot(e, normal_tapa)) - plano_tapa for e in _esquinas_de(pieza["caja"])]
            caja["t0"], caja["t1"] = min(ts), max(ts)
        candidatas.append(pieza)
        cajas.append(caja)
    if cara.get("solo_raiz"):
        return candidatas
    return [candidatas[i] for i in internas(cajas, cara.get("claro"), ancho, alto)]


def _foto_alzado(inv, view, cara: dict, piezas: list[dict], lado: str, mostradas: list, assembly):
    from weld_vista import _ajustar_aspecto, _restaurar_material

    normal = cara["normal"]
    u = cara["u"]
    v = cara["v"]
    plano = float(cara["plano"])
    us: list[float] = []
    vs: list[float] = []
    margen = 0.04
    recorte = None
    if lado == "dentro":
        a, b, c, d = cara.get("interior") or (
            float(cara["u0"]),
            float(cara["u0"]) + float(cara["ancho"]),
            float(cara["v0"]),
            float(cara["v0"]) + float(cara["alto"]),
        )
        esquinas = [e for p in _piezas_internas(piezas, cara) for e in _esquinas_de(p.get("caja"))]
        if esquinas:
            xs = [float(_dot(e, u)) for e in esquinas]
            ys = [float(_dot(e, v)) for e in esquinas]
            if cara.get("solo_raiz"):
                a, b, c, d = min(xs), max(xs), min(ys), max(ys)
            else:
                # Lo montado por fuera de los muros laterales entra, con tope del 15 %.
                tope = 0.15 * max(b - a, d - c)
                a, b = max(min(xs), a - tope), min(max(xs), b + tope)
                c, d = max(min(ys), c - tope), min(max(ys), d + tope)
        holgura = max(4.0, 0.015 * max(b - a, d - c))
        recorte = (a - holgura, b + holgura, c - holgura, d + holgura)
        us = [recorte[0], recorte[1]]
        vs = [recorte[2], recorte[3]]
        margen = 0.0
    else:
        for pieza in _piezas_en_alzado(piezas, cara, lado):
            for esquina in _esquinas_de(pieza.get("caja")):
                us.append(float(_dot(esquina, u)))
                vs.append(float(_dot(esquina, v)))
    if not us:
        us = [float(cara["u0"]), float(cara["u0"]) + float(cara["ancho"])]
        vs = [float(cara["v0"]), float(cara["v0"]) + float(cara["alto"])]
    cu = (min(us) + max(us)) / 2.0
    cv = (min(vs) + max(vs)) / 2.0
    ancho = max(max(us) - min(us), 10.0) * (1.0 + margen)
    alto = max(max(vs) - min(vs), 10.0) * (1.0 + margen)
    try:
        aspecto = float(view.Width) / float(view.Height)
    except Exception:
        aspecto = 0.0
    ancho, alto, _su, _sv = _ajustar_aspecto(ancho, alto, aspecto)
    origen = (
        u[0] * cu + v[0] * cv + normal[0] * plano,
        u[1] * cu + v[1] * cv + normal[1] * plano,
        u[2] * cu + v[2] * cv + normal[2] * plano,
    )
    tg = inv.TransientGeometry
    cam = view.Camera
    cam.Perspective = False
    # Misma distancia por los dos lados. El ojo queda fuera del modelo;
    # en ortográfica la distancia no cambia el encuadre.
    distancia = max(ancho, alto, 10.0) * 2.5
    signo = -1.0 if lado == "dentro" else 1.0
    cam.Target = tg.CreatePoint(origen[0], origen[1], origen[2])
    cam.Eye = tg.CreatePoint(
        origen[0] + normal[0] * distancia * signo,
        origen[1] + normal[1] * distancia * signo,
        origen[2] + normal[2] * distancia * signo,
    )
    try:
        cam.UpVector = tg.CreateUnitVector(float(v[0]), float(v[1]), float(v[2]))
    except Exception:
        cam.UpVector = tg.CreateVector(float(v[0]), float(v[1]), float(v[2]))
    cam.SetExtents(ancho, alto)
    cam.ApplyWithoutTransition()
    blanco = inv.TransientObjects.CreateColor(255, 255, 255)
    if recorte is not None:
        px_w, px_h = tamano_bitmap(
            ancho, alto, recorte[1] - recorte[0], lado_max=1600, area_max=2_000_000
        )
    else:
        px_w, px_h = tamano_bitmap(ancho, alto)
    codigo = cara.get("codigo") or "cara"
    imagen = a_contorno(_bitmap(cam, px_w, px_h, blanco, f"autodxf_espesor_{codigo}_{lado}"))
    solido = None
    # La máscara gris solo hace falta si no hay placa medida. Con placa, pintar
    # el aspecto de cada pieza y tomar otra foto satura el COM y la tarjeta.
    if lado == "fuera" and not cara.get("placa"):
        previos = _pintar_mascara(inv, assembly, mostradas)
        try:
            try:
                view.DisplayMode = 8709
            except Exception:
                pass
            cam.ApplyWithoutTransition()
            cruda = _bitmap(cam, px_w, px_h, blanco, f"autodxf_espesor_{codigo}_{lado}_m")
            solido = mascara_chapa(cruda)
        finally:
            _restaurar_material(previos)
            try:
                view.DisplayMode = 8711
            except Exception:
                pass
    if recorte is not None:
        return _recortar_dentro(imagen, solido, recorte, cu, cv, ancho, alto)
    ventana = (cu - ancho / 2.0, cv - alto / 2.0, cu + ancho / 2.0, cv + alto / 2.0)
    return imagen, ventana, solido


def _recortar_dentro(imagen, solido, recorte, cu: float, cv: float, ancho: float, alto: float):
    """Deja solo el hueco del tanque. Desde dentro la izquierda de la foto es la u mayor.

    La ventana va en u negada para que x crezca a la derecha de la foto.
    """
    a, b, c, d = recorte
    w, h = imagen.size
    izquierda = cu + ancho / 2.0
    arriba = cv + alto / 2.0
    x0 = int(max(0, min(w - 1, round((izquierda - b) / ancho * w))))
    x1 = int(max(x0 + 1, min(w, round((izquierda - a) / ancho * w))))
    y0 = int(max(0, min(h - 1, round((arriba - d) / alto * h))))
    y1 = int(max(y0 + 1, min(h, round((arriba - c) / alto * h))))
    imagen = imagen.crop((x0, y0, x1, y1))
    if solido is not None:
        solido = solido[y0:y1, x0:x1].copy()
    u_alto = izquierda - x0 / w * ancho
    u_bajo = izquierda - x1 / w * ancho
    v_alto = arriba - y0 / h * alto
    v_bajo = arriba - y1 / h * alto
    return imagen, (-u_alto, v_bajo, -u_bajo, v_alto), solido


def _retroceso_interno(piezas: list[dict], normal, plano) -> float:
    """Centímetros desde la piel hacia el claro, sin cruzar el muro contrario."""
    if normal is None or plano is None:
        return 120.0
    dots = []
    for pieza in piezas:
        for esquina in _esquinas_de(pieza.get("caja")):
            dots.append(float(_dot(esquina, normal)))
    if len(dots) < 2:
        return 120.0
    claro = max(float(plano) - min(dots), 80.0)
    return min(max(60.0, claro * 0.28), claro * 0.5)


_RPC_CAIDO = (-2147023174, -2147023170, -2147417848, -2147220995)


def _inventor_caido(ex: Exception) -> bool:
    codigo = getattr(ex, "hresult", None)
    if codigo is None and getattr(ex, "args", None):
        codigo = ex.args[0]
    return codigo in _RPC_CAIDO or "RPC" in str(ex)


def _pantalla(inv, encendida: bool) -> None:
    try:
        inv.ScreenUpdating = encendida
    except Exception:
        pass


def _bitmap(cam, px_w: int, px_h: int, blanco, nombre: str):
    from PIL import Image

    tmp = Path(tempfile.gettempdir()) / f"{nombre}.bmp"
    if tmp.exists():
        try:
            tmp.unlink()
        except OSError:
            pass
    cam.SaveAsBitmap(str(tmp), px_w, px_h, blanco, blanco)
    with Image.open(tmp) as raw:
        copia = raw.convert("RGB").copy()
    try:
        tmp.unlink()
    except OSError:
        pass
    return copia


def _pintar_mascara(inv, assembly, occs) -> list:
    from inventor_session import _set_appearance
    from weld_solido import _apariencia

    pintura = _apariencia(inv, assembly, "EspesorChapa", (70, 70, 70))
    previos = []
    for occ in occs:
        try:
            fuente = int(occ.AppearanceSourceType)
        except Exception:
            fuente = None
        try:
            aspecto = occ.Appearance
        except Exception:
            aspecto = None
        previos.append((occ, fuente, aspecto))
        if pintura is not None:
            _set_appearance(occ, pintura)
    return previos


def _ampliar_extremos(caras: list[dict], piezas: list[dict], planas: list[dict]) -> None:
    """El lado corto no es solo la placa del centro: entra todo el extremo del tanque."""
    rumbos = dict(_direcciones(planas))
    for codigo in ("SEGM2", "SEGM4"):
        normal = rumbos.get(codigo)
        if normal is None:
            continue
        zona = _zona_extremo(piezas, normal)
        if zona is None:
            continue
        actual = next((cara for cara in caras if cara.get("codigo") == codigo), None)
        if actual is None:
            zona["codigo"] = codigo
            zona["clase"] = "muro"
            zona["partes"] = []
            zona["trazos"] = []
            caras.append(zona)
            continue
        if zona["alto"] <= float(actual["alto"]) * 1.2 and zona["ancho"] <= float(actual["ancho"]) * 1.2:
            continue
        actual.update(
            ancho=zona["ancho"],
            alto=zona["alto"],
            u0=zona["u0"],
            v0=zona["v0"],
            u=zona["u"],
            v=zona["v"],
            normal=zona["normal"],
            plano=zona["plano"],
            holgura=zona["holgura"],
            trazos=[],
        )


def _zona_extremo(piezas: list[dict], normal) -> dict | None:
    u, v = _ejes_vista(normal)
    filas = []
    for pieza in piezas:
        if pieza.get("caja") is None:
            continue
        nombre = str(pieza.get("nombre_ocurrencia") or "")
        if _HW.search(nombre):
            continue
        xs: list[float] = []
        ys: list[float] = []
        profundidades: list[float] = []
        for esquina in _esquinas_de(pieza["caja"]):
            profundidades.append(float(_dot(esquina, normal)))
            xs.append(float(_dot(esquina, u)))
            ys.append(float(_dot(esquina, v)))
        if not profundidades:
            continue
        area = (max(xs) - min(xs)) * (max(ys) - min(ys))
        filas.append((max(profundidades), max(profundidades) - min(profundidades), xs, ys, area))
    delgadas = [item for item in filas if item[1] <= 80.0]
    if not delgadas:
        return None
    # La piel del extremo es la placa que tapa el hueco, no lo más lejano de afuera (boquillas, orejas, válvulas).
    tope = max(item[4] for item in delgadas)
    grandes = [item for item in delgadas if item[4] >= tope * 0.5]
    piel = max(item[0] for item in grandes)
    us: list[float] = []
    vs: list[float] = []
    for afuera, _espesor, xs, ys, _area in grandes:
        if afuera < piel - 20.0:
            continue
        us.extend(xs)
        vs.extend(ys)
    if len(us) < 4:
        return None
    u0, u1, v0, v1 = min(us), max(us), min(vs), max(vs)
    ancho, alto = u1 - u0, v1 - v0
    if ancho < 20 or alto < 20:
        return None
    return {
        "ancho": ancho,
        "alto": alto,
        "u0": u0,
        "v0": v0,
        "u": u,
        "v": v,
        "normal": tuple(normal),
        "plano": piel,
        "holgura": 45.0,
    }


def _direcciones(planas: list[dict]) -> list[tuple[str, tuple[float, float, float]]]:
    vertical = []
    for placa in planas:
        normal = _unit(placa.get("normal"))
        if normal is not None and abs(normal[1]) < 0.65:
            vertical.append((placa, normal))
    if vertical:
        frente = max(vertical, key=lambda item: float(item[0].get("area") or 0))[1]
    else:
        frente = (0.0, 0.0, 1.0)
    izquierda = _unit(_cross(frente, (0.0, 1.0, 0.0))) or (1.0, 0.0, 0.0)
    # En planta el segmento 1 es el muro largo opuesto al de la placa mayor (62285: P14 es el 1, P12 el 3).
    return [
        ("SEGM1", _scale(frente, -1.0)),
        ("SEGM3", frente),
        ("SEGM2", izquierda),
        ("SEGM4", _scale(izquierda, -1.0)),
        ("TOP", (0.0, 1.0, 0.0)),
        ("BASE", (0.0, -1.0, 0.0)),
    ]


def _cara_por_aristas(planas: list[dict], piezas: list[dict], codigo: str, normal) -> dict | None:
    """El JPG es el contorno de las aristas de Inventor, no la caja ni la malla."""
    placas = _placas_del_plano(planas, normal, codigo)
    if not placas:
        return None
    u, v = _ejes_vista(normal)
    crudos: list[list[tuple[float, float, float]]] = []
    for placa in placas:
        crudos.extend(_aristas_hacia(placa["occ"], normal, placa.get("caja")))
    if len(crudos) < 3:
        return None
    us = [float(_dot(p, u)) for trazo in crudos for p in trazo]
    vs = [float(_dot(p, v)) for trazo in crudos for p in trazo]
    if not us:
        return None
    u0, u1, v0, v1 = min(us), max(us), min(vs), max(vs)
    ancho, alto = u1 - u0, v1 - v0
    if ancho < 5 or alto < 5:
        return None
    trazos = [[(float(_dot(p, u)) - u0, float(_dot(p, v)) - v0) for p in trazo] for trazo in crudos]
    plano = sum(float(_dot(p, normal)) for trazo in crudos for p in trazo) / max(len(us), 1)
    partes = _partes_en_plano(piezas, normal, plano, u, v, u0, v0, ancho, alto)
    clase = "muro" if codigo.startswith("SEGM") else ("top" if codigo == "TOP" else "base")
    return {
        "codigo": codigo,
        "clase": clase,
        "ancho": ancho,
        "alto": alto,
        "partes": partes,
        "trazos": trazos,
        "normal": tuple(normal),
        "u": u,
        "v": v,
        "u0": u0,
        "v0": v0,
        "plano": plano,
    }


def _placas_del_plano(planas: list[dict], normal, codigo: str) -> list[dict]:
    """La piel del lado. Una placa que mira igual pero está en otro plano no entra."""
    candidatas = []
    for placa in planas:
        n = _unit(placa.get("normal"))
        centro = placa.get("centro")
        if n is None or centro is None or placa.get("occ") is None:
            continue
        if float(_dot(n, normal)) <= 0.82:
            continue
        candidatas.append((float(_dot(centro, normal)), float(placa.get("area") or 0.0), placa))
    if not candidatas:
        return []
    candidatas.sort(key=lambda item: item[0])
    grupos: list[list] = [[candidatas[0]]]
    for item in candidatas[1:]:
        if item[0] - grupos[-1][-1][0] <= 20.0:
            grupos[-1].append(item)
        else:
            grupos.append([item])
    if codigo == "TOP":
        elegido = grupos[-1]
    elif codigo == "BASE":
        elegido = grupos[0]
    else:
        elegido = max(grupos, key=lambda grupo: sum(item[1] for item in grupo))
    return [item[2] for item in elegido]


def _aristas_hacia(occ, normal, caja) -> list[list[tuple[float, float, float]]]:
    plano = 5890
    candidatas = []
    try:
        bodies = occ.SurfaceBodies
        n_body = int(bodies.Count)
    except Exception:
        return []
    for bi in range(1, n_body + 1):
        try:
            faces = bodies.Item(bi).Faces
            n_face = int(faces.Count)
        except Exception:
            continue
        for fi in range(1, n_face + 1):
            try:
                face = faces.Item(fi)
                if int(face.SurfaceType) != plano:
                    continue
                geom = face.Geometry.Normal
                n = _unit((float(geom.X), float(geom.Y), float(geom.Z)))
                area = float(face.Evaluator.Area)
            except Exception:
                continue
            if n is None or abs(float(_dot(n, normal))) < 0.82 or area < 20.0:
                continue
            candidatas.append((area, face))
    if not candidatas:
        return []
    tope = max(area for area, _face in candidatas)
    trazos = []
    for area, face in candidatas:
        if area < tope * 0.2:
            continue
        try:
            loops = face.EdgeLoops
            n_loop = int(loops.Count)
        except Exception:
            continue
        for li in range(1, n_loop + 1):
            try:
                edges = loops.Item(li).Edges
                n_edge = int(edges.Count)
            except Exception:
                continue
            for ei in range(1, n_edge + 1):
                try:
                    muestra = _muestra_arista(edges.Item(ei))
                except Exception:
                    continue
                puntos = [_en_caja(occ, punto, caja) for punto in muestra]
                if len(puntos) >= 2:
                    trazos.append(puntos)
    return trazos


def _en_caja(occ, punto, caja):
    """La cara del proxy ya está en el ensamble. Si el punto cae fuera de su caja, se transforma."""
    if _cerca_de_caja(punto, caja, 8.0):
        return punto
    try:
        from mesh_view import _mx_point

        movido = _mx_point(occ.Transformation, punto)
    except Exception:
        return punto
    if caja is None or _cerca_de_caja(movido, caja, 40.0):
        return movido
    return punto


def _cerca_de_caja(punto, caja, margen: float) -> bool:
    if not caja:
        return False
    (x0, y0, z0), (x1, y1, z1) = caja
    x, y, z = punto
    return (min(x0, x1) - margen) <= x <= (max(x0, x1) + margen) and (min(y0, y1) - margen) <= y <= (max(y0, y1) + margen) and (min(z0, z1) - margen) <= z <= (max(z0, z1) + margen)


def _muestra_arista(edge, pasos: int = 24) -> list[tuple[float, float, float]]:
    pts: list[tuple[float, float, float]] = []
    try:
        ev = edge.Evaluator
        ext = ev.GetParamExtents()
        lo, hi = float(ext[0]), float(ext[1])
        for i in range(pasos + 1):
            t = lo + (hi - lo) * i / pasos
            try:
                pt = ev.GetPointAtParam(t)
                if isinstance(pt, (tuple, list)):
                    pts.append((float(pt[0]), float(pt[1]), float(pt[2])))
                else:
                    pts.append((float(pt.X), float(pt.Y), float(pt.Z)))
            except Exception:
                coords = [0.0, 0.0, 0.0]
                ev.GetPointAtParam(t, coords)
                pts.append((float(coords[0]), float(coords[1]), float(coords[2])))
    except Exception:
        pts = []
    if len(pts) < 2:
        for nombre in ("StartVertex", "StopVertex"):
            try:
                p = getattr(edge, nombre).Point
                pts.append((float(p.X), float(p.Y), float(p.Z)))
            except Exception:
                pass
    return pts


def _partes_en_plano(piezas, normal, plano, u, v, u0, v0, ancho, alto) -> list[dict]:
    """Lo montado en la cara, con su profundidad respecto a la piel. Un subensamble compacto cuenta también entero."""
    partes = []
    grupos: dict[str, list[dict]] = {}
    for pieza in piezas:
        caja = pieza.get("caja")
        if not caja:
            continue
        nombre = str(pieza.get("nombre_ocurrencia") or "")
        if _HW.search(nombre):
            continue
        xs: list[float] = []
        ys: list[float] = []
        ds: list[float] = []
        cerca = False
        for esquina in _esquinas_de(caja):
            profundidad = float(_dot(esquina, normal)) - plano
            if abs(profundidad) <= 25.0:
                cerca = True
            ds.append(profundidad)
            xs.append(float(_dot(esquina, u)) - u0)
            ys.append(float(_dot(esquina, v)) - v0)
        if not cerca or not xs:
            continue
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        if x1 < 0 or y1 < 0 or x0 > ancho or y0 > alto:
            continue
        if (x1 - x0) > 0.9 * ancho and (y1 - y0) > 0.9 * alto:
            continue
        parte = {"nombre": nombre, "x0": x0, "x1": x1, "y0": y0, "y1": y1, "d0": min(ds), "d1": max(ds)}
        partes.append(parte)
        ruta = str(pieza.get("ruta_ocurrencia") or "")
        if "/" in ruta:
            grupos.setdefault(ruta.rsplit("/", 1)[0], []).append(parte)
    for ruta, hijos in grupos.items():
        if len(hijos) < 2:
            continue
        unidad = {
            "nombre": ruta.rsplit("/", 1)[-1],
            "x0": min(h["x0"] for h in hijos),
            "x1": max(h["x1"] for h in hijos),
            "y0": min(h["y0"] for h in hijos),
            "y1": max(h["y1"] for h in hijos),
            "d0": min(h["d0"] for h in hijos),
            "d1": max(h["d1"] for h in hijos),
            "grupo": True,
        }
        if max(unidad["x1"] - unidad["x0"], unidad["y1"] - unidad["y0"], unidad["d1"] - unidad["d0"]) <= 80.0:
            partes.append(unidad)
    clasificar_montadas(partes, ancho, alto)
    return partes


def _ejes_vista(normal) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    semilla = (0.0, 0.0, 1.0) if abs(float(normal[1])) > 0.9 else (0.0, 1.0, 0.0)
    u = _unit(_cross(semilla, normal))
    if u is None:
        u = (1.0, 0.0, 0.0)
    v = _unit(_cross(normal, u)) or (0.0, 1.0, 0.0)
    return u, v


def _id_pieza(pieza: dict) -> str:
    return str(pieza.get("ruta_ocurrencia") or pieza.get("nombre_ocurrencia") or "")


def _union_caja(placas: list[dict]):
    cajas = [placa["caja"] for placa in placas if placa.get("caja")]
    mn = tuple(min(caja[0][eje] for caja in cajas) for eje in range(3))
    mx = tuple(max(caja[1][eje] for caja in cajas) for eje in range(3))
    return (mn, mx)


def _proyectar(miembro: dict, marco: dict) -> dict | None:
    from roles_muros import _dot, _sub

    xs: list[float] = []
    ys: list[float] = []
    for esquina in _esquinas_de(miembro.get("caja")):
        rel = _sub(esquina, marco["origen"])
        xs.append(float(_dot(rel, marco["u"])) - float(marco["umin"]))
        ys.append(float(_dot(rel, marco["v"])) - float(marco["vmin"]))
    if not xs:
        return None
    return {
        "nombre": str(miembro.get("nombre_ocurrencia") or ""),
        "x0": min(xs),
        "x1": max(xs),
        "y0": min(ys),
        "y1": max(ys),
    }


def _esquinas_de(caja) -> list[tuple[float, float, float]]:
    if not caja:
        return []
    (x0, y0, z0), (x1, y1, z1) = caja
    return [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]


def reset_progress(total: int = 0, piece: str = "Preparando…") -> None:
    global _started
    _started = time.time()
    write_progress(current=0, total=max(0, int(total)), piece=piece, phase="inicio", done=False)


def write_progress(
    *,
    current: int,
    total: int,
    piece: str,
    photos: int = 0,
    phase: str = "caras",
    done: bool = False,
    result: dict | None = None,
    message: str = "",
) -> None:
    cur = max(0, int(current))
    tot = max(0, int(total))
    payload = {
        "running": not done,
        "done": done,
        "current": cur,
        "total": tot,
        "piece": str(piece or ""),
        "photos": int(photos),
        "phase": phase,
        "percent": 100 if done else (int(100 * cur / tot) if tot else 0),
        "message": message,
        "result": result,
    }
    PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False)
    tmp = PROGRESS_PATH.with_name(f"espesor_progress.{os.getpid()}.tmp")
    try:
        tmp.write_text(data, encoding="utf-8")
        os.replace(str(tmp), str(PROGRESS_PATH))
    except OSError:
        try:
            PROGRESS_PATH.write_text(data, encoding="utf-8")
        except OSError:
            pass


def read_progress() -> dict:
    if not PROGRESS_PATH.is_file():
        return {"running": False, "done": False, "current": 0, "total": 0, "piece": "", "percent": 0, "message": "", "result": None}
    try:
        data = json.loads(PROGRESS_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {"running": False, "done": False, "message": "", "result": None}
    return data if isinstance(data, dict) else {}


def _dibujar_todas(caras, raiz: Path, esquemas, otc: bool, nombre: str, muestra: bool) -> dict:
    fotos: list[str] = []
    avisos: list[str] = []
    puntos = 0
    por_esquema: list[str] = []
    total = len(caras) * len(esquemas)
    hecho = 0
    for esquema in esquemas:
        parcial = _dibujar(
            caras,
            raiz / CARPETA_ESQUEMA.get(esquema, esquema),
            esquema,
            otc and esquema == "poliuretano",
            nombre,
            muestra,
            paso=hecho,
            total_pasos=total,
            cerrar=False,
        )
        hecho += len(caras)
        if not parcial.get("ok"):
            return parcial
        puntos += int(parcial.get("count") or 0)
        fotos.extend(parcial.get("files") or [])
        for aviso in parcial.get("avisos") or []:
            if aviso not in avisos:
                avisos.append(aviso)
        por_esquema.append(f"{ESQUEMA_NOMBRE[esquema]} {parcial.get('count') or 0}")
    mensaje = (
        f"{', '.join(por_esquema)}. {puntos} puntos en {len(fotos)} JPG. "
        f"{raiz}. Sin escritura en la base de datos."
    )
    result = {
        "ok": True,
        "bd": False,
        "folder": str(raiz),
        "count": puntos,
        "fotos": len(fotos),
        "files": fotos,
        "avisos": avisos,
        "message": mensaje,
    }
    write_progress(
        current=total,
        total=total,
        piece="Listo",
        photos=len(fotos),
        phase="listo",
        done=True,
        result=result,
        message=mensaje,
    )
    return result


def _dibujar(
    caras,
    carpeta: Path,
    esquema: str,
    otc: bool,
    nombre: str,
    muestra: bool,
    paso: int = 0,
    total_pasos: int | None = None,
    cerrar: bool = True,
) -> dict:
    ensure_dir(carpeta)
    fotos = []
    detalle = []
    avisos = []
    total_puntos = 0
    total = total_pasos or len(caras)
    write_progress(current=paso, total=total, piece=nombre, phase="caras")
    presentes = {cara["codigo"] for cara in caras}
    if not muestra:
        for codigo in ORDEN:
            if codigo not in presentes:
                avisos.append(f"Sin placa de {TITULO[codigo]}.")
    for indice, cara in enumerate(caras, start=1):
        titulo = TITULO.get(cara["codigo"], cara["codigo"])
        write_progress(current=paso + indice - 1, total=total, piece=f"{ESQUEMA_NOMBRE[esquema]} · {titulo}", photos=len(fotos), phase="caras")
        lado = lado_vista(esquema)
        foto = cara.get(f"foto_{lado}")
        ventana = cara.get(f"ventana_{lado}")
        espejo = lado == "dentro" and foto is not None and ventana is not None
        partes = cara.get("partes")
        en_placa = esquema in ("thermox", "zinc_macro")
        placa = cara.get("placa") if en_placa else None
        estorbos = cara.get("estorbos" if lado == "dentro" else "estorbos_fuera") if placa else None
        radio = 30 if esquema == "thermox" else 20
        if espejo:
            ancho_cara = float(cara["ancho"])

            def reflejar(caja: dict) -> dict:
                return {**caja, "x0": ancho_cara - caja["x1"], "x1": ancho_cara - caja["x0"]}

            partes = [reflejar(parte) for parte in partes or []]
            placa = reflejar(placa) if placa else None
            estorbos = [reflejar(caja) for caja in estorbos or []]
        puntos, notas = plan_cara(
            esquema, cara["clase"], cara["ancho"], cara["alto"], partes, placa=placa, estorbos=estorbos
        )
        for nota in notas:
            texto = nota if nota.startswith("Tapa") else f"{titulo}: {nota}"
            if texto not in avisos:
                avisos.append(texto)
        if foto is None or ventana is None:
            if cara.get(f"foto_error_{lado}"):
                avisos.append(
                    f"{titulo}: no pude tomar el alzado "
                    f"{'interno' if lado == 'dentro' else 'externo'} ({cara[f'foto_error_{lado}']})."
                )
                continue
        else:
            if espejo:
                origen_u = -(float(cara.get("u0") or 0.0) + float(cara["ancho"]))
            else:
                origen_u = float(cara.get("u0") or 0.0)
            origen_v = float(cara.get("v0") or 0.0)
            solido = cara.get(f"solido_{lado}")
            if solido is not None and not placa:
                asentar_puntos(puntos, solido, ventana, origen_u, origen_v, cara=(cara["ancho"], cara["alto"]))
            elif cara.get(f"sin_mascara_{lado}"):
                texto = f"{titulo}: no separé la chapa del hueco."
                if texto not in avisos:
                    avisos.append(texto)
        base = titulo.replace(" ", "_")
        hojas = [(carpeta / f"{base}.jpg", f"{titulo}  ·  {ESQUEMA_NOMBRE[esquema]}", puntos, False)]
        if con_ocultas(esquema) and cara["clase"] == "muro":
            rojos = [punto for punto in puntos if punto["color"] != "azul"]
            azules = [punto for punto in puntos if punto["color"] == "azul"]
            hojas = [(carpeta / f"{base}.jpg", f"{titulo}  ·  {ESQUEMA_NOMBRE[esquema]}", rojos, False)]
            if azules:
                hojas.append(
                    (
                        carpeta / f"{base}_PARTES_OCULTAS.jpg",
                        f"{titulo}  ·  {ESQUEMA_NOMBRE[esquema]}  ·  PARTES OCULTAS",
                        azules,
                        True,
                    )
                )
            else:
                avisos.append(f"{titulo}: sin partes ocultas; no hay hoja de partes ocultas.")
        for archivo, titulo_jpg, puntos_hoja, oculta in hojas:
            subtitulo = _subtitulo(esquema, otc, len(puntos_hoja), cara.get("codigo") or "", oculta)
            if foto is not None and ventana is not None:

                def px(x: float, y: float, _ventana=ventana, _u=origen_u, _v=origen_v, _foto=foto) -> tuple[float, float]:
                    izquierda, abajo, derecha, arriba = _ventana
                    span_x = derecha - izquierda or 1.0
                    span_y = arriba - abajo or 1.0
                    return (
                        (float(x) + _u - izquierda) / span_x * _foto.width,
                        (arriba - (float(y) + _v)) / span_y * _foto.height,
                    )

                guardar_foto(
                    archivo,
                    foto,
                    px,
                    titulo=titulo_jpg,
                    subtitulo=subtitulo,
                    ancho=cara["ancho"],
                    alto=cara["alto"],
                    puntos=puntos_hoja,
                    pie="Cara interna del ensamble" if lado == "dentro" else "Alzado del ensamble",
                    radio=radio,
                )
            elif cara.get("trazos") and not cara.get("holgura"):
                dibujar_trazos(
                    archivo,
                    cara["trazos"],
                    titulo=titulo_jpg,
                    subtitulo=subtitulo,
                    ancho=cara["ancho"],
                    alto=cara["alto"],
                    puntos=puntos_hoja,
                    radio=radio,
                )
            elif cara.get("vista"):
                vista = cara["vista"]
                guardar_vista(
                    archivo,
                    vista[0],
                    vista[1],
                    titulo=titulo_jpg,
                    subtitulo=subtitulo,
                    ancho=cara["ancho"],
                    alto=cara["alto"],
                    puntos=puntos_hoja,
                    radio=radio,
                )
            else:
                guardar(
                    archivo,
                    titulo=titulo_jpg,
                    subtitulo=subtitulo,
                    ancho=cara["ancho"],
                    alto=cara["alto"],
                    puntos=puntos_hoja,
                    partes=cara.get("partes") if oculta else None,
                    radio=radio,
                )
            fotos.append(str(archivo))
        total_puntos += len(puntos)
        detalle.append(
            {
                "codigo": cara["codigo"],
                "titulo": titulo,
                "ancho_in": round(cara["ancho"] * CM_A_IN, 2),
                "alto_in": round(cara["alto"] * CM_A_IN, 2),
                "puntos": [_publico(punto) for punto in puntos],
            }
        )
    escritos = {Path(ruta).name for ruta in fotos}
    for viejo in carpeta.glob("*.jpg"):
        if viejo.name not in escritos:
            try:
                viejo.unlink()
            except OSError:
                pass
    zinc = esquema == "zinc_macro" or otc
    manifiesto = {
        "bd": False,
        "esquema": esquema,
        "otc": otc,
        "zinc": zinc,
        "ensamble": nombre,
        "muestra": muestra,
        "puntos": total_puntos,
        "fotos": fotos,
        "avisos": avisos,
        "caras": detalle,
    }
    (carpeta / "manifiesto.json").write_text(
        json.dumps(manifiesto, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    nota_avisos = f" Avisos: {len(avisos)}." if avisos else ""
    mensaje = (
        f"{ESQUEMA_NOMBRE[esquema]}: {total_puntos} puntos en {len(fotos)} JPG. "
        f"{carpeta}. Sin escritura en la base de datos.{nota_avisos}"
    )
    result = {
        "ok": True,
        "bd": False,
        "folder": str(carpeta),
        "count": total_puntos,
        "fotos": len(fotos),
        "files": fotos,
        "avisos": avisos,
        "message": mensaje,
    }
    if cerrar:
        write_progress(
            current=total,
            total=total,
            piece="Listo",
            photos=len(fotos),
            phase="listo",
            done=True,
            result=result,
            message=mensaje,
        )
    return result


def _publico(punto: dict) -> dict:
    return {
        "numero": punto["numero"],
        "color": punto["color"],
        "grupo": punto["grupo"],
        "banda": punto["banda"],
        "columna": punto["columna"],
        "x_in": round(float(punto["x"]) * CM_A_IN, 2),
        "y_in": round(float(punto["y"]) * CM_A_IN, 2),
        "pieza": punto.get("pieza") or "",
        "aviso": punto.get("aviso") or "",
    }


def _subtitulo(esquema: str, otc: bool, cantidad: int, codigo: str = "", oculta: bool = False) -> str:
    extra = ""
    if esquema == "poliuretano":
        extra = "  ·  con Zinc (OTC)" if otc else "  ·  sin Zinc"
    if oculta:
        return f"{cantidad} puntos  ·  debajo de Jacking Pad, brace, cartabón y válvula{extra}"
    if lado_vista(esquema) == "dentro":
        return f"{cantidad} puntos  ·  cara interna, alzado desde dentro{extra}"
    return f"{cantidad} puntos  ·  cara externa, alzado desde fuera{extra}"


def _destino(payload: dict, nombre: str, esquema: str) -> Path:
    pedido = str(payload.get("carpeta") or "").strip()
    if pedido:
        return Path(pedido)
    raiz, _nota = local_jpg_dir("")
    slug = re.sub(r"[^\w.\-]+", "_", Path(nombre).stem).strip("_")[:80] or "ensamble"
    return raiz / "ESPESOR_PINTURA" / slug / esquema


def _muestra() -> list[dict]:
    """Cuatro segmentos de 160×90 in y tapa/base de 160×70 in, en cm."""
    ancho = 160 * 2.54
    alto = 90 * 2.54
    tapa = 70 * 2.54

    def partes(w: float, h: float) -> list[dict]:
        return [
            {"nombre": "Brace medio", "x0": 0.08 * w, "x1": 0.92 * w, "y0": 0.55 * h, "y1": 0.61 * h},
            {"nombre": "Brace inferior", "x0": 0.08 * w, "x1": 0.92 * w, "y0": 0.20 * h, "y1": 0.26 * h},
            {"nombre": "Solera Jacking Pad", "x0": 0.08 * w, "x1": 0.22 * w, "y0": 0.62 * h, "y1": 0.74 * h},
            {"nombre": "Cartabon esquina", "x0": 0.40 * w, "x1": 0.55 * w, "y0": 0.05 * h, "y1": 0.14 * h},
            {"nombre": "Valvula alivio", "x0": 0.72 * w, "x1": 0.86 * w, "y0": 0.30 * h, "y1": 0.42 * h},
        ]

    caras = []
    for numero in range(1, 5):
        caras.append(
            {
                "codigo": f"SEGM{numero}",
                "clase": "muro",
                "ancho": ancho,
                "alto": alto,
                "partes": partes(ancho, alto),
            }
        )
    for codigo, clase in (("TOP", "top"), ("BASE", "base")):
        caras.append({"codigo": codigo, "clase": clase, "ancho": ancho, "alto": tapa, "partes": []})
    return caras


def _error(message: str) -> dict:
    result = {"ok": False, "bd": False, "count": 0, "message": message, "folder": "", "files": []}
    write_progress(
        current=1,
        total=1,
        piece="Error",
        phase="listo",
        done=True,
        result=result,
        message=message,
    )
    return result
