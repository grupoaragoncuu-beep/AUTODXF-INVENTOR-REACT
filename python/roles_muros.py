"""Selector L2: clasificar placas de muro y memoria de roles (sin Inventor)."""

from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path

ROLES_MURO = (
    "Segmento_1",
    "Segmento_2",
    "Segmento_3",
    "Segmento_4",
    "Base",
    "Top_Cover",
)
ROLES_PUBLICAR = ROLES_MURO + ("Lifting_Lug", "Jacking_Pad", "Componentes")
CARA_DE_ROL = {
    "Segmento_1": "SEGM1",
    "Segmento_2": "SEGM2",
    "Segmento_3": "SEGM3",
    "Segmento_4": "SEGM4",
    "Top_Cover": "TOP",
    "Base": "BASE",
}

HOLGURA = 1.5
TOLERANCIA_CONTACTO = 0.005
UMBRAL_HORIZONTAL = 0.35
UMBRAL_ALINEACION = 0.72
_PREFIJO_JOB = re.compile(r"^\d+[_\- ]+")
_NOMBRE_MURO = re.compile(
    r"^(?:seg(?:m|mento)?|segment)[\s_\-]*[1-4]$"
    r"|^(?:s[\s_\-]*[1-4])$"
    r"|^(?:base)$"
    r"|^(?:top[\s_\-]*cover|tapa(?:[\s_\-]*superior)?|cubierta|tank[\s_\-]*lid|tank[\s_\-]*base)$",
    re.IGNORECASE,
)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _scale(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _norm(v):
    length = math.sqrt(_dot(v, v))
    if length < 1e-9:
        return None
    return (v[0] / length, v[1] / length, v[2] / length)


def _aplanar(v, arriba):
    return _norm(_sub(v, _scale(arriba, _dot(v, arriba))))


def es_placa_muro(texto: str) -> bool:
    cola = str(texto or "").replace("\\", "/").split("/")[-1].split(":")[0].strip()
    cola = Path(cola).stem
    cola = _PREFIJO_JOB.sub("", cola)
    return bool(_NOMBRE_MURO.match(cola))


def cajas_cerca(a, b, holgura=HOLGURA) -> bool:
    for eje in range(3):
        if b[1][eje] < a[0][eje] - holgura or b[0][eje] > a[1][eje] + holgura:
            return False
    return True


# Montado en un muro = toca o atraviesa la cara EXTERIOR de su placa, dentro de su rectángulo,
# y esa placa es la más cercana de los 6 muros. Solo cajas (cm): sin GetMinimumDistance.
CONTACTO_CARA_CM = 0.3
SALE_CARA_CM = 0.05
MARGEN_CARA_CM = 0.5
MONTAJE_CM = 0.5
_RONDAS_MONTAJE = 4


def _esquinas(caja) -> list[tuple[float, float, float]]:
    (x0, y0, z0), (x1, y1, z1) = caja
    return [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]


def centro_caja(caja) -> tuple[float, float, float]:
    return tuple((float(caja[0][i]) + float(caja[1][i])) / 2 for i in range(3))


def marco_cara(normal, puntos_cara, caja_placa, centro_tanque) -> dict | None:
    """Plano exterior de la placa: normal hacia afuera del tanque y rectángulo u/v de la placa."""
    n = _norm(tuple(float(c) for c in normal)) if normal is not None else None
    if n is None or not caja_placa:
        return None
    origen = centro_caja(caja_placa)
    if centro_tanque is not None and _dot(n, _sub(origen, tuple(centro_tanque))) < 0:
        n = _scale(n, -1.0)
    puntos = [tuple(float(c) for c in p) for p in (puntos_cara or []) if p is not None]
    if not puntos:
        puntos = _esquinas(caja_placa)
    exterior = max(_dot(p, n) for p in puntos)
    v = _aplanar((0.0, 1.0, 0.0), n) or _aplanar((1.0, 0.0, 0.0), n)
    u = _norm(_cross(v, n)) if v is not None else None
    if u is None or v is None:
        return None
    esquinas = _esquinas(caja_placa)
    us = [_dot(_sub(p, origen), u) for p in esquinas]
    vs = [_dot(_sub(p, origen), v) for p in esquinas]
    return {
        "n": n,
        "u": u,
        "v": v,
        "origen": origen,
        "exterior": exterior,
        "umin": min(us),
        "umax": max(us),
        "vmin": min(vs),
        "vmax": max(vs),
    }


def _rango_s(caja, marco) -> tuple[float, float]:
    s = [_dot(p, marco["n"]) - marco["exterior"] for p in _esquinas(caja)]
    return min(s), max(s)


def _fuera_rect(punto, marco) -> float:
    rel = _sub(punto, marco["origen"])
    uu, vv = _dot(rel, marco["u"]), _dot(rel, marco["v"])
    du = max(0.0, marco["umin"] - uu, uu - marco["umax"])
    dv = max(0.0, marco["vmin"] - vv, vv - marco["vmax"])
    return du + dv


def dueno_muro(caja, marcos: dict) -> str | None:
    """Muro más cercano: distancia al plano exterior + 3× lo que se sale de su rectángulo."""
    c = centro_caja(caja)
    mejor, mejor_s = None, None
    for clave, marco in (marcos or {}).items():
        s = abs(_dot(c, marco["n"]) - marco["exterior"]) + 3.0 * _fuera_rect(c, marco)
        if mejor_s is None or s < mejor_s:
            mejor, mejor_s = clave, s
    return mejor


def montadas_en_cara(propia: str, marco: dict, candidatos: list[dict], marcos: dict | None = None) -> list[dict]:
    """Nivel 1: toca/atraviesa la cara exterior. Luego, lo que se apoya en eso, siempre delante
    de la cara, dentro del rectángulo y con este muro como dueño. Nunca entra lo de otro muro."""
    marcos = dict(marcos or {})
    marcos.setdefault(propia, marco)
    nivel1: list[dict] = []
    delante: list[dict] = []
    for item in candidatos or []:
        caja = item.get("caja")
        if not caja:
            continue
        smin, smax = _rango_s(caja, marco)
        if smax < SALE_CARA_CM:
            continue
        if _fuera_rect(centro_caja(caja), marco) > MARGEN_CARA_CM:
            continue
        if len(marcos) > 1 and dueno_muro(caja, marcos) != propia:
            continue
        (nivel1 if smin <= CONTACTO_CARA_CM else delante).append(item)
    dentro = list(nivel1)
    for _ in range(_RONDAS_MONTAJE):
        nuevas = [p for p in delante if any(cajas_cerca(b["caja"], p["caja"], holgura=MONTAJE_CM) for b in dentro)]
        if not nuevas:
            break
        ids = {id(p) for p in nuevas}
        delante = [p for p in delante if id(p) not in ids]
        dentro.extend(nuevas)
    return dentro


def clasificar_placas(placas: list[dict], frente, arriba) -> dict[str, dict]:
    """Asigna placas grandes a Segmento_1..4, Base y Top_Cover."""
    frente_n = _aplanar(frente, arriba)
    arriba_n = _norm(arriba)
    if frente_n is None or arriba_n is None or not placas:
        return {}
    izquierda = _norm(_cross(frente_n, arriba_n))
    if izquierda is None:
        return {}
    derecha = _scale(izquierda, -1.0)

    muros, tapas = [], []
    for placa in placas:
        normal = _norm(tuple(placa["normal"]))
        if normal is None:
            continue
        vertical = abs(_dot(normal, arriba_n))
        if vertical >= 1.0 - UMBRAL_HORIZONTAL:
            tapas.append(placa)
        elif vertical <= UMBRAL_HORIZONTAL:
            muros.append(placa)
    if not muros:
        return {}

    area_max = max(float(item["area"]) for item in muros)
    grandes = [item for item in muros if float(item["area"]) >= area_max * 0.18]
    if len(grandes) < 4:
        grandes = sorted(muros, key=lambda item: float(item["area"]), reverse=True)[:6]

    def mejor(eje, signo):
        orden = sorted(
            grandes,
            key=lambda item: signo * _dot(_norm(tuple(item["normal"])) or (0, 0, 0), eje),
            reverse=True,
        )
        if not orden:
            return None
        ganador = orden[0]
        normal = _norm(tuple(ganador["normal"])) or (0, 0, 0)
        if signo * _dot(normal, eje) < UMBRAL_ALINEACION:
            return None
        return ganador

    roles: dict[str, dict] = {}
    frente_placa = mejor(frente_n, 1.0)
    if frente_placa is None:
        return roles
    roles["Segmento_1"] = frente_placa
    usados = {id(frente_placa)}
    atras = [
        item
        for item in grandes
        if id(item) not in usados
        and _dot(_norm(tuple(item["normal"])) or (0, 0, 0), frente_n) < -UMBRAL_ALINEACION
    ]
    if atras:
        centro_1 = tuple(frente_placa["centro"])
        atras.sort(key=lambda item: _dot(_sub(tuple(item["centro"]), centro_1), frente_n))
        roles["Segmento_3"] = atras[0]
        usados.add(id(atras[0]))

    lateral = [item for item in grandes if id(item) not in usados]
    derecha_placa = izquierda_placa = None
    mejor_der = mejor_izq = -1.0
    for item in lateral:
        normal = _norm(tuple(item["normal"])) or (0, 0, 0)
        izq, der = _dot(normal, izquierda), _dot(normal, derecha)
        if der > mejor_der:
            mejor_der, derecha_placa = der, item
        if izq > mejor_izq:
            mejor_izq, izquierda_placa = izq, item
    if izquierda_placa is not None and mejor_izq >= UMBRAL_ALINEACION:
        roles["Segmento_2"] = izquierda_placa
    if (
        derecha_placa is not None
        and derecha_placa is not izquierda_placa
        and mejor_der >= UMBRAL_ALINEACION
    ):
        roles["Segmento_4"] = derecha_placa

    if "Segmento_1" in roles and "Segmento_2" in roles and "Segmento_4" in roles:
        caja_1 = roles["Segmento_1"]["caja"]
        if not (
            cajas_cerca(caja_1, roles["Segmento_2"]["caja"])
            and cajas_cerca(caja_1, roles["Segmento_4"]["caja"])
        ):
            roles.pop("Segmento_2", None)
            roles.pop("Segmento_4", None)
    if "Segmento_3" in roles and "Segmento_2" in roles and "Segmento_4" in roles:
        caja_3 = roles["Segmento_3"]["caja"]
        if not (
            cajas_cerca(caja_3, roles["Segmento_2"]["caja"])
            and cajas_cerca(caja_3, roles["Segmento_4"]["caja"])
        ):
            roles.pop("Segmento_3", None)

    if tapas:
        area_tapa = max(float(item["area"]) for item in tapas)
        candidatas = [item for item in tapas if float(item["area"]) >= area_tapa * 0.25]
        candidatas.sort(key=lambda item: _dot(tuple(item["centro"]), arriba_n))
        if candidatas:
            roles["Base"] = candidatas[0]
            if len(candidatas) > 1 and candidatas[-1] is not candidatas[0]:
                roles["Top_Cover"] = candidatas[-1]
    return roles


def token_de_miembro(miembro: dict | str) -> str:
    if isinstance(miembro, dict):
        bruto = str(miembro.get("ruta_archivo") or miembro.get("nombre_ocurrencia") or "")
    else:
        bruto = str(miembro or "")
    texto = bruto.strip().strip('"')
    if re.search(r"[\\/]", texto) or re.match(r"^[A-Za-z]:", texto):
        texto = Path(texto).name
    stem = Path(texto.split(":", 1)[0]).stem
    stem = _PREFIJO_JOB.sub("", stem)
    return re.sub(r"[^a-z0-9]+", "_", stem.casefold()).strip("_")


def ruta_aprendizaje() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    raiz = Path(local) / "VisorPlanos" / "aprendizaje" if local else Path.home() / ".visor_planos" / "aprendizaje"
    return raiz / "roles.json"


def ruta_aprendizaje_proyecto() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "aprendizaje_roles.json"


def _leer_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        datos = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return datos if isinstance(datos, dict) else {}


def _merge_listas(a, b) -> list:
    out = []
    for item in list(a or []) + list(b or []):
        text = str(item or "")
        if text and text not in out:
            out.append(text)
    return out


def _merge_aprendizaje(base: dict, extra: dict) -> dict:
    out = dict(base or {})
    for clave, valor in (extra or {}).items():
        if clave == "ensambles" and isinstance(valor, dict):
            ens = dict(out.get("ensambles") or {}) if isinstance(out.get("ensambles"), dict) else {}
            ens.update(valor)
            out["ensambles"] = ens
            continue
        if isinstance(valor, dict) and isinstance(out.get(clave), dict):
            bucket = dict(out[clave])
            for rol, info in valor.items():
                if not isinstance(info, dict):
                    bucket[rol] = info
                    continue
                prev = bucket.get(rol) if isinstance(bucket.get(rol), dict) else {}
                bucket[rol] = {
                    "incluir": _merge_listas(prev.get("incluir"), info.get("incluir")),
                    "excluir": _merge_listas(prev.get("excluir"), info.get("excluir")),
                }
            out[clave] = bucket
        else:
            out[clave] = valor
    return out


def cargar_aprendizaje() -> dict:
    return _merge_aprendizaje(_leer_json(ruta_aprendizaje()), _leer_json(ruta_aprendizaje_proyecto()))


def guardar_aprendizaje(datos: dict) -> Path:
    texto = json.dumps(datos, indent=2, ensure_ascii=False) + "\n"
    written = None
    for path in (ruta_aprendizaje_proyecto(), ruta_aprendizaje()):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(texto, encoding="utf-8")
            written = path
        except OSError:
            continue
    return written or ruta_aprendizaje_proyecto()


def foto_bolsas(bolsas: dict, roles=None) -> dict[str, list[str]]:
    foto = {}
    for rol in roles or ROLES_MURO:
        tokens = []
        for miembro in bolsas.get(rol) or []:
            if not isinstance(miembro, dict):
                continue
            token = token_de_miembro(miembro)
            if len(token) < 3 or token in tokens:
                continue
            tokens.append(token)
        foto[rol] = tokens
    return foto


def registrar_sesion(producto: str, bolsas: dict, propuesto: dict, solo_rol=None, reemplazar=False):
    roles = [solo_rol] if solo_rol else [rol for rol in ROLES_PUBLICAR if rol in bolsas]
    if not roles:
        return None
    actual = foto_bolsas(bolsas, roles)
    if not any(actual.values()) and not any(propuesto.get(rol) for rol in roles):
        return None
    datos = cargar_aprendizaje()
    bucket = datos.setdefault(producto.casefold() or "default", {})
    if not isinstance(bucket, dict):
        bucket = {}
        datos[producto.casefold() or "default"] = bucket
    for rol in roles:
        info = bucket.get(rol) if isinstance(bucket.get(rol), dict) else {}
        incluir = [] if reemplazar else [str(x) for x in info.get("incluir") or [] if str(x)]
        excluir = [] if reemplazar else [str(x) for x in info.get("excluir") or [] if str(x)]
        quedaron = set(actual.get(rol) or [])
        estaban = set(propuesto.get(rol) or [])
        for token in quedaron:
            if token not in incluir:
                incluir.append(token)
            if token in excluir:
                excluir.remove(token)
        for token in estaban - quedaron:
            if token not in excluir:
                excluir.append(token)
            if token in incluir:
                incluir.remove(token)
        bucket[rol] = {"incluir": incluir, "excluir": excluir}
    return guardar_aprendizaje(datos)


def registrar_token(producto: str, rol: str, token: str, incluir: bool) -> Path | None:
    token = str(token or "").strip()
    if len(token) < 3 or not rol:
        return None
    datos = cargar_aprendizaje()
    bucket = datos.setdefault(str(producto or "tank").casefold() or "default", {})
    if not isinstance(bucket, dict):
        bucket = {}
        datos[str(producto or "tank").casefold() or "default"] = bucket
    info = bucket.get(rol) if isinstance(bucket.get(rol), dict) else {}
    incluir_l = [str(x) for x in info.get("incluir") or [] if str(x)]
    excluir_l = [str(x) for x in info.get("excluir") or [] if str(x)]
    if incluir:
        if token not in incluir_l:
            incluir_l.append(token)
        if token in excluir_l:
            excluir_l.remove(token)
        shared = [str(x) for x in bucket.get("tipos_compartidos") or [] if str(x)]
        if token not in shared:
            shared.append(token)
        bucket["tipos_compartidos"] = shared
    else:
        if token not in excluir_l:
            excluir_l.append(token)
        if token in incluir_l:
            incluir_l.remove(token)
    bucket[rol] = {"incluir": incluir_l, "excluir": excluir_l}
    return guardar_aprendizaje(datos)


def clave_ensamble(ruta: str) -> str:
    stem = Path(str(ruta or "")).stem
    return re.sub(r"[^a-z0-9]+", "_", stem.casefold()).strip("_")


def registrar_foto_ensamble(ruta_iam: str, bags_cara: dict) -> Path | None:
    clave = clave_ensamble(ruta_iam)
    if not clave:
        return None
    datos = cargar_aprendizaje()
    ens = datos.setdefault("ensambles", {})
    if not isinstance(ens, dict):
        ens = {}
        datos["ensambles"] = ens
    publico = {}
    for cara, miembros in (bags_cara or {}).items():
        filas = []
        for miembro in miembros or []:
            if not isinstance(miembro, dict):
                continue
            filas.append(
                {
                    "nombre_ocurrencia": miembro.get("nombre_ocurrencia"),
                    "ruta_archivo": miembro.get("ruta_archivo"),
                    "ruta_ocurrencia": miembro.get("ruta_ocurrencia"),
                    "placa_rol": bool(miembro.get("placa_rol")),
                    "sugerido": bool(miembro.get("sugerido", False)),
                }
            )
        if filas:
            publico[str(cara).upper()] = filas
    ens[clave] = {"assembly": ruta_iam, "bags": publico}
    return guardar_aprendizaje(datos)


def bags_ensamble(ruta_iam: str) -> dict:
    datos = cargar_aprendizaje()
    ens = datos.get("ensambles") if isinstance(datos.get("ensambles"), dict) else {}
    hit = ens.get(clave_ensamble(ruta_iam)) if isinstance(ens, dict) else None
    bags = hit.get("bags") if isinstance(hit, dict) else {}
    return bags if isinstance(bags, dict) else {}


def _miembro_de_pieza(pieza: dict, placa_rol: bool = False) -> dict:
    return {
        "nombre_ocurrencia": pieza.get("nombre_ocurrencia"),
        "ruta_archivo": pieza.get("ruta_archivo"),
        "placa_rol": bool(pieza.get("placa_rol") or placa_rol),
        "sugerido": True,
        "occ": pieza.get("occ"),
        "caja": pieza.get("caja"),
        "centro": pieza.get("centro"),
        "area": pieza.get("area"),
        "normal": pieza.get("normal"),
    }


def _path_miembro(miembro: dict) -> str:
    return str(miembro.get("ruta_archivo") or "").replace("\\", "/").lower()


def _instancia_id(miembro: dict) -> str:
    path = _path_miembro(miembro)
    c = miembro.get("centro")
    try:
        if isinstance(c, (list, tuple)) and len(c) >= 3:
            return f"{path}|{float(c[0]):.2f}|{float(c[1]):.2f}|{float(c[2]):.2f}"
    except (TypeError, ValueError):
        pass
    return f"{path}|{miembro.get('nombre_ocurrencia') or ''}"


def tokens_compartidos(producto: str) -> set[str]:
    """Tipos que el usuario ya usó en algún muro: pueden repetirse en otros."""
    memoria = cargar_aprendizaje().get(str(producto or "tank").casefold() or "default")
    out: set[str] = set()
    if not isinstance(memoria, dict):
        return out
    extra = memoria.get("tipos_compartidos")
    if isinstance(extra, list):
        out.update(str(x) for x in extra if str(x))
    for clave, info in memoria.items():
        if clave in {"tipos_compartidos"} or not isinstance(info, dict):
            continue
        out.update(str(x) for x in (info.get("incluir") or []) if str(x))
    return out


def aplicar_inclusiones(producto: str, bolsas: dict, piezas: list, en_contacto=None, exigir_contacto=True) -> int:
    memoria = cargar_aprendizaje().get(str(producto or "tank").casefold() or "default")
    if not isinstance(memoria, dict):
        return 0
    por_token: dict[str, list] = {}
    for pieza in piezas or []:
        token = token_de_miembro(pieza)
        if len(token) < 3:
            continue
        por_token.setdefault(token, []).append(pieza)
    reclamado = {_instancia_id(m) for bolsa in bolsas.values() for m in (bolsa or []) if _instancia_id(m)}
    shared = tokens_compartidos(producto)
    added = 0
    for rol, bolsa in list(bolsas.items()):
        info = memoria.get(rol) if isinstance(memoria.get(rol), dict) else {}
        excluir = {str(x) for x in (info.get("excluir") or []) if str(x)}
        placa = next((m for m in (bolsa or []) if m.get("placa_rol")), (bolsa or [None])[0])
        wanted = [str(x) for x in (info.get("incluir") or []) if str(x)]
        for token in shared:
            if token not in wanted:
                wanted.append(token)
        for token in wanted:
            token = str(token or "")
            if len(token) < 3 or token in excluir:
                continue
            for pieza in por_token.get(token) or []:
                path = _path_miembro(pieza)
                inst = _instancia_id(pieza)
                if not path or inst in reclamado:
                    continue
                if exigir_contacto and callable(en_contacto) and placa is not None:
                    try:
                        if not en_contacto(placa, pieza):
                            continue
                    except Exception:
                        continue
                bolsa.append(_miembro_de_pieza(pieza, bool(pieza.get("placa_rol"))))
                reclamado.add(inst)
                added += 1
        bolsas[rol] = bolsa
    return added


def aplicar_foto_ensamble(ruta_iam: str, bolsas_rol: dict, piezas: list) -> int:
    foto = bags_ensamble(ruta_iam)
    if not foto:
        return 0
    por_path: dict[str, list] = {}
    for p in piezas or []:
        path = _path_miembro(p)
        if path:
            por_path.setdefault(path, []).append(p)
    reclamado = {_instancia_id(m) for bolsa in bolsas_rol.values() for m in (bolsa or []) if _instancia_id(m)}
    added = 0
    for cara, miembros in foto.items():
        rol = next((k for k, v in CARA_DE_ROL.items() if v == str(cara).upper()), None)
        if not rol:
            continue
        bolsa = bolsas_rol.setdefault(rol, [])
        for miembro in miembros or []:
            if not isinstance(miembro, dict):
                continue
            path = _path_miembro(miembro)
            if not path or path in reclamado:
                continue
            pieza = por_path.get(path)
            if not pieza:
                continue
            bolsa.append(_miembro_de_pieza(pieza, bool(miembro.get("placa_rol") or pieza.get("placa_rol"))))
            reclamado.add(path)
            added += 1
        bolsas_rol[rol] = bolsa
    return added


def aplicar_exclusiones(producto: str, bolsas: dict) -> list[str]:
    memoria = cargar_aprendizaje().get(producto.casefold() or "default")
    if not isinstance(memoria, dict):
        return []
    notas = []
    for rol, bolsa in list(bolsas.items()):
        info = memoria.get(rol) if isinstance(memoria.get(rol), dict) else {}
        excluir = set(info.get("excluir") or [])
        if not excluir:
            continue
        antes = len(bolsa)
        bolsas[rol] = [
            m
            for m in bolsa
            if not isinstance(m, dict) or m.get("placa_rol") or token_de_miembro(m) not in excluir
        ]
        if len(bolsas[rol]) != antes:
            notas.append(f"{rol}: se omitieron piezas que quitaste antes")
    return notas
