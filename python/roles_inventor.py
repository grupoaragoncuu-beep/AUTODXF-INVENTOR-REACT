"""Host Inventor del selector L2: muros por instancia.

El clic del ingeniero manda: cada ocurrencia queda en la cara que eligió y así se
guarda (por ensamble y por ruta de ocurrencia). Clic en una placa de muro suma la
placa y lo que está montado en ella. Proponer muros solo llena lo que no se eligió.
"""

from __future__ import annotations

import json
from pathlib import Path

from roles_muros import (
    CARA_DE_ROL,
    _cross,
    _dot,
    _norm,
    _scale,
    _sub,
    bags_ensamble,
    _instancia_id,
    clasificar_placas,
    es_placa_muro,
    marco_cara,
    montadas_en_cara,
    registrar_foto_ensamble,
    token_de_miembro,
)

ARRIBA = (0.0, 1.0, 0.0)
TIPO_IPT = 12290
ORDEN_CARAS = ("TOP", "SEGM1", "SEGM2", "SEGM3", "SEGM4", "BASE")
SESSION_PATH = Path(__file__).resolve().parents[1] / "config" / "roles_sesion.json"
# Una pieza cuenta como placa de muro si su cara plana mayor es al menos esta fracción de la mayor del tanque.
FRACCION_PLACA = 0.25
COLORES_CARA = {
    "SEGM1": "#7C3AED",
    "SEGM2": "#2563EB",
    "SEGM3": "#06B6D4",
    "SEGM4": "#EA580C",
    "TOP": "#EAB308",
    "BASE": "#F97316",
}
TOKEN_A_CARA = {
    "s1": "SEGM1",
    "s2": "SEGM2",
    "s3": "SEGM3",
    "s4": "SEGM4",
    "seg_1": "SEGM1",
    "seg_2": "SEGM2",
    "seg_3": "SEGM3",
    "seg_4": "SEGM4",
    "segmento_1": "SEGM1",
    "segmento_2": "SEGM2",
    "segmento_3": "SEGM3",
    "segmento_4": "SEGM4",
    "base": "BASE",
    "tank_lid": "TOP",
    "tank_base": "BASE",
    "top_cover": "TOP",
    "tapa": "TOP",
}

_LAST_BAGS: dict[str, list[dict]] = {}


def last_bags() -> dict[str, list[dict]]:
    return _LAST_BAGS


def mapa_desde_bolsas(bolsas: dict[str, list[dict]] | None = None) -> dict[str, str]:
    out: dict[str, str] = {}
    for cara, miembros in (bolsas or _LAST_BAGS).items():
        for miembro in miembros or []:
            path = str(miembro.get("ruta_archivo") or "").replace("\\", "/").lower()
            if path:
                out[path] = cara
    return out


def proponer_muros(assembly, anclas_por_cara: dict | None = None) -> dict[str, list[dict]]:
    """Bolsas SEGM1…/TOP/BASE: una placa ancla por cara (nombre o clic previo; lo que falte,
    por geometría) y, en cada una, lo que está montado en ella por contacto real. Lo elegido a
    mano (sugerido=False) en las bolsas actuales se conserva tal cual."""
    global _LAST_BAGS
    manual = {c: [m for m in ms if not m.get("sugerido")] for c, ms in (_LAST_BAGS or {}).items()}
    piezas = _piezas_hoja(assembly)
    if not piezas:
        return dict(_LAST_BAGS)
    anclas_por_cara = dict(anclas_por_cara or {})
    for cara, miembros in manual.items():
        ancla = next((m for m in miembros if m.get("placa_rol") and m.get("occ") is not None), None)
        if ancla is not None:
            anclas_por_cara[cara] = ancla["occ"]
    por_inst = {_clave_inst(p): p for p in piezas}
    dueno = {_clave_inst(m): c for c, ms in manual.items() for m in ms}
    roles: dict[str, dict] = {}
    for cara, occ in anclas_por_cara.items():
        rol = next((k for k, v in CARA_DE_ROL.items() if v == str(cara).upper()), None)
        if not rol or occ is None:
            continue
        if dueno.get(_clave_occ(occ), CARA_DE_ROL[rol]) != CARA_DE_ROL[rol]:
            continue
        placa = por_inst.get(_clave_occ(occ)) or _placa_de_occ(occ)
        if placa:
            roles[rol] = placa
    if len(roles) < len(CARA_DE_ROL):
        candidatas = _placas_grandes(piezas, 12)
        _orientar_afuera(candidatas)
        frente = _frente_camara(assembly) or _frente_mayor(candidatas)
        usadas = {_clave_inst(p) for p in roles.values()} | set(dueno)
        if frente is not None:
            for rol, placa in clasificar_placas(candidatas, frente, ARRIBA).items():
                if rol not in roles and _clave_inst(placa) not in usadas:
                    roles[rol] = placa
                    usadas.add(_clave_inst(placa))
    area_max = _area_max(piezas)
    anclas = {_clave_inst(p) for p in roles.values()}
    bolsas: dict[str, list[dict]] = {}
    asignado: dict[str, tuple[str, float]] = {}
    for rol, placa in roles.items():
        cara = CARA_DE_ROL[rol]
        bolsas[cara] = [_miembro(placa, placa_rol=True, sugerido=True)]
        geo = _geo_placa(placa)
        for pieza in _montadas(placa, piezas, area_max):
            clave = _clave_inst(pieza)
            if clave in anclas:
                continue
            dist = _dist_plano(pieza, geo)
            if clave not in asignado or dist < asignado[clave][1]:
                asignado[clave] = (cara, dist)
    for clave, (cara, _dist) in asignado.items():
        bolsas[cara].append(_miembro(por_inst[clave], placa_rol=False, sugerido=True))
    fijas = {_clave_inst(m) for ms in manual.values() for m in ms}
    out = {c: list(ms) for c, ms in manual.items() if ms}
    for cara, miembros in bolsas.items():
        for miembro in miembros:
            if _clave_inst(miembro) not in fijas:
                out.setdefault(cara, []).append(miembro)
    for bolsa in out.values():
        _fijar_ancla(bolsa)
    _LAST_BAGS = out
    return out


def _clave_inst(miembro: dict) -> str:
    return str(miembro.get("ruta_ocurrencia") or "").replace("\\", "/").strip().lower()


def _clave_occ(occ) -> str:
    from inventor_session import _occ_key

    try:
        return str(_occ_key(occ) or "").replace("\\", "/").strip().lower()
    except Exception:
        return ""


def _area_max(piezas: list[dict]) -> float:
    planas = [p for p in piezas if p.get("plana")] or piezas
    return max((float(p.get("area") or 0) for p in planas), default=0.0)


def _es_placa(pieza: dict, area_max: float) -> bool:
    if pieza.get("placa_rol") or es_placa_muro(pieza.get("nombre_ocurrencia") or ""):
        return True
    if not pieza.get("plana"):
        return False
    return area_max > 0 and float(pieza.get("area") or 0) >= area_max * FRACCION_PLACA


def _dist_plano(pieza: dict, geo: dict | None) -> float:
    try:
        return abs(_dot(_sub(tuple(pieza["centro"]), tuple(geo["centro"])), tuple(geo["normal"])))
    except Exception:
        return float("inf")


def _montadas(placa: dict, piezas: list[dict], area_max: float) -> list[dict]:
    """Lo montado en la cara exterior de la placa (ver montadas_en_cara). Otras placas no entran."""
    if not placa.get("caja"):
        return []
    propia = _clave_inst(placa)
    centro = _centro_piezas(piezas)
    marcos: dict[str, dict] = {}
    for pieza in piezas:
        if _clave_inst(pieza) == propia or _es_placa(pieza, area_max):
            marco = _marco_pieza(pieza, centro)
            if marco:
                marcos[_clave_inst(pieza)] = marco
    marco = marcos.get(propia) or _marco_pieza(placa, centro)
    if marco is None:
        return []
    candidatos = [p for p in piezas if p.get("caja") and _clave_inst(p) not in marcos]
    return montadas_en_cara(propia, marco, candidatos, marcos)


def _centro_piezas(piezas: list[dict]):
    cajas = [p["caja"] for p in piezas if p.get("caja")]
    if not cajas:
        return None
    return tuple((min(c[0][i] for c in cajas) + max(c[1][i] for c in cajas)) / 2 for i in range(3))


def _marco_pieza(pieza: dict, centro_tanque) -> dict | None:
    if not pieza.get("puntos_cara") and pieza.get("occ") is not None:
        normal, area, centro, puntos = _cara_plana_mayor(pieza["occ"])
        if normal is not None:
            pieza.update({"normal": normal, "puntos_cara": puntos, "plana": True})
            if area > 0:
                pieza["area"] = area
            if centro is not None:
                pieza["centro"] = centro
    return marco_cara(pieza.get("normal"), pieza.get("puntos_cara"), pieza.get("caja"), centro_tanque)


def _fijar_ancla(bolsa: list[dict]) -> None:
    if bolsa and not any(m.get("placa_rol") for m in bolsa):
        max(bolsa, key=lambda m: float(m.get("area") or 0))["placa_rol"] = True


def _quitar_inst(bags: dict, clave: str) -> None:
    for cara in list(bags):
        bags[cara] = [m for m in bags[cara] if _clave_inst(m) != clave]


def _aplicar_picks(assembly, bags: dict, rows: list, inteligente: bool) -> tuple[dict, str]:
    """Clics del selector: cada instancia a la cara elegida (o quitada). Clic en una placa
    con selección inteligente suma lo montado en ella, sin robar lo que elegiste a mano."""
    piezas = _piezas_hoja(assembly)
    por_inst = {_clave_inst(p): p for p in piezas}
    area_max = _area_max(piezas)
    bags = {str(c).upper(): list(m or []) for c, m in (bags or {}).items()}
    sumadas = quitadas = montadas = 0
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        clave = str(row.get("path") or "").replace("\\", "/").strip().lower()
        pieza = por_inst.get(clave)
        if pieza is None:
            continue
        _quitar_inst(bags, clave)
        if row.get("removed"):
            quitadas += 1
            continue
        cara = str(row.get("cara") or "").upper()
        if cara not in ORDEN_CARAS:
            continue
        es_placa = _es_placa(pieza, area_max)
        bags.setdefault(cara, []).append(_miembro(pieza, placa_rol=es_placa, sugerido=False))
        sumadas += 1
        if not (inteligente and es_placa):
            continue
        geo = _geo_placa(pieza)
        manuales = {_clave_inst(m) for ms in bags.values() for m in ms if not m.get("sugerido")}
        for extra in _montadas(pieza, piezas, area_max):
            k = _clave_inst(extra)
            if k in manuales:
                continue
            previa = next((c for c, ms in bags.items() if any(_clave_inst(m) == k for m in ms)), None)
            if previa and previa != cara:
                ancla = next((m for m in bags[previa] if m.get("placa_rol")), None)
                if ancla is not None and _dist_plano(extra, _geo_placa(ancla)) <= _dist_plano(extra, geo):
                    continue
            _quitar_inst(bags, k)
            bags[cara].append(_miembro(extra, placa_rol=False, sugerido=True))
            montadas += 1
    for bolsa in bags.values():
        _fijar_ancla(bolsa)
    bags = {c: ms for c, ms in bags.items() if ms}
    partes = [f"{sumadas} clic(s) aplicados"]
    if montadas:
        partes.append(f"{montadas} pieza(s) montadas en las placas")
    if quitadas:
        partes.append(f"{quitadas} quitada(s)")
    return bags, ", ".join(partes) + "."


def _piezas_hoja(assembly) -> list[dict]:
    """Cajas de todas las hojas. Solo las láminas grandes recorren caras (cara plana mayor)."""
    filas = []
    try:
        leaves = assembly.ComponentDefinition.Occurrences.AllLeafOccurrences
        total = int(leaves.Count)
    except Exception:
        return filas
    hojas = []
    for index in range(1, total + 1):
        try:
            occ = leaves.Item(index)
            if bool(occ.Suppressed):
                continue
            if int(occ.DefinitionDocumentType) != TIPO_IPT:
                continue
            caja = _caja(occ)
        except Exception:
            continue
        if caja is not None:
            hojas.append((occ, caja))
    laminas = [_area_caja(c) for _o, c in hojas if _es_lamina(c)]
    corte = max(laminas, default=0.0) * FRACCION_PLACA * 0.6
    for occ, caja in hojas:
        try:
            caras = _es_lamina(caja) and _area_caja(caja) >= corte
            placa = _placa_de_occ(occ, caja=caja, caras=caras)
        except Exception:
            continue
        if placa:
            filas.append(placa)
    return filas


def _es_lamina(caja) -> bool:
    d = sorted(abs(caja[1][i] - caja[0][i]) for i in range(3))
    return d[1] > 0 and d[0] <= 0.15 * d[1]


def _claves_pieza(pieza: dict) -> set[str]:
    from inventor_session import _occ_key

    keys: set[str] = set()
    raws = [
        pieza.get("ruta_archivo"),
        pieza.get("ruta_ocurrencia"),
        pieza.get("nombre_ocurrencia"),
    ]
    occ = pieza.get("occ")
    if occ is not None:
        try:
            raws.append(_occ_key(occ))
        except Exception:
            pass
    for raw in raws:
        text = str(raw or "").replace("\\", "/").strip().lower()
        if not text:
            continue
        keys.add(text)
        keys.add(text.rsplit("/", 1)[-1])
        stem = text.rsplit("/", 1)[-1]
        if "." in stem:
            keys.add(stem.rsplit(".", 1)[0])
    return keys


def _pieza_en_rutas(pieza: dict, wanted: set[str]) -> bool:
    if not wanted:
        return False
    keys = _claves_pieza(pieza)
    if keys & wanted:
        return True
    occ = str(pieza.get("ruta_ocurrencia") or "").replace("\\", "/").lower()
    if not occ:
        occ = next((k for k in keys if "/" in k), "")
    for w in wanted:
        if not w:
            continue
        if occ == w or (occ and occ.startswith(w.rstrip("/") + "/")):
            return True
        if w in occ or occ.endswith("/" + w):
            return True
    return False


def _placa_de_occ(occ, caja=None, caras: bool = True) -> dict | None:
    caja = caja or _caja(occ)
    if caja is None:
        return None
    from inventor_session import _occ_key

    doc = occ.Definition.Document
    path = str(doc.FullFileName or "")
    nombre = str(occ.Name or Path(path).name)
    occ_path = _occ_key(occ)
    nombre_muro = es_placa_muro(nombre) or es_placa_muro(path)
    if caras or nombre_muro:
        normal, area, centro, puntos = _cara_plana_mayor(occ)
    else:
        normal, area, centro, puntos = None, 0.0, None, []
    plana = normal is not None and _es_lamina(caja)
    if centro is None:
        centro = (
            (caja[0][0] + caja[1][0]) / 2,
            (caja[0][1] + caja[1][1]) / 2,
            (caja[0][2] + caja[1][2]) / 2,
        )
    if area <= 0:
        area = _area_caja(caja)
    if normal is None:
        normal = (0.0, 0.0, 1.0)
    return {
        "occ": occ,
        "caja": caja,
        "centro": centro,
        "normal": normal,
        "area": float(area),
        "plana": plana,
        "puntos_cara": puntos,
        "nombre_ocurrencia": nombre,
        "ruta_archivo": path,
        "ruta_ocurrencia": occ_path,
        "placa_rol": nombre_muro,
    }


def _miembro(pieza: dict, placa_rol: bool, sugerido: bool) -> dict:
    return {
        "nombre_ocurrencia": pieza.get("nombre_ocurrencia"),
        "ruta_archivo": pieza.get("ruta_archivo"),
        "ruta_ocurrencia": pieza.get("ruta_ocurrencia"),
        "placa_rol": placa_rol,
        "sugerido": sugerido,
        "occ": pieza.get("occ"),
        "caja": pieza.get("caja"),
        "centro": pieza.get("centro"),
        "area": pieza.get("area"),
        "normal": pieza.get("normal"),
        "plana": pieza.get("plana"),
        "puntos_cara": pieza.get("puntos_cara"),
    }


def _caja(occ):
    try:
        rb = occ.RangeBox
        mn = (float(rb.MinPoint.X), float(rb.MinPoint.Y), float(rb.MinPoint.Z))
        mx = (float(rb.MaxPoint.X), float(rb.MaxPoint.Y), float(rb.MaxPoint.Z))
    except Exception:
        return None
    return (mn, mx)


def _area_caja(caja) -> float:
    dx = abs(caja[1][0] - caja[0][0])
    dy = abs(caja[1][1] - caja[0][1])
    dz = abs(caja[1][2] - caja[0][2])
    return max(dx * dy, dx * dz, dy * dz)


def _placas_grandes(piezas: list[dict], n: int) -> list[dict]:
    planas = [p for p in piezas if p.get("plana") or p.get("placa_rol")] or piezas
    orden = sorted(planas, key=lambda item: float(item.get("area") or 0), reverse=True)
    return orden[: max(1, n)]


def _orientar_afuera(placas: list[dict]) -> None:
    if not placas:
        return
    cx = sum(p["centro"][0] for p in placas) / len(placas)
    cy = sum(p["centro"][1] for p in placas) / len(placas)
    cz = sum(p["centro"][2] for p in placas) / len(placas)
    centro = (cx, cy, cz)
    for placa in placas:
        normal = _norm(tuple(placa["normal"]))
        if normal is None:
            continue
        if _dot(normal, _sub(placa["centro"], centro)) < 0:
            placa["normal"] = _scale(normal, -1.0)


def _frente_camara(assembly):
    try:
        view = assembly.Parent.ActiveView
        cam = view.Camera
        eye = (float(cam.Eye.X), float(cam.Eye.Y), float(cam.Eye.Z))
        tgt = (float(cam.Target.X), float(cam.Target.Y), float(cam.Target.Z))
    except Exception:
        return None
    return _norm(_sub(eye, tgt))


def _frente_mayor(placas: list[dict]):
    muros = []
    for placa in placas:
        normal = _norm(tuple(placa["normal"]))
        if normal is None:
            continue
        if abs(_dot(normal, ARRIBA)) <= 0.35:
            muros.append(placa)
    if not muros:
        return None
    mejor = max(muros, key=lambda item: float(item.get("area") or 0))
    return _norm(tuple(mejor["normal"]))


def _cara_plana_mayor(occ) -> tuple:
    """(normal, área, punto, puntos de las caras grandes paralelas: interior y exterior)."""
    plano = 5890
    planas: list[tuple[float, object]] = []
    try:
        bodies = occ.SurfaceBodies
        n_body = int(bodies.Count)
    except Exception:
        return None, 0.0, None, []
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
                planas.append((float(face.Evaluator.Area), face))
            except Exception:
                continue
    if not planas:
        return None, 0.0, None, []
    planas.sort(key=lambda item: item[0], reverse=True)
    area_max, mejor = planas[0]
    normal = _normal_cara(mejor)
    if normal is None:
        return None, 0.0, None, []
    puntos = []
    for area, face in planas:
        if area < area_max * 0.5:
            break
        n = _normal_cara(face)
        if n is None or abs(_dot(n, normal)) < 0.99:
            continue
        try:
            pt = face.PointOnFace
            puntos.append((float(pt.X), float(pt.Y), float(pt.Z)))
        except Exception:
            continue
    return normal, area_max, (puntos[0] if puntos else None), puntos


def _normal_cara(face):
    try:
        n = face.Geometry.Normal
        return _norm((float(n.X), float(n.Y), float(n.Z)))
    except Exception:
        return None


def run_roles_action(payload: dict | None = None) -> dict:
    payload = payload or {}
    action = str(payload.get("action") or "snapshot").strip().lower()
    from inventor_session import _active_assembly, _full_name, _inventor, _name

    try:
        inv = _inventor()
        assembly = _active_assembly(inv)
    except Exception as ex:
        return {"ok": False, "message": str(ex), "bags": {}, "colors": COLORES_CARA}
    if assembly is None:
        return {"ok": False, "message": "Abre un ensamble (.iam) en Inventor.", "bags": {}, "colors": COLORES_CARA}

    if action == "propose":
        _bags_actuales(assembly)
        bags = proponer_muros(assembly, anclas_por_cara=_anclas_por_nombre(assembly))
        guardar_sesion(assembly, bags, confirmed=False)
        n = pintar_bolsas(assembly, bags)
        faltan = [c for c in ORDEN_CARAS if c not in bags]
        nota = f" Sin placa: {', '.join(faltan)} (clic en la placa de esa cara)." if faltan else ""
        return _snapshot(
            assembly,
            True,
            f"Propuesta pintada ({n} piezas). Lo que elegiste a mano se respetó.{nota} Ajusta y confirma.",
        )
    if action == "paint":
        bags = cosechar_pintura(assembly, _bags_actuales(assembly))
        n = pintar_bolsas(assembly, bags)
        return _snapshot(assembly, True, f"Se volvió a pintar {n} piezas.")
    if action == "confirm":
        bags = cosechar_pintura(assembly, _bags_actuales(assembly))
        for miembros in bags.values():
            for miembro in miembros:
                miembro["sugerido"] = False
        guardar_sesion(assembly, bags, confirmed=True)
        pintar_bolsas(assembly, bags, tocar_vista=False)
        return _snapshot(assembly, True, "Selección confirmada. Ya puedes acotar.")
    if action == "clear":
        cara = str(payload.get("cara") or "").upper()
        bags = _bags_actuales(assembly)
        if cara in bags:
            bags[cara] = [m for m in bags[cara] if m.get("placa_rol")]
        guardar_sesion(assembly, bags, confirmed=False)
        pintar_bolsas(assembly, bags)
        return _snapshot(assembly, True, f"{cara}: quedó solo la placa.")
    if action == "remove":
        clave = str(payload.get("ocurrencia") or "").replace("\\", "/").strip().lower()
        ruta = str(payload.get("ruta") or "").replace("\\", "/").lower()
        cara_activa = str(payload.get("cara") or "").upper()
        bags = _bags_actuales(assembly)
        for cara in [cara_activa] if cara_activa in bags else list(bags):
            bags[cara] = [
                m
                for m in bags.get(cara) or []
                if not (
                    _clave_inst(m) == clave
                    if clave
                    else str(m.get("ruta_archivo") or "").replace("\\", "/").lower() == ruta
                )
            ]
            _fijar_ancla(bags[cara])
        bags = {c: ms for c, ms in bags.items() if ms}
        guardar_sesion(assembly, bags, confirmed=False)
        pintar_bolsas(assembly, bags)
        return _snapshot(assembly, True, "Pieza quitada.")
    if action in {"pick", "ingest", "add"}:
        inteligente = bool(payload.get("smart", True))
        if action == "pick":
            rows = payload.get("rows") or []
        elif action == "add" and payload.get("rutas"):
            cara = str(payload.get("cara") or "").upper()
            wanted = {str(p).replace("\\", "/").lower() for p in payload.get("rutas") or [] if p}
            rows = [
                {"path": p.get("ruta_ocurrencia"), "cara": cara}
                for p in _piezas_hoja(assembly)
                if _pieza_en_rutas(p, wanted)
            ]
        else:
            rows = _filas_selector(str(payload.get("cara") or "").upper())
        bags, nota = _aplicar_picks(assembly, _bags_actuales(assembly), rows, inteligente)
        guardar_sesion(assembly, bags, confirmed=False)
        pintar_bolsas(assembly, bags)
        if not rows:
            nota = "El selector no devolvió piezas. Inicia de nuevo, clic en cada muro y pulsa Terminar."
        return _snapshot(assembly, True, nota)
    if action == "restore":
        bags = _bags_actuales(assembly)
        if not bags:
            try:
                ruta_iam = str(assembly.FullFileName or "")
            except Exception:
                ruta_iam = ""
            bags = hidratar(assembly, bags_ensamble(ruta_iam))
        if bags:
            pintar_bolsas(assembly, bags)
        n = sum(len(m) for m in bags.values())
        return _snapshot(assembly, True, f"Sesión de {_name(assembly)}: {n} piezas en {len(bags)} caras.")
    return _snapshot(assembly, True, "")


def _bags_actuales(assembly) -> dict[str, list[dict]]:
    return last_bags() or hidratar(assembly, load_session(assembly).get("bags") or {})


def _filas_selector(fallback: str) -> list[dict]:
    from inventor_session import _read_pick_paths, read_pick_status

    paths, _lengths, classes = _read_pick_paths()
    rows = [
        {"path": p, "cara": str(classes.get(str(p).replace("\\", "/").lower()) or fallback).upper()}
        for p in paths
    ]
    for path in read_pick_status().get("removed") or []:
        rows.append({"path": path, "cara": fallback, "removed": True})
    return rows


def filas_desde_sesion(assembly) -> list[tuple]:
    bags_raw = load_session(assembly).get("bags") or {}
    path = _ruta_iam(assembly)
    if not bags_raw:
        bags_raw = bags_ensamble(path)
    if not bags_raw:
        return []
    bags = hidratar(assembly, bags_raw)
    if not bags:
        return []
    global _LAST_BAGS
    _LAST_BAGS = bags
    rows = []
    for cara in ORDEN_CARAS:
        miembros = bags.get(cara) or []
        ancla = next((m for m in miembros if m.get("placa_rol") and m.get("occ") is not None), None)
        if ancla is None:
            ancla = next((m for m in miembros if m.get("occ") is not None), None)
        if ancla is not None:
            rows.append((cara, assembly, 1, ancla["occ"]))
    return rows


def pintar_bolsas(assembly, bags: dict[str, list[dict]] | None = None, tocar_vista: bool = True) -> int:
    """Pinta exactamente las instancias de las bolsas y quita el color de muro a las demás."""
    from inventor_session import _all_occurrences, _clear_appearance, _hex_rgb, _inventor

    if bags is None:
        bags = last_bags()
    try:
        inv = assembly.Parent if hasattr(assembly, "Parent") else _inventor()
    except Exception:
        inv = _inventor()
    try:
        dv = assembly.ComponentDefinition.RepresentationsManager.ActiveDesignViewRepresentation
        if bool(getattr(dv, "Locked", False)):
            dv.Locked = False
    except Exception:
        pass
    destino = {
        _clave_inst(m): cara
        for cara, miembros in (bags or {}).items()
        for m in (miembros or [])
        if _clave_inst(m)
    }
    painted = 0
    assets: dict[str, object] = {}
    for occ, _key in _all_occurrences(assembly):
        cara = destino.get(_clave_occ(occ))
        actual = _cara_de_occ(occ)
        if cara is None:
            if actual:
                _clear_appearance(occ)
            continue
        if actual == cara:
            painted += 1
            continue
        asset = assets.get(cara)
        if asset is None:
            asset = _asset_rol(inv, assembly, cara, _hex_rgb(COLORES_CARA.get(cara, "#7C3AED")))
            assets[cara] = asset
        if asset is None:
            continue
        if _aplicar_color(occ, asset, assembly):
            painted += 1
    if tocar_vista:
        try:
            view = inv.ActiveView
            mode = int(getattr(view, "DisplayMode", 0) or 0)
            if mode not in {8709, 8710}:
                view.DisplayMode = 8709
            view.Update()
        except Exception:
            try:
                inv.ActiveView.Update()
            except Exception:
                pass
    else:
        try:
            inv.ActiveView.Update()
        except Exception:
            pass
    return painted


def cosechar_pintura(assembly, bags: dict[str, list[dict]] | None) -> dict[str, list[dict]]:
    """Suma instancias pintadas a mano con un color de muro AutoDXF, en la cara de ese color."""
    bags = {str(c).upper(): list(m or []) for c, m in (bags or {}).items()}
    have = {_clave_inst(m) for miembros in bags.values() for m in miembros}
    for pieza in _piezas_hoja(assembly):
        clave = _clave_inst(pieza)
        cara = _cara_de_occ(pieza.get("occ"))
        if not cara or not clave or clave in have:
            continue
        bags.setdefault(cara, []).append(_miembro(pieza, False, False))
        have.add(clave)
    for bolsa in bags.values():
        _fijar_ancla(bolsa)
    global _LAST_BAGS
    _LAST_BAGS = bags
    return bags


def _cara_de_aparencia(nombre: str) -> str | None:
    """Solo aspectos propios del selector ("AutoDXF SEGM1 …"): los colores de biblioteca
    los usa también la clasificación por bloques y no indican muro."""
    upper = str(nombre or "").strip().upper()
    if upper.startswith("AUTODXF ROL "):
        upper = "AUTODXF " + upper[12:]
    if not upper.startswith("AUTODXF "):
        return None
    rest = upper[8:].strip()
    for cara in COLORES_CARA:
        if rest == cara or rest.startswith(cara + " "):
            return cara
    return None


def _cara_de_occ(occ) -> str | None:
    try:
        if int(occ.AppearanceSourceType) != 100609:
            return None
        asset = occ.Appearance
        if asset is None:
            return None
        return _cara_de_aparencia(str(asset.DisplayName or ""))
    except Exception:
        return None


def _doc_contenedor(occ, assembly):
    try:
        parent = occ.ParentOccurrence
        if parent is not None:
            return parent.Definition.Document
    except Exception:
        pass
    try:
        return occ.Parent.Document
    except Exception:
        return assembly


def _aplicar_color(occ, asset, assembly) -> bool:
    from inventor_session import _set_appearance

    if asset is None:
        return False
    docs = []
    for doc in (_doc_contenedor(occ, assembly), assembly):
        if doc is not None and doc not in docs:
            docs.append(doc)
    for doc in docs:
        local = asset
        try:
            if doc is not None and doc is not assembly:
                local = asset.CopyTo(doc, True)
        except Exception:
            local = asset
        if _set_appearance(occ, local or asset):
            return True
    return _set_appearance(occ, asset)


def _asset_rol(inv, document, cara: str, rgb: tuple[int, int, int]):
    from inventor_session import (
        _appearance_in_document,
        _copy_library_appearance,
        _set_asset_opacity,
        _tint_appearance,
    )

    r, g, b = rgb
    display = f"AutoDXF {cara} {r}-{g}-{b}"
    asset = _appearance_in_document(document, display)
    if asset is None:
        asset = _appearance_in_document(document, f"AutoDXF Rol {cara}")
    if asset is None:
        for proto in ("Generic", "Genérico"):
            try:
                asset = document.Assets.Add(1044482, proto, display)
                break
            except Exception:
                try:
                    asset = document.AppearanceAssets.Add(proto, display)
                    break
                except Exception:
                    continue
    if asset is None:
        asset = _copy_library_appearance(inv, document, ("Generic", "Genérico"))
        if asset is None:
            return None
        try:
            asset.DisplayName = display
        except Exception:
            pass
    _tint_appearance(inv, asset, (r, g, b))
    _tint_por_recorrido(inv, asset, (r, g, b))
    _set_asset_opacity(asset, 1.0)
    return asset


def _tint_por_recorrido(inv, asset, rgb: tuple[int, int, int]) -> None:
    import win32com.client

    r, g, b = rgb
    try:
        shade = inv.TransientObjects.CreateColor(int(r), int(g), int(b))
        total = int(asset.Count)
    except Exception:
        return
    for index in range(1, total + 1):
        try:
            item = asset.Item(index)
            label = str(getattr(item, "Name", "") or "").lower()
            if "tint" in label or "bump" in label:
                continue
            slot = win32com.client.CastTo(item, "ColorAssetValue")
            slot.Value = shade
            if "diffuse" in label or "color" in label:
                return
        except Exception:
            continue


def _ruta_iam(assembly) -> str:
    try:
        return str(assembly.FullFileName or "")
    except Exception:
        return ""


def _clave_iam(ruta: str) -> str:
    return str(ruta or "").replace("\\", "/").strip().lower()


def _leer_sesiones() -> dict:
    """{"assemblies": {ruta_iam: {assembly, confirmed, bags}}}; migra el archivo viejo de un solo ensamble."""
    if not SESSION_PATH.is_file():
        return {"assemblies": {}}
    try:
        data = json.loads(SESSION_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {"assemblies": {}}
    if not isinstance(data, dict):
        return {"assemblies": {}}
    todos = data.get("assemblies") if isinstance(data.get("assemblies"), dict) else {}
    if data.get("assembly") and isinstance(data.get("bags"), dict):
        todos.setdefault(
            _clave_iam(data["assembly"]),
            {"assembly": data["assembly"], "confirmed": bool(data.get("confirmed")), "bags": data["bags"]},
        )
    return {"assemblies": todos}


def guardar_sesion(assembly, bags: dict, confirmed: bool) -> None:
    global _LAST_BAGS
    _LAST_BAGS = bags
    path = _ruta_iam(assembly)
    datos = _leer_sesiones()
    datos["assemblies"][_clave_iam(path)] = {
        "assembly": path,
        "confirmed": bool(confirmed),
        "bags": {
            cara: [_publico(m) for m in (miembros or [])]
            for cara, miembros in (bags or {}).items()
            if miembros
        },
    }
    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    SESSION_PATH.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    if confirmed:
        try:
            registrar_foto_ensamble(path, bags)
        except Exception:
            pass


def load_session(assembly=None) -> dict:
    """Sesión del ensamble dado (o del activo en Inventor si no se pasa)."""
    if assembly is None:
        try:
            from inventor_session import _active_assembly, _inventor

            assembly = _active_assembly(_inventor())
        except Exception:
            assembly = None
    hit = _leer_sesiones()["assemblies"].get(_clave_iam(_ruta_iam(assembly))) if assembly is not None else None
    return hit if isinstance(hit, dict) else {}


def hidratar(assembly, bags_raw) -> dict[str, list[dict]]:
    """Cada miembro guardado vuelve a su instancia y a la cara que tenía. Sesiones viejas sin
    ruta de ocurrencia se reconstruyen por plano de placa."""
    global _LAST_BAGS
    if not isinstance(bags_raw, dict):
        bags_raw = {}
    planos = [m for ms in bags_raw.values() for m in (ms or []) if isinstance(m, dict)]
    if planos and not any(m.get("ruta_ocurrencia") for m in planos):
        return _hidratar_legacy(assembly, bags_raw)
    por_inst = {_clave_inst(p): p for p in _piezas_hoja(assembly)}
    bags: dict[str, list[dict]] = {}
    vistos: set[str] = set()
    for cara, miembros in bags_raw.items():
        cara = str(cara).upper()
        if cara not in ORDEN_CARAS:
            continue
        filas = []
        for miembro in miembros or []:
            if not isinstance(miembro, dict):
                continue
            clave = _clave_inst(miembro)
            pieza = por_inst.get(clave)
            if pieza is None or clave in vistos:
                continue
            vistos.add(clave)
            filas.append(_miembro(pieza, bool(miembro.get("placa_rol")), bool(miembro.get("sugerido", False))))
        _fijar_ancla(filas)
        if filas:
            bags[cara] = filas
    _LAST_BAGS = bags
    return bags


def _hidratar_legacy(assembly, bags_raw: dict) -> dict[str, list[dict]]:
    global _LAST_BAGS
    piezas = _piezas_hoja(assembly)
    bags: dict[str, list[dict]] = {}
    for cara, miembros in bags_raw.items():
        filas = []
        for miembro in miembros or []:
            if not isinstance(miembro, dict):
                continue
            if miembro.get("placa_rol"):
                path = str(miembro.get("ruta_archivo") or "").replace("\\", "/").lower()
                pieza = next(
                    (
                        p
                        for p in piezas
                        if str(p.get("ruta_archivo") or "").replace("\\", "/").lower() == path
                    ),
                    None,
                )
                filas.append(_miembro(pieza or miembro, True, bool(miembro.get("sugerido", False))))
        if filas:
            bags[str(cara).upper()] = filas
    anclas_geo = _anclas_desde_bags(bags, piezas)
    bolsas_rol = _bolsas_rol(bags)
    if not bolsas_rol:
        for cara, miembros in bags_raw.items():
            rol = next((k for k, v in CARA_DE_ROL.items() if v == str(cara).upper()), None)
            if rol:
                bolsas_rol[rol] = list(miembros or [])
    _repartir_por_plano(bolsas_rol, piezas, anclas_geo, bags_raw=bags_raw)
    por_cara: dict[str, list[dict]] = {}
    for rol, miembros in bolsas_rol.items():
        cara = CARA_DE_ROL.get(rol)
        if cara and miembros:
            por_cara[cara] = miembros
    _LAST_BAGS = por_cara
    return por_cara


def _publico(miembro: dict) -> dict:
    return {
        "nombre_ocurrencia": miembro.get("nombre_ocurrencia"),
        "ruta_archivo": miembro.get("ruta_archivo"),
        "ruta_ocurrencia": miembro.get("ruta_ocurrencia"),
        "placa_rol": bool(miembro.get("placa_rol")),
        "sugerido": bool(miembro.get("sugerido", True)),
    }


def _snapshot(assembly, ok: bool, message: str) -> dict:
    from inventor_session import _name

    bags = last_bags()
    public = {cara: [_publico(m) for m in miembros] for cara, miembros in bags.items()}
    n = sum(len(v) for v in public.values())
    confirmed = bool(load_session(assembly).get("confirmed"))
    return {
        "ok": ok,
        "message": message or f"{n} piezas en 6 caras.",
        "bags": public,
        "colors": COLORES_CARA,
        "confirmed": confirmed,
        "assembly": _name(assembly),
        "count": n,
    }


def _anclas_por_nombre(assembly) -> dict:
    anclas = {}
    for pieza in _piezas_hoja(assembly):
        cara = TOKEN_A_CARA.get(token_de_miembro(pieza))
        if cara and cara not in anclas and pieza.get("occ") is not None:
            anclas[cara] = pieza["occ"]
    return anclas


def _geo_placa(placa: dict) -> dict | None:
    if not placa:
        return None
    centro = placa.get("centro")
    raw = placa.get("normal")
    if centro is None or not isinstance(raw, (list, tuple)) or len(raw) < 3:
        return None
    normal = _norm((float(raw[0]), float(raw[1]), float(raw[2])))
    if normal is None:
        return None
    geo = {"centro": centro, "normal": normal, "occ": placa.get("occ"), "pieza": placa}
    occ = placa.get("occ")
    if occ is None:
        return geo
    try:
        rb = occ.RangeBox
        corners = [
            (float(x), float(y), float(z))
            for x in (rb.MinPoint.X, rb.MaxPoint.X)
            for y in (rb.MinPoint.Y, rb.MaxPoint.Y)
            for z in (rb.MinPoint.Z, rb.MaxPoint.Z)
        ]
    except Exception:
        return geo
    n = normal
    v = _norm(_sub((0.0, 1.0, 0.0), _scale(n, _dot((0.0, 1.0, 0.0), n))))
    if v is None:
        v = _norm(_sub((1.0, 0.0, 0.0), _scale(n, _dot((1.0, 0.0, 0.0), n))))
    u = _norm(_cross(v, n)) if v is not None else None
    if u is None or v is None:
        return geo
    us = [_dot(_sub(p, centro), u) for p in corners]
    vs = [_dot(_sub(p, centro), v) for p in corners]
    geo.update({"u": u, "v": v, "umin": min(us), "umax": max(us), "vmin": min(vs), "vmax": max(vs)})
    return geo


def _anclas_desde_bags(bags: dict, piezas: list[dict]) -> dict[str, dict]:
    geo: dict[str, dict] = {}
    for cara, miembros in (bags or {}).items():
        for m in miembros or []:
            if not m.get("placa_rol"):
                continue
            placa = m if m.get("centro") and m.get("normal") else None
            if placa is None and m.get("occ") is not None:
                placa = _placa_de_occ(m["occ"])
            if placa is None:
                path = str(m.get("ruta_archivo") or "").replace("\\", "/").lower()
                placa = next(
                    (
                        p
                        for p in piezas
                        if str(p.get("ruta_archivo") or "").replace("\\", "/").lower() == path
                    ),
                    None,
                )
            hit = _geo_placa(placa or {})
            if hit:
                geo[str(cara).upper()] = hit
            break
    if len(geo) < 6:
        for pieza in piezas:
            cara = TOKEN_A_CARA.get(token_de_miembro(pieza))
            if cara and cara not in geo:
                hit = _geo_placa(pieza)
                if hit:
                    geo[cara] = hit
    return geo


def _cara_por_plano(pieza: dict | None, anclas: dict[str, dict]) -> str | None:
    """Muro cuya placa contiene el punto (distancia al plano + penalización si cae fuera de la cara)."""
    if not pieza or not anclas:
        return None
    p = pieza.get("centro")
    if not p:
        return None
    mejor = None
    mejor_s = None
    for cara, a in anclas.items():
        try:
            c = tuple(a["centro"])
            n = tuple(a["normal"])
            d = abs(_dot(_sub(tuple(p), c), n))
        except Exception:
            continue
        penal = 0.0
        if a.get("u") is not None and "umin" in a:
            try:
                uu = _dot(_sub(tuple(p), c), tuple(a["u"]))
                vv = _dot(_sub(tuple(p), c), tuple(a["v"]))
                du = max(0.0, a["umin"] - uu, uu - a["umax"])
                dv = max(0.0, a["vmin"] - vv, vv - a["vmax"])
                penal = (du + dv) * 3.0
            except Exception:
                penal = 0.0
        s = d + penal
        if mejor_s is None or s < mejor_s:
            mejor, mejor_s = cara, s
    return mejor


def _repartir_por_plano(bolsas_rol: dict, piezas: list, anclas_geo: dict, bags_raw=None) -> None:
    """Cada instancia al muro de su placa. El mismo .ipt puede quedar en varios segmentos."""
    from roles_muros import cargar_aprendizaje, token_de_miembro

    paths = set()
    for bolsa in bolsas_rol.values():
        for m in bolsa or []:
            if m.get("placa_rol"):
                continue
            path = str(m.get("ruta_archivo") or "").replace("\\", "/").lower()
            if path:
                paths.add(path)
    if isinstance(bags_raw, dict):
        for miembros in bags_raw.values():
            for m in miembros or []:
                if isinstance(m, dict) and not m.get("placa_rol") and m.get("ruta_archivo"):
                    paths.add(str(m.get("ruta_archivo") or "").replace("\\", "/").lower())
    mem = cargar_aprendizaje().get("tank") if isinstance(cargar_aprendizaje().get("tank"), dict) else {}
    excluir_rol = {}
    for rol in list(bolsas_rol):
        info = mem.get(rol) if isinstance(mem.get(rol), dict) else {}
        excluir_rol[rol] = {str(x) for x in (info.get("excluir") or []) if str(x)}
        bolsas_rol[rol] = [m for m in (bolsas_rol.get(rol) or []) if m.get("placa_rol")]
    have = set()
    inv = {v: k for k, v in CARA_DE_ROL.items()}
    for pieza in piezas:
        if pieza.get("placa_rol") or es_placa_muro(pieza.get("nombre_ocurrencia") or ""):
            continue
        path = str(pieza.get("ruta_archivo") or "").replace("\\", "/").lower()
        if path not in paths:
            continue
        cara = _cara_por_plano(pieza, anclas_geo)
        rol = inv.get(cara) if cara else None
        if not rol:
            continue
        token = token_de_miembro(pieza)
        if token and token in excluir_rol.get(rol, set()):
            continue
        inst = _instancia_id(pieza)
        if inst in have:
            continue
        have.add(inst)
        bolsas_rol.setdefault(rol, []).append(_miembro(pieza, False, True))


def _bolsas_rol(bags: dict) -> dict:
    inv = {v: k for k, v in CARA_DE_ROL.items()}
    return {inv[cara]: miembros for cara, miembros in bags.items() if cara in inv}
