"""Nomenclatura de soldadura: clasificación y símbolo ISO de filete por cordón.

Misma regla que Classify Weld de Cotas de Soldadura, sin el add-in. La tabla se
guarda por ensamble en config/weld_nomenclatura.json y la usan las cotas JPG.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVO = ROOT / "config" / "weld_nomenclatura.json"
APRENDIZAJE = ROOT / "config" / "weld_aprendizaje.json"
PRIORIDAD = ROOT / "config" / "weld_prioridad.txt"

HERMETICO = "hermetico"
ACCESORIO = "accesorio"
TAMANOS = ["3", "5", "6", "8"]
PASOS = ["", "10-60", "100-300"]
PRESETS = [
    "FILLET 3 mm 2SIDES TYP",
    "FILLET 5 mm 2SIDES",
    "FILLET 6 mm TYP",
    "FILLET 8 mm TYP",
    "FILLET 6/8 mm 100-300",
    "FILLET 6 mm 2SIDES 100-300",
    "FILLET 3 mm 2SIDES 10-60",
]
_PREFIJO_OCC = "WELD_ANOTATION"
_CUERPO = 67119008
_CUERPO_PIEZA = 67118896
_CARA = 67119408
_CARA_PROXY = 67119520
_OCURRENCIA = 67113776
_PRIORIDAD_CUERPO = 67593
_FILTRO_CARA = 15877


def clave(ruta: str) -> str:
    return str(ruta or "").replace("\\", "/").strip().lower()


def _numero(valor) -> float:
    try:
        return float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def _corto(valor: float) -> str:
    texto = f"{valor:.2f}".rstrip("0").rstrip(".")
    return texto or "0"


def weld_publicado(weld: dict, spec: dict | None) -> dict:
    """El símbolo de la hoja usa lo que el usuario fijó en nomenclatura."""
    salida = dict(weld or {})
    if not spec:
        return salida
    flecha = _numero(spec.get("flecha")) or 6.0
    dos = bool(spec.get("dos_lados"))
    otro = _numero(spec.get("otro")) if dos else 0.0
    if dos and otro <= 0:
        otro = flecha
    salida["leg"] = _corto(flecha)
    salida["other"] = _corto(otro) if dos else ""
    salida["sides"] = 2 if dos else 1
    salida["typ"] = bool(spec.get("typ"))
    paso = str(spec.get("paso") or "")
    salida["pitch"] = paso if paso in PASOS else ""
    return salida


def spec_de_weld(weld: dict) -> dict:
    """Del símbolo de taller que trae la junta (leg, other, pitch, sides, typ)."""
    weld = weld or {}
    flecha = _numero(weld.get("leg")) or 6.0
    dos = int(_numero(weld.get("sides")) or 1) >= 2
    otro = _numero(weld.get("other")) if dos else 0.0
    if dos and otro <= 0:
        otro = flecha
    paso = str(weld.get("pitch") or "").strip()
    return {
        "flecha": flecha,
        "otro": otro,
        "dos_lados": dos,
        "typ": bool(weld.get("typ")),
        "paso": paso if paso in PASOS else "",
    }


def formato(spec: dict) -> str:
    flecha = _numero(spec.get("flecha")) or 6.0
    dos = bool(spec.get("dos_lados"))
    otro = _numero(spec.get("otro")) if dos else 0.0
    if dos and otro <= 0:
        otro = flecha
    if dos and abs(otro - flecha) > 0.05:
        texto = f"FILLET {_corto(flecha)}/{_corto(otro)} mm"
    elif dos:
        texto = f"FILLET {_corto(flecha)} mm 2SIDES"
    else:
        texto = f"FILLET {_corto(flecha)} mm"
    paso = str(spec.get("paso") or "")
    if paso:
        texto += f" {paso}"
    if spec.get("typ"):
        texto += " TYP"
    return texto


def leer_texto(texto: str) -> dict:
    """Preset o texto libre a spec. Igual que WeldSymbolSpec.TryParse."""
    crudo = str(texto or "").strip().upper()
    spec = {"flecha": 6.0, "otro": 0.0, "dos_lados": False, "typ": "TYP" in crudo, "paso": ""}
    if not crudo:
        return spec
    spec["dos_lados"] = "2SIDE" in crudo or "2 SIDE" in crudo
    paso = re.search(r"(\d+(?:[.,]\d+)?)\s*-\s*(\d+(?:[.,]\d+)?)", crudo)
    if paso:
        spec["paso"] = f"{_corto(_numero(paso.group(1)))}-{_corto(_numero(paso.group(2)))}"
        crudo = crudo.replace(paso.group(0), " ")
    desigual = re.search(r"(\d+(?:[.,]\d+)?)\s*/\s*(\d+(?:[.,]\d+)?)", crudo)
    if desigual:
        spec["flecha"] = _numero(desigual.group(1))
        spec["otro"] = _numero(desigual.group(2))
        spec["dos_lados"] = True
        return spec
    tamano = re.search(r"(\d+(?:[.,]\d+)?)", crudo)
    if tamano:
        spec["flecha"] = _numero(tamano.group(1)) or 6.0
    if spec["dos_lados"]:
        spec["otro"] = spec["flecha"]
    return spec


def _leer() -> dict:
    try:
        datos = json.loads(ARCHIVO.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        datos = {}
    if not isinstance(datos, dict) or not isinstance(datos.get("assemblies"), dict):
        datos = {"assemblies": {}}
    return datos


def _escribir(datos: dict) -> None:
    ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVO.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def _token_union(ident: str, titulo: str, kind: str) -> str:
    """Pieza de un accesorio. El par de muros hermético se recuerda por su id, no por un token corto."""
    if kind == HERMETICO:
        return ""
    crudo = str(titulo or "")
    if " / " in crudo:
        crudo = crudo.split(" / ", 1)[1]
    else:
        crudo = str(ident or "").split("_", 1)[-1]
    crudo = re.sub(r":\d+$", "", crudo)
    return re.sub(r"[^a-z0-9]+", "", crudo.casefold())


def _leer_aprendizaje() -> dict:
    try:
        datos = json.loads(APRENDIZAJE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        datos = {}
    if not isinstance(datos, dict):
        datos = {}
    datos.setdefault("uniones", [])
    datos.setdefault("tokens", [])
    return datos


def _guardar_aprendizaje(datos: dict) -> None:
    APRENDIZAJE.parent.mkdir(parents=True, exist_ok=True)
    APRENDIZAJE.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def _ids_vetados(ensamble: dict | None) -> set[str]:
    ids = {str(item) for item in (ensamble or {}).get("excluidos") or [] if str(item)}
    for item in _leer_aprendizaje().get("uniones") or []:
        if str(item):
            ids.add(str(item))
    return ids


def _tokens_vetados() -> set[str]:
    return {str(item) for item in _leer_aprendizaje().get("tokens") or [] if len(str(item)) >= 4}


def junta_vetada(junta: dict, ensamble: dict | None = None) -> bool:
    ident = str((junta or {}).get("id") or "")
    if ident and ident in _ids_vetados(ensamble):
        return True
    if str((junta or {}).get("kind") or "") == HERMETICO:
        return False
    token = _token_union(ident, str((junta or {}).get("title") or ""), ACCESORIO)
    return len(token) >= 4 and token in _tokens_vetados()


def filtrar_juntas(ruta: str, juntas: list[dict]) -> list[dict]:
    _datos, ensamble = _buscar(ruta)
    return [junta for junta in juntas if not junta_vetada(junta, ensamble)]


def excluir(ruta: str, ident: str) -> dict:
    """Quita el cordón de la tabla y recuerda la unión para el siguiente pase."""
    datos, ensamble = _buscar(ruta)
    if ensamble is None:
        datos, ensamble = _entrada(ruta, datos)
    ident = str(ident or "")
    fila = next((item for item in ensamble["cordones"] if str(item.get("id")) == ident), None)
    if fila is None:
        return {"ok": False, "message": f"No encontré el cordón {ident}.", "cuerpos": []}
    cuerpos = [str(nombre) for nombre in fila.get("cuerpos") or [] if str(nombre)]
    ensamble["cordones"] = [item for item in ensamble["cordones"] if str(item.get("id")) != ident]
    vetados = [str(item) for item in ensamble.get("excluidos") or [] if str(item)]
    if ident and ident not in vetados:
        vetados.append(ident)
    ensamble["excluidos"] = vetados
    ensamble["assembly"] = ensamble.get("assembly") or ruta
    _escribir(datos)
    memoria = _leer_aprendizaje()
    uniones = [str(item) for item in memoria.get("uniones") or [] if str(item)]
    if ident and ident not in uniones:
        uniones.append(ident)
    tokens = [str(item) for item in memoria.get("tokens") or [] if str(item)]
    token = _token_union(ident, str(fila.get("titulo") or ""), str(fila.get("clasificacion_auto") or fila.get("clasificacion") or ""))
    if len(token) >= 4 and token not in tokens:
        tokens.append(token)
    memoria["uniones"] = uniones
    memoria["tokens"] = tokens
    _guardar_aprendizaje(memoria)
    resultado = listar(ruta)
    resultado["ok"] = True
    resultado["cuerpos"] = cuerpos
    resultado["message"] = f"{fila.get('titulo') or ident} quedó fuera. El siguiente pase no lo vuelve a proponer."
    return resultado


def _entrada(ruta: str, datos: dict | None = None) -> tuple[dict, dict]:
    datos = datos if datos is not None else _leer()
    ensamble = datos["assemblies"].setdefault(clave(ruta), {"assembly": ruta, "cordones": []})
    if not isinstance(ensamble.get("cordones"), list):
        ensamble["cordones"] = []
    return datos, ensamble


def _buscar(ruta: str, datos: dict | None = None) -> tuple[dict, dict | None]:
    """La tabla se guarda con la ruta de Inventor; el módulo puede traer otra carpeta del mismo .iam."""
    datos = datos if datos is not None else _leer()
    exacta = clave(ruta)
    directa = datos["assemblies"].get(exacta)
    if isinstance(directa, dict) and directa.get("cordones"):
        if not isinstance(directa.get("cordones"), list):
            directa["cordones"] = []
        return datos, directa
    nombre = Path(ruta).name.lower()
    if nombre:
        candidatas = [
            item
            for key, item in datos["assemblies"].items()
            if isinstance(item, dict)
            and Path(str(item.get("assembly") or key)).name.lower() == nombre
            and item.get("cordones")
        ]
        if candidatas:
            hallado = candidatas[0]
            if not isinstance(hallado.get("cordones"), list):
                hallado["cordones"] = []
            return datos, hallado
    if isinstance(directa, dict):
        if not isinstance(directa.get("cordones"), list):
            directa["cordones"] = []
        return datos, directa
    return datos, None


def guardar_manifiesto(ruta: str, juntas: list[dict], cuerpos: dict[str, list[str]]) -> int:
    """Tras generar los filetes: un renglón por junta con cuerpo. Lo editado a mano se conserva."""
    datos, ensamble = _buscar(ruta)
    if ensamble is None:
        datos, ensamble = _entrada(ruta, datos)
    previos = {str(item.get("id")): item for item in ensamble["cordones"] if isinstance(item, dict)}
    filas = []
    for junta in juntas:
        ident = str(junta.get("id") or "")
        nombres = cuerpos.get(ident) or []
        if not ident or not nombres:
            continue
        clasificacion = HERMETICO if junta.get("kind") == HERMETICO else ACCESORIO
        auto = spec_de_weld(junta.get("weld") or {})
        fila = {
            "id": ident,
            "titulo": str(junta.get("title") or ident),
            "largo": str((junta.get("weld") or {}).get("length") or ""),
            "clasificacion": clasificacion,
            "clasificacion_auto": clasificacion,
            "spec": auto,
            "spec_auto": auto,
            "texto": formato(auto),
            "cuerpos": list(nombres),
            "editado": False,
        }
        if ident in _ids_vetados(ensamble):
            continue
        viejo = previos.get(ident)
        if viejo and viejo.get("editado"):
            fila["clasificacion"] = viejo.get("clasificacion") or clasificacion
            fila["spec"] = viejo.get("spec") or auto
            fila["texto"] = formato(fila["spec"])
            fila["editado"] = True
        filas.append(fila)
    ensamble["assembly"] = ruta
    ensamble["cordones"] = filas
    ensamble["excluidos"] = list(_ids_vetados(ensamble))
    _escribir(datos)
    return len(filas)


def clasificaciones(ruta: str) -> dict[str, str]:
    """Lo que el usuario fijó a mano. El siguiente pase pinta con eso."""
    _datos, ensamble = _buscar(ruta)
    if ensamble is None:
        return {}
    return {
        str(item.get("id")): str(item.get("clasificacion"))
        for item in ensamble["cordones"]
        if isinstance(item, dict) and item.get("editado") and item.get("clasificacion") in {HERMETICO, ACCESORIO}
    }


def listar(ruta: str) -> dict:
    _datos, ensamble = _buscar(ruta)
    filas = [item for item in (ensamble or {}).get("cordones") or [] if isinstance(item, dict)]
    pendientes = sum(1 for item in filas if not item.get("editado"))
    omitidos = len(_ids_vetados(ensamble))
    if filas:
        mensaje = f"{len(filas)} cordones. Revisados: {len(filas) - pendientes}."
        if omitidos:
            mensaje += f" Memoria: {omitidos} unión(es) que no se vuelven a proponer."
    else:
        mensaje = "Genera los cordones 3D para llenar la tabla."
        if omitidos:
            mensaje = f"Sin cordones en la tabla. Memoria: {omitidos} unión(es) que no se vuelven a proponer."
    return {
        "ok": True,
        "message": mensaje,
        "assembly": ruta,
        "cordones": filas,
        "presets": PRESETS,
        "sizes": TAMANOS,
        "pitches": PASOS,
    }


def aplicar(ruta: str, ident: str, clasificacion: str, spec: dict) -> tuple[dict, dict | None]:
    datos, ensamble = _buscar(ruta)
    if ensamble is None:
        return {"ok": False, "message": "Genera los cordones 3D para llenar la tabla."}, None
    fila = next((item for item in ensamble["cordones"] if str(item.get("id")) == str(ident)), None)
    if fila is None:
        return {"ok": False, "message": f"No encontré el cordón {ident}."}, None
    if clasificacion not in {HERMETICO, ACCESORIO}:
        return {"ok": False, "message": "Elige Hermético o Accesorio antes de aplicar."}, None
    limpio = {
        "flecha": _numero(spec.get("flecha")) or 6.0,
        "otro": _numero(spec.get("otro")),
        "dos_lados": bool(spec.get("dos_lados")),
        "typ": bool(spec.get("typ")),
        "paso": str(spec.get("paso") or "") if str(spec.get("paso") or "") in PASOS else "",
    }
    anterior = fila.get("clasificacion")
    fila["clasificacion"] = clasificacion
    fila["spec"] = limpio
    fila["texto"] = formato(limpio)
    fila["editado"] = True
    _escribir(datos)
    resultado = listar(ruta)
    resultado["message"] = f"{fila['titulo']}: {fila['texto']}"
    cambio = fila if anterior != clasificacion else None
    return resultado, cambio


def run_inventor(payload: dict) -> dict:
    """Acciones que tocan Inventor: iluminar un cordón, leer el que eligió el usuario, repintar."""
    from inventor_session import _active_assembly, _full_name, _inventor

    accion = str(payload.get("action") or "").lower()
    inv = _inventor()
    assembly = _active_assembly(inv)
    if assembly is None:
        return {"ok": False, "message": "Abre el ensamble del tanque en Inventor."}
    ruta = _full_name(assembly)
    cuerpos = _cuerpos_de_soldadura(assembly)
    if not cuerpos:
        return {"ok": False, "message": "No hay cordones 3D en el ensamble. Genera los cordones primero."}
    if accion == "armar":
        _activar_cuerpo(inv)
        return {"ok": True, "message": "Clic en un filete: se elige ese cordón."}
    if accion == "soltar":
        _restaurar_prioridad(inv)
        return {"ok": True, "message": "Selección de Inventor restaurada."}
    if accion == "mira":
        _activar_cuerpo(inv)
        return _mira(assembly, ruta)
    if accion == "select":
        _activar_cuerpo(inv)
        nombres = [str(nombre) for nombre in payload.get("cuerpos") or []]
        return _iluminar(inv, assembly, cuerpos, nombres)
    if accion == "pick":
        return _elegido(inv, assembly, ruta)
    if accion == "drop":
        return _borrar_cuerpos(assembly, [str(nombre) for nombre in payload.get("cuerpos") or []])
    if accion == "color":
        nombres = [str(nombre) for nombre in payload.get("cuerpos") or []]
        return _repintar(inv, assembly, cuerpos, nombres, str(payload.get("clasificacion") or ""))
    return {"ok": False, "message": f"Acción desconocida: {accion}"}


def _cuerpos_de_soldadura(assembly) -> dict[str, object]:
    salida: dict[str, object] = {}
    try:
        ocurrencias = assembly.ComponentDefinition.Occurrences
        total = int(ocurrencias.Count)
    except Exception:
        return salida
    for indice in range(1, total + 1):
        try:
            occ = ocurrencias.Item(indice)
            if not str(occ.Name).startswith(_PREFIJO_OCC):
                continue
            lista = occ.SurfaceBodies
            for posicion in range(1, int(lista.Count) + 1):
                cuerpo = lista.Item(posicion)
                salida[str(cuerpo.Name)] = cuerpo
        except Exception:
            continue
    return salida


def _iluminar(inv, assembly, cuerpos: dict, nombres: list[str]) -> dict:
    _activar_cuerpo(inv)
    pedidos = nombres_de_cordon(nombres, list(cuerpos))
    elegidos = [cuerpos[nombre] for nombre in pedidos if nombre in cuerpos]
    if not elegidos:
        return {"ok": False, "message": "Ese cordón ya no está en el ensamble. Vuelve a generar los cordones."}
    seleccion = assembly.SelectSet
    try:
        seleccion.Clear()
    except Exception:
        pass
    for cuerpo in elegidos:
        try:
            seleccion.Select(cuerpo)
        except Exception:
            continue
    try:
        inv.ActiveView.Update()
    except Exception:
        pass
    return {"ok": True, "message": f"Cordón iluminado en Inventor ({len(elegidos)} filete(s))."}


def nombres_de_cordon(pedidos: list[str], existentes: list[str]) -> list[str]:
    """El filete y su otro lado (_B). No arrastra el resto del mismo color."""
    salida: list[str] = []
    for clave in existentes:
        if any(clave == nombre or clave.startswith(nombre + "_") for nombre in pedidos if nombre):
            salida.append(clave)
    return salida or [nombre for nombre in pedidos if nombre]


def _mira(assembly, ruta: str) -> dict:
    nombres = _cuerpos_sueltos(assembly)
    if len(nombres) != 1:
        return {"ok": True, "message": "", "id": ""}
    _datos, ensamble = _buscar(ruta)
    if ensamble is None:
        return {"ok": True, "message": "", "id": ""}
    fila = _fila_de_cuerpo(ensamble.get("cordones") or [], nombres[0])
    if fila is None:
        return {"ok": True, "message": "", "id": ""}
    return {"ok": True, "message": str(fila.get("titulo") or ""), "id": str(fila.get("id") or "")}


def _activar_cuerpo(inv) -> None:
    """Mientras la nomenclatura está abierta, el clic toma un filete y no la pieza del color."""
    if not PRIORIDAD.exists():
        anterior = _prioridad(inv)
        if anterior is not None and anterior != _PRIORIDAD_CUERPO:
            try:
                PRIORIDAD.write_text(str(anterior), encoding="utf-8")
            except OSError:
                pass
    _poner_prioridad(inv, _PRIORIDAD_CUERPO)


def _restaurar_prioridad(inv) -> None:
    try:
        texto = PRIORIDAD.read_text(encoding="utf-8").strip()
    except OSError:
        return
    try:
        PRIORIDAD.unlink()
    except OSError:
        pass
    if texto:
        _poner_prioridad(inv, texto)


def _elegido(inv, assembly, ruta: str) -> dict:
    anterior = _prioridad(inv)
    try:
        _poner_prioridad(inv, _PRIORIDAD_CUERPO)
        nombres = _cuerpos_sueltos(assembly)
        if len(nombres) != 1:
            try:
                cara = inv.CommandManager.Pick(_FILTRO_CARA, "Clic en un solo cordón, no en el grupo de color")
            except Exception:
                cara = None
            nombre = _nombre_de_cuerpo(cara) if cara is not None else ""
            nombres = [nombre] if nombre else []
    finally:
        if anterior is not None:
            _poner_prioridad(inv, anterior)
    if len(nombres) != 1:
        return {"ok": False, "message": "Clic en un solo filete. El grupo del mismo color no cuenta como un cordón."}
    _datos, ensamble = _buscar(ruta)
    if ensamble is None:
        return {"ok": False, "message": "Genera los cordones 3D para llenar la tabla."}
    fila = _fila_de_cuerpo(ensamble.get("cordones") or [], nombres[0])
    if fila is None:
        return {"ok": False, "message": f"El cuerpo {nombres[0]} no está en la tabla. Vuelve a generar los cordones."}
    _iluminar(inv, assembly, _cuerpos_de_soldadura(assembly), list(fila.get("cuerpos") or []))
    return {"ok": True, "message": f"Cordón elegido: {fila.get('titulo')}", "id": fila.get("id")}


def _fila_de_cuerpo(filas: list, nombre: str) -> dict | None:
    for fila in filas:
        if not isinstance(fila, dict):
            continue
        cuerpos = [str(item) for item in fila.get("cuerpos") or [] if str(item)]
        if nombre in cuerpos or any(nombre.startswith(item + "_") or item.startswith(nombre + "_") for item in cuerpos):
            return fila
    return None


def _cuerpos_sueltos(assembly) -> list[str]:
    """Caras o cuerpos. Una ocurrencia WELD_ANOTATION es el grupo de un color y no se acepta."""
    nombres: list[str] = []
    try:
        seleccion = assembly.SelectSet
        total = int(seleccion.Count)
    except Exception:
        return nombres
    for indice in range(1, total + 1):
        try:
            item = seleccion.Item(indice)
        except Exception:
            continue
        try:
            if int(item.Type) == _OCURRENCIA:
                continue
        except Exception:
            pass
        nombre = _nombre_de_cuerpo(item)
        if nombre and nombre not in nombres:
            nombres.append(nombre)
    return nombres


def _prioridad(inv):
    try:
        return int(inv.SelectionPriority)
    except Exception:
        return None


def _poner_prioridad(inv, valor) -> None:
    try:
        inv.SelectionPriority = int(valor)
    except Exception:
        pass


def _borrar_cuerpos(assembly, nombres: list[str]) -> dict:
    presentes = _cuerpos_de_soldadura(assembly)
    buscados = nombres_de_cordon(nombres, list(presentes))
    if not buscados:
        return {"ok": False, "message": "Ese cordón no tenía sólido en el ensamble."}
    rasgos = []
    documentos = []
    for nombre in buscados:
        cuerpo = presentes.get(nombre)
        if cuerpo is None:
            continue
        nativo = _nativo(cuerpo)
        rasgo = _rasgo_de(nativo) or _rasgo_de(cuerpo)
        if rasgo is not None:
            rasgos.append(rasgo)
        documento = _documento(nativo)
        if documento is not None:
            documentos.append(documento)
    borrados = 0
    errores: list[str] = []
    for rasgo in rasgos:
        try:
            rasgo.Delete(False, False, False)
            borrados += 1
            continue
        except Exception as ex:
            ultimo = ex
        try:
            rasgo.Delete()
            borrados += 1
        except Exception as ex:
            ultimo = ex
            errores.append(str(getattr(ultimo, "excepinfo", None) or ultimo)[:180])
    for documento in documentos:
        try:
            documento.Update2(True)
        except Exception:
            try:
                documento.Update()
            except Exception:
                pass
    try:
        assembly.Update2(True)
    except Exception:
        try:
            assembly.Update()
        except Exception:
            pass
    if borrados == 0:
        detalle = errores[0] if errores else "no encontré la operación del filete"
        return {"ok": False, "message": f"La unión quedó en memoria, pero el sólido sigue: {detalle}"}
    return {"ok": True, "message": f"Sólido borrado ({borrados} filete(s))."}


def _rasgo_de(cuerpo):
    try:
        rasgo = cuerpo.CreatedByFeature
        if rasgo is not None:
            return rasgo
    except Exception:
        pass
    return None


def _nombre_de_cuerpo(item) -> str:
    try:
        tipo = int(item.Type)
    except Exception:
        tipo = 0
    candidatos = []
    if tipo == _CUERPO:
        candidatos.append(item)
    for atributo in ("SurfaceBody", "Parent"):
        try:
            candidatos.append(getattr(item, atributo))
        except Exception:
            continue
    try:
        candidatos.append(item.Faces.Item(1).SurfaceBody)
    except Exception:
        pass
    for candidato in candidatos:
        try:
            if int(candidato.Type) not in {_CUERPO, _CUERPO_PIEZA}:
                continue
            occ = candidato.ContainingOccurrence
            if occ is not None and not str(occ.Name).startswith(_PREFIJO_OCC):
                continue
            return str(candidato.Name)
        except Exception:
            continue
    return ""


def _repintar(inv, assembly, cuerpos: dict, nombres: list[str], clasificacion: str) -> dict:
    from weld_solido import _AZUL, _NARANJA, _apariencia, _pintar

    hermetico = clasificacion == HERMETICO
    rgb = _AZUL if hermetico else _NARANJA
    nombre = "WeldHermetico" if hermetico else "WeldAccesorio"
    hechos = 0
    for clave_cuerpo in nombres:
        cuerpo = cuerpos.get(clave_cuerpo)
        if cuerpo is None:
            continue
        nativo = _nativo(cuerpo)
        pieza = _documento(nativo) or assembly
        _pintar(nativo, _apariencia(inv, pieza, nombre, rgb))
        _pintar(cuerpo, _apariencia(inv, assembly, nombre, rgb))
        _sin_aspecto_de_ocurrencia(cuerpo)
        hechos += 1
    try:
        inv.ActiveView.Update()
    except Exception:
        pass
    if hechos == 0:
        return {"ok": False, "message": "No pude pintar el cordón."}
    color = "azul" if hermetico else "naranja"
    return {"ok": True, "message": f"Cordón repintado en {color} ({hechos} filete(s)). No guardé el archivo."}


def _nativo(cuerpo):
    try:
        nativo = cuerpo.NativeObject
        if nativo is not None:
            return nativo
    except Exception:
        pass
    return cuerpo


def _documento(cuerpo):
    try:
        return cuerpo.Parent.Document
    except Exception:
        return None


def _sin_aspecto_de_ocurrencia(cuerpo) -> None:
    """El color del filete manda. Un aspecto de la ocurrencia lo deja transparente o del grupo entero."""
    try:
        occ = cuerpo.ContainingOccurrence
    except Exception:
        return
    if occ is None:
        return
    try:
        occ.AppearanceSourceType = 100612
    except Exception:
        pass
