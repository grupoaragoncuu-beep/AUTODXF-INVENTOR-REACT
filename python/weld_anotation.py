"""Weld Anotation: un JPG por cordón, dibujado en Python.

La geometría sale del ensamble abierto. No se abre un plano de Inventor.
El dibujo está en weld_jpg.py.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
AWIS_DIR = Path.home() / "Documents" / "AWIS"
PROGRESS_PATH = ROOT / "config" / "weld_anotation_progress.json"
DRAWING_DOC = 12292
_FACE_PREFIX = "AWIS_FACE_DRAWING_"
_DIMS_PREFIX = "AWIS_WELD_DIMS_"

_started = 0.0


def safe_token(name: str) -> str:
    value = (name or "").strip() or "UNKNOWN_TANK"
    value = re.sub(r"[^\w.\-]+", "_", value, flags=re.UNICODE)
    value = re.sub(r"_+", "_", value).strip("_. ")
    return value or "UNKNOWN_TANK"


def tank_token(payload: dict) -> str:
    for key in ("assemblyPath", "assemblyName", "job"):
        raw = str(payload.get(key) or "").strip()
        if not raw:
            continue
        stem = Path(raw).stem
        if stem:
            return stem
    return "UNKNOWN_TANK"


def tank_from_drawing(path: Path) -> str:
    stem = path.stem
    low = stem.lower()
    for prefix in (_FACE_PREFIX, _DIMS_PREFIX):
        if low.startswith(prefix.lower()):
            return stem[len(prefix) :]
    return stem


def output_folder(local_jpg: str, folder_name: str, create: bool = False) -> Path:
    from acotacion import ensure_dir, local_jpg_dir

    root, _note = local_jpg_dir(local_jpg, create=create)
    dest = root / (safe_token(folder_name) or "SIN_JOB") / "WELD_ANOTATION"
    if create:
        ensure_dir(dest)
    return dest


def carpeta_weld_de(eleccion: dict, job: str) -> Path | None:
    """``JOB\\DOSSIER FILES\\JPGS\\Weld``. Misma carpeta de cotas del job elegido."""
    from dossier_arbol import ruta_jpgs

    datos = eleccion if isinstance(eleccion, dict) else {}
    base = ruta_jpgs(
        str(datos.get("producto") or ""),
        str(datos.get("cliente") or ""),
        str(job or datos.get("job") or ""),
        raiz=str(datos.get("raiz") or ""),
    )
    if not base:
        return None
    return Path(base) / "Weld"


def carpeta_weld(payload: dict, create: bool = False) -> Path:
    from acotacion import ensure_dir
    from dossier_arbol import cargar_eleccion

    eleccion = cargar_eleccion()
    job = str((payload or {}).get("job") or eleccion.get("job") or "").strip()
    destino = carpeta_weld_de(eleccion, job)
    if destino is None:
        raise RuntimeError("Elige el job del dossier. Los JPG van a DOSSIER FILES\\JPGS\\Weld.")
    if create:
        ensure_dir(destino)
    return destino


def resolve_drawing_path(directory: Path, tank: str, kind: str) -> Path | None:
    token = safe_token(tank)
    names: list[str] = []
    if kind == "dims":
        names.append(f"{_DIMS_PREFIX}{token}.dwg")
    else:
        names.extend((f"{_FACE_PREFIX}{token}.dwg", f"{_FACE_PREFIX}{token}.idw"))
    for name in names:
        candidate = directory / name
        if candidate.is_file():
            return candidate
    return None


def find_drawing(payload: dict, kind: str) -> Path | None:
    explicit = str(payload.get("drawingPath") or "").strip()
    if explicit:
        chosen = Path(explicit)
        if chosen.is_file():
            return chosen
    if kind == "open":
        return None
    directories = [Path(str(payload.get("awisDir") or AWIS_DIR))]
    assembly = str(payload.get("assemblyPath") or "").strip()
    if assembly:
        parent = Path(assembly).parent
        if parent not in directories:
            directories.append(parent)
    tank = tank_token(payload)
    for directory in directories:
        found = resolve_drawing_path(directory, tank, kind)
        if found is not None:
            return found
    return None


def sheet_pixel_box(
    img_w: int,
    img_h: int,
    target_x: float,
    target_y: float,
    vis_w: float,
    vis_h: float,
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
) -> tuple[int, int, int, int] | None:
    """Pasa el rectángulo de la hoja (cm, Y arriba) a píxeles (Y abajo)."""
    if vis_w < 1 or vis_h < 1 or img_w < 2 or img_h < 2:
        return None
    if max_x - min_x < 1 or max_y - min_y < 1:
        return None
    vis_min_x = target_x - (vis_w * 0.5)
    vis_max_y = target_y + (vis_h * 0.5)
    x1 = int((min_x - vis_min_x) / vis_w * img_w)
    x2 = int((max_x - vis_min_x) / vis_w * img_w + 0.999)
    y1 = int((vis_max_y - max_y) / vis_h * img_h)
    y2 = int((vis_max_y - min_y) / vis_h * img_h + 0.999)
    x1 = max(0, min(x1, img_w - 1))
    y1 = max(0, min(y1, img_h - 1))
    x2 = max(x1 + 1, min(x2, img_w))
    y2 = max(y1 + 1, min(y2, img_h))
    if (x2 - x1) < img_w * 0.2 or (y2 - y1) < img_h * 0.2:
        return None
    if (x2 - x1) > img_w * 0.96 and (y2 - y1) > img_h * 0.96:
        return None
    return x1, y1, x2, y2


def trim_margin(image: Image.Image, threshold: int = 248, pad: int = 12) -> Image.Image:
    rgb = image.convert("RGB")
    mask = rgb.convert("L").point(lambda pixel: 0 if pixel >= threshold else 255)
    box = mask.getbbox()
    if not box:
        return rgb
    width, height = rgb.size
    x0, y0, x1, y1 = box
    if (x1 - x0) < width * 0.08 or (y1 - y0) < height * 0.08:
        return rgb
    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - pad)
    x1 = min(width, x1 + pad)
    y1 = min(height, y1 + pad)
    if x0 == 0 and y0 == 0 and x1 == width and y1 == height:
        return rgb
    return rgb.crop((x0, y0, x1, y1))


def compose_sheet_jpg(image: Image.Image, crop: tuple[int, int, int, int] | None) -> Image.Image:
    rgb = image.convert("RGB")
    if crop:
        rgb = rgb.crop(crop)
    framed = trim_margin(rgb)
    framed.load()
    return framed


def scan_weld_drawing(payload: dict) -> dict:
    tank = tank_token(payload)
    try:
        folder = str(carpeta_weld(payload if isinstance(payload, dict) else {}))
        message = "Los JPG van a DOSSIER FILES\\JPGS\\Weld del job elegido. Un JPG por cordón."
    except RuntimeError as ex:
        folder = ""
        message = str(ex)
    return {
        "ok": True,
        "kind": "python",
        "tank": tank,
        "drawingPath": "",
        "folder": folder,
        "message": message,
    }


def run_weld_anotation(payload: dict) -> dict:
    data = payload if isinstance(payload, dict) else {}
    reset_weld_progress(0, "Leyendo el ensamble…")
    try:
        return _generar(data)
    except Exception as ex:
        from inventor_session import _short

        message = _short(ex)
        fail = {"ok": False, "message": message, "count": 0, "folder": "", "files": []}
        write_weld_progress(
            current=1,
            total=1,
            piece="Error",
            phase="listo",
            done=True,
            result=fail,
            message=message,
        )
        return fail


def _visibles_de(junta: dict, accesorios: list) -> list:
    """La foto del segmento muestra la placa y todos los accesorios de esa cara.

    El cordón azul también enseña la otra placa. El de al lado no entra.
    """
    visibles = []
    for occ in (junta.get("host"), junta.get("pieza")):
        if occ is not None and occ not in visibles:
            visibles.append(occ)
    if junta.get("kind") == "hermetico" and junta.get("otro") is not None and junta.get("otro") not in visibles:
        visibles.append(junta["otro"])
    cara = str(junta.get("cara") or "")
    for item in accesorios:
        pieza = item.get("occ")
        if pieza is None or str(item.get("cara") or "") != cara or pieza in visibles:
            continue
        visibles.append(pieza)
    return visibles


def _borrar_cordones(assembly, ruta: str) -> dict:
    """Saca los filetes del ensamble y la lista. No calcula cordones nuevos."""
    from weld_nomenclatura import vaciar
    from weld_solido import _quitar_anteriores

    write_weld_progress(current=0, total=1, piece="Borrando cordones…", phase="borrar")
    solidos = _quitar_anteriores(assembly)
    resultado = vaciar(ruta)
    message = str(resultado.get("message") or "Cordones borrados.")
    if int(solidos.get("quedan") or 0) > 0:
        message = f"La lista quedó vacía, pero siguen {solidos['quedan']} sólidos de soldadura en el ensamble."
    result = {"ok": True, "message": message, "count": 0, "folder": "", "files": [], "warnings": []}
    write_weld_progress(current=1, total=1, piece="Listo", phase="listo", done=True, result=result, message=message)
    return result


def _generar(payload: dict) -> dict:
    from inventor_session import _active_assembly, _full_name, _inventor, _occ_key, _short
    from roles_inventor import _clave_iam, _leer_sesiones
    from weld_juntas import armar_juntas, marco_cara, marco_derecho

    inv = _inventor()
    assembly = _active_assembly(inv)
    if assembly is None:
        raise RuntimeError("Abre el ensamble del tanque en Inventor.")
    ruta = _full_name(assembly)
    if str(payload.get("fase") or "").strip().lower() == "borrar":
        return _borrar_cordones(assembly, ruta)
    sesion = _sesion_muros(ruta, _leer_sesiones()["assemblies"], _clave_iam)
    bags = sesion.get("bags") if isinstance(sesion.get("bags"), dict) else {}
    if not bags:
        raise RuntimeError("Confirma los muros en Acotación JPG. Sin esas caras no hay cordón.")
    write_weld_progress(current=0, total=1, piece="Leyendo caras…", phase="geometria")
    indice = _indice_hojas(assembly, _occ_key)
    ensambles = _ensambles_por_raiz(assembly)
    usadas: set[str] = set()
    muros = {}
    accesorios = []
    por_cara: dict[str, list] = {}

    def anotar(occ, cara_id: str, nombre: str, miembro: dict) -> None:
        por_cara.setdefault(cara_id, []).append(occ)
        if miembro.get("placa_rol") and cara_id not in muros:
            cara_geo = _cara_de_ocurrencia(occ, marco_cara, marco_derecho)
            if cara_geo:
                cara_geo["cara"] = cara_id
                cara_geo["occ"] = occ
                muros[cara_id] = cara_geo
            return
        if miembro.get("placa_rol"):
            return
        caja = _caja_mm(occ)
        if caja is None:
            return
        accesorios.append(
            {
                "cara": cara_id,
                "nombre": nombre,
                "centro": caja["centro"],
                "caja": caja["caja"],
                "puntos": caja["puntos"],
                "occ": occ,
            }
        )

    pendientes = []
    for cara, miembros in bags.items():
        cara_id = str(cara).upper()
        for miembro in miembros or []:
            occ = _buscar_ocurrencia(indice, miembro)
            if occ is not None:
                anotar(occ, cara_id, str(miembro.get("nombre_ocurrencia") or cara_id), miembro)
                continue
            if miembro.get("placa_rol"):
                continue
            raiz = _raiz_nombre(str(miembro.get("nombre_ocurrencia") or ""))
            if raiz:
                pendientes.append((cara_id, miembro, raiz))
    from weld_juntas import _largo_de_apoyo

    por_raiz: dict[str, list] = {}
    for cara_id, miembro, raiz in pendientes:
        por_raiz.setdefault(raiz, []).append((cara_id, miembro))
    for raiz, puestos in por_raiz.items():
        for padre in ensambles.get(raiz) or []:
            clave = str(_occ_key(padre) or "").replace("\\", "/").lower()
            if not clave or clave in usadas:
                continue
            mejor = None
            mayor = 0.0
            for cara_id, miembro in puestos:
                muro = muros.get(cara_id)
                if muro is None:
                    continue
                largo = _largo_de_apoyo(padre, muro)
                if largo > mayor:
                    mayor = largo
                    mejor = (cara_id, miembro)
            if mejor is None or mayor < 8.0:
                continue
            usadas.add(clave)
            anotar(padre, mejor[0], clave, mejor[1])
    from weld_nomenclatura import filtrar_juntas

    juntas = filtrar_juntas(ruta, armar_juntas(muros, accesorios, holgura_mm=80.0))
    from weld_nomenclatura import unidad_de_ruta

    if unidad_de_ruta(ruta) == "in":
        from weld_juntas import aplicar_pauta_vantran

        aplicar_pauta_vantran(juntas)
    for junta in juntas:
        junta["visibles"] = _visibles_de(junta, accesorios)
    solo = str(payload.get("only") or "").strip().lower()
    if solo:
        juntas = [junta for junta in juntas if solo in str(junta.get("id") or "").lower() or solo in str(junta.get("title") or "").lower()]
    nombres = [str(nombre).strip().lower() for nombre in (payload.get("nombres") or []) if str(nombre).strip()]
    if nombres:
        juntas = [
            junta
            for junta in juntas
            if any(
                nombre in str(junta.get("id") or "").lower() or nombre in str(junta.get("title") or "").lower()
                for nombre in nombres
            )
        ]
    limite = max(0, int(payload.get("limit") or 0))
    if limite > 0:
        juntas = _muestra_juntas(juntas, limite)
    if not juntas:
        raise RuntimeError("No apareció ningún cordón en los muros confirmados.")
    warnings: list[str] = []
    total = len(juntas)
    from weld_solido import Cordones

    from weld_nomenclatura import clasificaciones, guardar_manifiesto

    fase = str(payload.get("fase") or "").strip().lower()
    solo_fotos = fase == "foto" or str(payload.get("photos") or "").lower() in {"1", "true", "yes", "jpg"}
    write_weld_progress(
        current=0,
        total=total,
        piece="JPG…" if solo_fotos else "Cordones 3D…",
        phase="foto" if solo_fotos else "cordon",
    )
    cordon = Cordones(inv, assembly)
    piezas_gris = 0
    try:
        if solo_fotos:
            hechos = cordon.adoptar(ruta)
            if hechos == 0:
                raise RuntimeError("No hay cordones 3D en el ensamble. Genera los filetes primero.")
        else:
            from weld_solido import descolorear

            piezas_gris = descolorear(inv, assembly)
            hechos = cordon.construir(juntas, clasificaciones(ruta))
    except Exception as ex:
        if not solo_fotos:
            cordon.cerrar()
        raise RuntimeError(f"Cordón 3D: {_short(ex)}") from ex
    if hechos == 0:
        if not solo_fotos:
            cordon.cerrar()
        aviso = cordon.error or "no se pudo crear el filete."
        raise RuntimeError("Cordón 3D: " + aviso)
    if not solo_fotos and not solo:
        try:
            guardar_manifiesto(ruta, juntas, cordon.por_junta)
        except OSError as ex:
            warnings.append(f"No guardé la tabla de nomenclatura: {ex}")
    files: list[str] = []
    dest = ""
    nota_bd = ""
    if solo_fotos:
        pedido = str(payload.get("dest") or "").strip()
        if pedido:
            from acotacion import ensure_dir

            dest_path = ensure_dir(Path(pedido))
        else:
            dest_path = carpeta_weld(payload, create=True)
        dest = str(dest_path)
        completo = limite <= 0 and not nombres and not pedido
        files = _publicar_fotos(
            inv,
            assembly,
            juntas,
            dest_path,
            cordon,
            ruta,
            warnings,
            borrar=completo,
        )
        try:
            from cotas_dossier import alimentar_weld
            from dossier_arbol import cargar_eleccion

            eleccion = cargar_eleccion()
            job = str(payload.get("job") or eleccion.get("job") or "").strip()
            bd = alimentar_weld(dest, job=job, completo=completo)
            nota_bd = " " + str(bd.get("message") or "")
            if not bd.get("ok") and bd.get("message"):
                warnings.append(str(bd["message"]))
        except Exception as ex:
            nota_bd = f" BD: {ex}"
            warnings.append(nota_bd.strip())
    else:
        try:
            dest = str(carpeta_weld(payload))
        except RuntimeError:
            dest = ""
    cordon.encuadrar()
    naranja = cordon.conteo("accesorio")
    azul = cordon.conteo("hermetico")
    extra = f"\nAvisos: {' | '.join(warnings[:8])}" if warnings else ""
    if cordon.error:
        extra = f"\nAvisos: {cordon.error}" + extra
    if solo_fotos:
        message = f"{len(files)} JPG en {dest}. No guardé el archivo.{nota_bd}" + extra
    else:
        message = (
            f"Cordones 3D: {hechos} filetes ({naranja} naranja, {azul} azul). "
            f"Tanque en gris ({piezas_gris} piezas). No guardé el archivo."
            + extra
        )
    result = {
        "ok": True,
        "message": message,
        "count": len(files) or hechos,
        "folder": str(dest),
        "files": files,
        "warnings": warnings,
    }
    write_weld_progress(
        current=total,
        total=total,
        piece="Listo",
        phase="listo",
        photos=len(files),
        done=True,
        result=result,
        message=result["message"],
    )
    return result


def _muestra_juntas(juntas: list[dict], limite: int) -> list[dict]:
    """Una hermética de base, una esquina y un accesorio. Para probar sin esperar todo el set."""
    if limite <= 0 or len(juntas) <= limite:
        return juntas[:limite] if limite else juntas
    elegidas = []
    pruebas = (
        lambda junta: junta.get("kind") == "hermetico" and "BASE" in str(junta.get("title") or ""),
        lambda junta: junta.get("kind") == "hermetico" and "SEGM" in str(junta.get("title") or "") and "BASE" not in str(junta.get("title") or "") and "TOP" not in str(junta.get("title") or ""),
        lambda junta: junta.get("kind") == "accesorio" and str(junta.get("cara") or "").startswith("SEGM"),
        lambda junta: junta.get("kind") == "accesorio",
    )
    for prueba in pruebas:
        hit = next((junta for junta in juntas if prueba(junta) and junta not in elegidas), None)
        if hit is not None:
            elegidas.append(hit)
        if len(elegidas) >= limite:
            return elegidas[:limite]
    for junta in juntas:
        if junta not in elegidas:
            elegidas.append(junta)
        if len(elegidas) >= limite:
            break
    return elegidas[:limite]


def _publicar_fotos(inv, assembly, juntas, dest, cordon, ruta, warnings, borrar: bool = True) -> list[str]:
    """Un JPG por junta: cara, detalle, isométrica y el símbolo de nomenclatura."""
    from weld_jpg import save_weld_jpg
    from weld_nomenclatura import listar, presentar_weld, unidad_de_ruta, weld_publicado
    from weld_vista import VistaSoldadura

    if dest.exists() and borrar:
        _clear_jpgs(dest)
    dest.mkdir(parents=True, exist_ok=True)
    unidad = unidad_de_ruta(ruta)
    tabla = {str(item.get("id")): item for item in listar(ruta).get("cordones") or []}
    vista = VistaSoldadura(inv, assembly, (juntas[0] if juntas else {}).get("centro_tanque"), cordon)
    files: list[str] = []
    usados: set[str] = set()
    try:
        for indice, junta in enumerate(juntas, start=1):
            write_weld_progress(
                current=indice - 1,
                total=len(juntas),
                piece=str(junta.get("title") or junta.get("id") or "cordón"),
                phase="foto",
                photos=len(files),
            )
            try:
                tomas = vista.tomar(junta)
            except Exception as ex:
                warnings.append(f"{junta.get('title')}: {ex}")
                continue
            if tomas is None:
                warnings.append(f"{junta.get('title')}: sin foto.")
                continue
            frente, detalle, iso, ventana = tomas
            fila = tabla.get(str(junta.get("id"))) or {}
            fijado = fila.get("spec") if fila.get("editado") else None
            weld = presentar_weld(weld_publicado(junta.get("weld") or {}, fijado), unidad)
            nombre = safe_token(str(junta.get("title") or junta.get("id") or "CORDON")) or "CORDON"
            archivo = f"{nombre}.jpg"
            extra = 2
            while archivo in usados:
                archivo = f"{nombre}_{extra}.jpg"
                extra += 1
            usados.add(archivo)
            cara_jpg = str(junta.get("cara") or "").upper()
            if cara_jpg not in {"SEGM1", "SEGM2", "SEGM3", "SEGM4", "BASE", "TOP"}:
                cara_jpg = "Weld"
            carpeta = dest / cara_jpg
            carpeta.mkdir(parents=True, exist_ok=True)
            save_weld_jpg(
                carpeta / archivo,
                title=str(junta.get("title") or ""),
                outline=list(junta.get("outline") or []),
                welds=[weld],
                frontal=frente,
                detalle=detalle,
                iso=iso,
                vista=ventana,
            )
            files.append(archivo)
    finally:
        vista.cerrar()
    return files


def _sesion_muros(ruta: str, sesiones: dict, clave) -> dict:
    directa = sesiones.get(clave(ruta))
    if isinstance(directa, dict) and directa.get("bags"):
        return directa
    nombre = Path(ruta).name.lower()
    candidatas = [
        item
        for item in sesiones.values()
        if isinstance(item, dict)
        and Path(str(item.get("assembly") or "")).name.lower() == nombre
        and item.get("bags")
    ]
    confirmadas = [item for item in candidatas if item.get("confirmed")]
    uso = confirmadas or candidatas
    if len(uso) == 1:
        return uso[0]
    return {}


def _indice_hojas(assembly, occ_key) -> dict:
    indice = {}
    leaves = assembly.ComponentDefinition.Occurrences.AllLeafOccurrences
    for index in range(1, int(leaves.Count) + 1):
        try:
            occ = leaves.Item(index)
            if bool(occ.Suppressed):
                continue
        except Exception:
            continue
        clave = str(occ_key(occ) or "").replace("\\", "/").lower()
        if clave:
            indice[clave] = occ
    return indice


def _raiz_nombre(nombre: str) -> str:
    """El nombre pintado y el ensamble que lo reemplazó comparten esta raíz.

    `261080_Tank-Base_Default<As Machined>_21` y
    `261080_Tank-Base_Default_As_Machined_:1` quedan en `261080tankbase`.
    Una pieza hija también cae en la misma raíz, así que el empareje es solo
    contra ensambles.
    """
    texto = str(nombre or "").casefold().replace("<", " ").replace(">", " ")
    texto = re.sub(r":\d+$", "", texto.strip())
    texto = re.sub(r"[_\s]+\d+$", "", texto)
    texto = re.sub(r"[_\s]+", " ", texto)
    for marca in ("as machined", "default"):
        texto = texto.replace(marca, " ")
    return re.sub(r"[^a-z0-9]+", "", texto)


def _es_ensamble(occ) -> bool:
    try:
        return int(occ.DefinitionDocumentType) == 12291
    except Exception:
        return False


def _ensambles_por_raiz(assembly) -> dict[str, list]:
    grupos: dict[str, list] = {}

    def walk(occurrences) -> None:
        try:
            count = int(occurrences.Count)
        except Exception:
            return
        for index in range(1, count + 1):
            try:
                occ = occurrences.Item(index)
                if bool(occ.Suppressed) or not _es_ensamble(occ):
                    continue
                raiz = _raiz_nombre(str(occ.Name))
            except Exception:
                continue
            if raiz:
                grupos.setdefault(raiz, []).append(occ)
            try:
                walk(occ.SubOccurrences)
            except Exception:
                continue

    try:
        walk(assembly.ComponentDefinition.Occurrences)
    except Exception:
        return grupos
    return grupos


def _hojas_del_ensamble(indice: dict, padre, occ_key) -> list:
    prefijo = str(occ_key(padre) or "").replace("\\", "/").lower()
    if not prefijo:
        return []
    prefijo += "/"
    return [occ for clave, occ in indice.items() if str(clave).startswith(prefijo)]


def _buscar_ocurrencia(indice: dict, miembro: dict):
    ruta = str(miembro.get("ruta_ocurrencia") or "").replace("\\", "/").lower()
    if ruta and ruta in indice:
        return indice[ruta]
    nombre = str(miembro.get("nombre_ocurrencia") or "").strip().lower()
    archivo = str(miembro.get("ruta_archivo") or "").replace("\\", "/").lower()
    for clave, occ in indice.items():
        hoja = clave.split("/")[-1]
        if nombre and hoja == nombre and (not archivo or _archivo_occ(occ) == archivo):
            return occ
    return None


def _archivo_occ(occ) -> str:
    try:
        return str(occ.Definition.Document.FullFileName or "").replace("\\", "/").lower()
    except Exception:
        return ""


def _cara_de_ocurrencia(occ, marco_cara, marco_derecho=None):
    """La cara mira de frente a la placa, con sus cantos paralelos a la foto."""
    contorno = _contorno_placa(occ)
    if contorno and marco_derecho is not None:
        normal, puntos, canto = contorno
        marco = marco_derecho(normal, puntos, canto)
        if marco:
            return marco
    caja = _caja_mm(occ)
    if caja is None:
        return None
    minimo, maximo = caja["caja"]
    tramos = [maximo[eje] - minimo[eje] for eje in range(3)]
    fino = tramos.index(min(tramos))
    normal = [0.0, 0.0, 0.0]
    normal[fino] = 1.0
    return marco_cara(tuple(normal), caja["puntos"])


def _contorno_placa(occ):
    """Normal y vértices (mm) de la cara plana más grande, en el ensamble."""
    plano = 5890
    mejor = None
    area = 0.0
    try:
        cuerpos = occ.SurfaceBodies
        n_cuerpos = int(cuerpos.Count)
    except Exception:
        return None
    for bi in range(1, n_cuerpos + 1):
        try:
            caras = cuerpos.Item(bi).Faces
            n_caras = int(caras.Count)
        except Exception:
            continue
        for fi in range(1, n_caras + 1):
            try:
                cara = caras.Item(fi)
                if int(cara.SurfaceType) != plano:
                    continue
                medida = float(cara.Evaluator.Area)
            except Exception:
                continue
            if medida > area:
                area = medida
                mejor = cara
    if mejor is None or area < 200.0:
        return None
    try:
        vector = mejor.Geometry.Normal
        normal = (float(vector.X), float(vector.Y), float(vector.Z))
    except Exception:
        return None
    lazo = _lazo_exterior(mejor)
    if lazo is None:
        return None
    try:
        aristas = lazo.Edges
        n_aristas = min(int(aristas.Count), 240)
    except Exception:
        return None
    pares = []
    for indice in range(1, n_aristas + 1):
        try:
            arista = aristas.Item(indice)
            inicio = arista.StartVertex.Point
            fin = arista.StopVertex.Point
            pares.append(
                (
                    (float(inicio.X), float(inicio.Y), float(inicio.Z)),
                    (float(fin.X), float(fin.Y), float(fin.Z)),
                )
            )
        except Exception:
            continue
    if len(pares) < 3:
        return None
    planos = [extremo for par in pares for extremo in par]
    planos, normal = _ubicar(occ, planos, normal)
    puntos = [(punto[0] * 10.0, punto[1] * 10.0, punto[2] * 10.0) for punto in planos]
    canto = _canto_mas_largo(puntos, normal)
    return normal, puntos[0::2], canto


def _canto_mas_largo(puntos, normal):
    mejor = None
    largo = 0.0
    nx, ny, nz = normal
    for indice in range(0, len(puntos) - 1, 2):
        a = puntos[indice]
        b = puntos[indice + 1]
        delta = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        proy = delta[0] * nx + delta[1] * ny + delta[2] * nz
        delta = (delta[0] - nx * proy, delta[1] - ny * proy, delta[2] - nz * proy)
        medida = delta[0] ** 2 + delta[1] ** 2 + delta[2] ** 2
        if medida > largo:
            largo = medida
            mejor = delta
    return mejor


def _lazo_exterior(cara):
    """El contorno de la placa. IsOuter no existe en este Inventor: gana el lazo más grande."""
    try:
        lazos = cara.EdgeLoops
        total = int(lazos.Count)
    except Exception:
        return None
    mejor = None
    mejor_area = -1.0
    for indice in range(1, total + 1):
        try:
            lazo = lazos.Item(indice)
        except Exception:
            continue
        try:
            if bool(lazo.IsOuter):
                return lazo
        except Exception:
            pass
        area = _area_lazo(lazo)
        if area > mejor_area:
            mejor_area = area
            mejor = lazo
    return mejor


def _area_lazo(lazo) -> float:
    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []
    try:
        aristas = lazo.Edges
        total = int(aristas.Count)
    except Exception:
        return 0.0
    for indice in range(1, total + 1):
        try:
            arista = aristas.Item(indice)
        except Exception:
            continue
        for vertice in (arista.StartVertex, arista.StopVertex):
            try:
                punto = vertice.Point
                xs.append(float(punto.X))
                ys.append(float(punto.Y))
                zs.append(float(punto.Z))
            except Exception:
                continue
    if len(xs) < 2:
        return 0.0
    tramos = [max(valores) - min(valores) for valores in (xs, ys, zs)]
    tramos.sort()
    return tramos[-1] * tramos[-2]


def _ubicar(occ, puntos, normal):
    """Pasa el contorno al ensamble solo si todavía está en la pieza.

    Mirar el primer vértice contra el centro partía las placas: SEGM1 y SEGM3
    se quedaban en el mismo plano y no tocaban la base.
    """
    from referencia_snapshot import _matriz
    from weld_juntas import _caja_cm, _conviene_matriz

    matriz = _matriz(occ)
    minimo, maximo = _caja_cm(occ)
    if not _conviene_matriz(puntos, minimo, maximo, matriz):
        return puntos, normal
    return [_aplicar(matriz, punto) for punto in puntos], _girar(matriz, normal)


def _aplicar(matriz, punto):
    x, y, z = punto
    return (
        matriz[0][0] * x + matriz[0][1] * y + matriz[0][2] * z + matriz[0][3],
        matriz[1][0] * x + matriz[1][1] * y + matriz[1][2] * z + matriz[1][3],
        matriz[2][0] * x + matriz[2][1] * y + matriz[2][2] * z + matriz[2][3],
    )


def _girar(matriz, normal):
    x, y, z = normal
    return (
        matriz[0][0] * x + matriz[0][1] * y + matriz[0][2] * z,
        matriz[1][0] * x + matriz[1][1] * y + matriz[1][2] * z,
        matriz[2][0] * x + matriz[2][1] * y + matriz[2][2] * z,
    )


def _tamano_cara(puntos: list[tuple[float, float, float]]) -> float:
    if len(puntos) < 3:
        return 0.0
    tramos = []
    for eje in range(3):
        valores = [punto[eje] for punto in puntos]
        tramos.append(max(valores) - min(valores))
    tramos.sort()
    return tramos[-1] * tramos[-2]


def _puntos_lazo(face) -> list[tuple[float, float, float]]:
    try:
        loops = face.EdgeLoops
        total = int(loops.Count)
    except Exception:
        return []
    elegido = None
    for index in range(1, total + 1):
        try:
            loop = loops.Item(index)
        except Exception:
            continue
        try:
            if bool(loop.IsOuter):
                elegido = loop
                break
        except Exception:
            elegido = loop
    if elegido is None and total:
        try:
            elegido = loops.Item(1)
        except Exception:
            return []
    puntos = []
    try:
        edges = elegido.Edges
        n_edges = int(edges.Count)
    except Exception:
        return []
    for index in range(1, n_edges + 1):
        try:
            punto = edges.Item(index).StartVertex.Point
            puntos.append((float(punto.X) * 10.0, float(punto.Y) * 10.0, float(punto.Z) * 10.0))
        except Exception:
            continue
    return puntos


def _caja_mm(occ) -> dict | None:
    try:
        caja = occ.RangeBox
        minimo = (float(caja.MinPoint.X) * 10.0, float(caja.MinPoint.Y) * 10.0, float(caja.MinPoint.Z) * 10.0)
        maximo = (float(caja.MaxPoint.X) * 10.0, float(caja.MaxPoint.Y) * 10.0, float(caja.MaxPoint.Z) * 10.0)
    except Exception:
        return None
    puntos = [(x, y, z) for x in (minimo[0], maximo[0]) for y in (minimo[1], maximo[1]) for z in (minimo[2], maximo[2])]
    centro = tuple((minimo[eje] + maximo[eje]) / 2 for eje in range(3))
    return {"caja": (minimo, maximo), "puntos": puntos, "centro": centro}


def _run(payload: dict) -> dict:
    from inventor_session import _inventor, _short

    kind = _kind(payload)
    limit = max(0, int(payload.get("limit") or 0))
    job = str(payload.get("job") or "").strip() or tank_token(payload)
    if kind != "open" and find_drawing(payload, kind) is None:
        raise RuntimeError(_missing_message(kind, tank_token(payload)))
    inv = _inventor()
    previous = _try_active(inv)
    drawing = None
    opened = False
    path: Path | None = None
    try:
        drawing, opened, path = _acquire_drawing(inv, payload, kind)
        sheets = _sheet_entries(drawing)
        if limit > 0:
            sheets = sheets[:limit]
        if not sheets:
            raise RuntimeError("El plano no tiene hojas.")
        dest = output_folder(str(payload.get("localJpg") or ""), job, create=True)
        if limit <= 0:
            _clear_jpgs(dest)
        files: list[str] = []
        warnings: list[str] = []
        used: set[str] = set()
        total = len(sheets)
        write_weld_progress(current=0, total=total, piece="Preparando hojas…", phase="hojas", photos=0)
        for index, row in enumerate(sheets, start=1):
            write_weld_progress(
                current=index - 1,
                total=total,
                piece=str(row["name"]),
                phase="hojas",
                photos=len(files),
            )
            try:
                jpg = _capture_sheet(inv, drawing, row, dest, used)
                files.append(jpg.name)
            except Exception as ex:
                warnings.append(f"{row['name']}: {_short(ex)}")
            write_weld_progress(
                current=index,
                total=total,
                piece=str(row["name"]),
                phase="hojas",
                photos=len(files),
            )
        tmp = dest / "_tmp"
        if tmp.is_dir():
            try:
                tmp.rmdir()
            except OSError:
                pass
        label = path.name if path is not None and path.name else "plano activo"
        extra = ""
        if warnings:
            extra = "\nAvisos: " + " | ".join(warnings[:8])
        message = f"Weld Anotation: {len(files)} JPG de {label}.{extra}\nCarpeta: {dest}"
        result = {
            "ok": len(files) > 0,
            "message": message,
            "count": len(files),
            "folder": str(dest),
            "files": files,
            "warnings": warnings,
            "drawingPath": str(path or ""),
        }
        if not files:
            result["message"] = "No se pudo guardar ninguna hoja." + extra
        write_weld_progress(
            current=total,
            total=total,
            piece="Listo",
            phase="listo",
            photos=len(files),
            done=True,
            result=result,
            message=result["message"],
        )
        return result
    finally:
        _restore(inv, previous, drawing, opened)


def _kind(payload: dict) -> str:
    kind = str(payload.get("kind") or "face").strip().lower()
    return kind if kind in {"face", "dims", "open"} else "face"


def _missing_message(kind: str, tank: str) -> str:
    token = safe_token(tank)
    if kind == "dims":
        return (
            f"No está {_DIMS_PREFIX}{token}.dwg. "
            "El módulo todavía no genera ese plano; la corrida completa es el siguiente paso de esta pestaña."
        )
    return (
        f"No está {_FACE_PREFIX}{token}.dwg. "
        "El módulo todavía no genera ese plano; la corrida completa es el siguiente paso de esta pestaña."
    )


def _acquire_drawing(inv, payload: dict, kind: str):
    if kind == "open":
        drawing = _active_drawing(inv)
        if drawing is None:
            opened_docs = _open_drawing_docs(inv)
            if len(opened_docs) == 1:
                drawing = opened_docs[0]
        if drawing is None:
            raise RuntimeError("Activa un plano en Inventor, o elige Plano de caras.")
        full = _full_name(drawing)
        return drawing, False, Path(full) if full else None

    path = find_drawing(payload, kind)
    if path is None:
        raise RuntimeError(_missing_message(kind, tank_token(payload)))
    before = [_full_name(doc) for doc in _open_drawing_docs(inv)]
    existing = _drawing_already_open(inv, path)
    if existing is not None:
        return existing, False, path
    try:
        inv.SilentOperation = True
    except Exception:
        pass
    try:
        try:
            drawing = inv.Documents.Open(str(path), True)
        except Exception:
            drawing = inv.Documents.Open(str(path))
    finally:
        try:
            inv.SilentOperation = False
        except Exception:
            pass
    full = _full_name(drawing)
    opened = not any(_same_path(full, item) for item in before)
    return drawing, opened, path


def _capture_sheet(inv, drawing, row: dict, dest: Path, used: set[str]) -> Path:
    sheet = drawing.Sheets.Item(int(row["index"]))
    try:
        drawing.Activate()
    except Exception:
        pass
    sheet.Activate()
    view = inv.ActiveView
    try:
        view.Fit()
    except Exception:
        pass
    try:
        view.Update()
    except Exception:
        pass
    time.sleep(0.15)
    sheet_w = float(sheet.Width)
    sheet_h = float(sheet.Height)
    vis_w, vis_h = sheet_w, sheet_h
    target_x = target_y = None
    try:
        extents = _camera_extents(view.Camera)
        if extents:
            vis_w, vis_h = extents
        target = view.Camera.Target
        target_x, target_y = float(target.X), float(target.Y)
    except Exception:
        pass
    pixel_w, pixel_h = _pixel_size(vis_w, vis_h)
    tmp_dir = dest / "_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    bitmap = _save_bitmap(view, tmp_dir / f"hoja_{int(row['index'])}.png", pixel_w, pixel_h)
    crop = None
    with Image.open(bitmap) as raw:
        if target_x is not None and target_y is not None:
            crop = sheet_pixel_box(
                raw.size[0],
                raw.size[1],
                target_x,
                target_y,
                vis_w,
                vis_h,
                0.0,
                0.0,
                sheet_w,
                sheet_h,
            )
        image = compose_sheet_jpg(raw, crop)
    try:
        bitmap.unlink(missing_ok=True)
    except OSError:
        pass
    out = dest / _jpg_name(str(row["name"]), int(row["index"]), used)
    image.save(out, "JPEG", quality=90, optimize=True)
    return out


def _pixel_size(vis_w: float, vis_h: float) -> tuple[int, int]:
    width = 2000
    height = max(400, int(round(width * float(vis_h) / max(float(vis_w), 0.1))))
    if height > 3600:
        height = 3600
        width = max(800, int(round(height * float(vis_w) / max(float(vis_h), 0.1))))
    return width, height


def _save_bitmap(view, path_png: Path, width: int, height: int) -> Path:
    path_png.parent.mkdir(parents=True, exist_ok=True)
    last = "SaveAsBitmap no escribió la hoja."
    for suffix in (".png", ".bmp"):
        dest = path_png.with_suffix(suffix)
        try:
            if dest.exists():
                dest.unlink()
        except OSError:
            pass
        try:
            view.SaveAsBitmap(str(dest), int(width), int(height))
        except Exception as ex:
            last = str(ex)
            continue
        if dest.is_file() and dest.stat().st_size > 0:
            return dest
    raise RuntimeError(last)


def _camera_extents(camera) -> tuple[float, float] | None:
    try:
        got = camera.GetExtents()
        if isinstance(got, (list, tuple)) and len(got) >= 2:
            width, height = float(got[0]), float(got[1])
            if width > 1 and height > 1:
                return width, height
    except Exception:
        pass
    try:
        import pythoncom
        import win32com.client

        width_ref = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_R8, 0.0)
        height_ref = win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_R8, 0.0)
        camera.GetExtents(width_ref, height_ref)
        width, height = float(width_ref.value), float(height_ref.value)
        if width > 1 and height > 1:
            return width, height
    except Exception:
        return None
    return None


def _sheet_entries(drawing) -> list[dict]:
    sheets = drawing.Sheets
    total = int(sheets.Count)
    rows = []
    for index in range(1, total + 1):
        sheet = sheets.Item(index)
        try:
            name = str(sheet.Name or "").strip()
        except Exception:
            name = ""
        rows.append({"index": index, "name": name or f"Hoja {index}"})
    return rows


def _jpg_name(sheet_name: str, index: int, used: set[str]) -> str:
    base = safe_token(sheet_name) or f"Hoja_{index}"
    name = base
    n = 2
    while name.lower() in used:
        name = f"{base}_{n}"
        n += 1
    used.add(name.lower())
    return f"{name}.jpg"


def _clear_jpgs(dest: Path) -> None:
    if not dest.is_dir():
        return
    carpetas = [dest]
    carpetas.extend(ruta for ruta in dest.iterdir() if ruta.is_dir())
    for carpeta in carpetas:
        for file in carpeta.glob("*.jpg"):
            try:
                file.unlink()
            except OSError:
                pass


def _doc_type(doc) -> int:
    try:
        return int(doc.DocumentType)
    except Exception:
        return 0


def _full_name(doc) -> str:
    try:
        return str(doc.FullFileName or "")
    except Exception:
        return ""


def _try_active(inv):
    try:
        return inv.ActiveDocument
    except Exception:
        return None


def _active_drawing(inv):
    doc = _try_active(inv)
    if doc is not None and _doc_type(doc) == DRAWING_DOC:
        return doc
    return None


def _open_drawing_docs(inv) -> list:
    docs = []
    try:
        collection = inv.Documents
        total = int(collection.Count)
    except Exception:
        return docs
    for index in range(1, total + 1):
        try:
            doc = collection.Item(index)
        except Exception:
            continue
        if _doc_type(doc) == DRAWING_DOC:
            docs.append(doc)
    return docs


def _same_path(left: str, right: str) -> bool:
    if not left or not right:
        return False
    try:
        return os.path.normcase(str(Path(left).resolve())) == os.path.normcase(str(Path(right).resolve()))
    except OSError:
        return os.path.normcase(left) == os.path.normcase(right)


def _drawing_already_open(inv, path: Path):
    for doc in _open_drawing_docs(inv):
        if _same_path(_full_name(doc), str(path)):
            return doc
    return None


def _restore(inv, previous, drawing, opened: bool) -> None:
    if previous is not None:
        try:
            previous.Activate()
        except Exception:
            pass
    if not opened or drawing is None:
        return
    try:
        inv.SilentOperation = True
    except Exception:
        pass
    try:
        drawing.Close(False)
    except Exception:
        pass
    try:
        inv.SilentOperation = False
    except Exception:
        pass


def reset_weld_progress(total: int = 0, piece: str = "Preparando…") -> None:
    global _started
    _started = time.time()
    write_weld_progress(
        current=0,
        total=max(0, int(total)),
        piece=piece,
        phase="inicio",
        done=False,
        result=None,
        message="",
    )


def write_weld_progress(
    *,
    current: int,
    total: int,
    piece: str,
    marca: str = "",
    photos: int = 0,
    phase: str = "hojas",
    done: bool = False,
    result: dict | None = None,
    message: str = "",
) -> None:
    elapsed = max(0.0, time.time() - (_started or time.time()))
    cur = max(0, int(current))
    tot = max(0, int(total))
    eta = 0.0
    if cur > 0 and tot > cur:
        eta = (elapsed / cur) * (tot - cur)
    elif done:
        eta = 0.0
    payload = {
        "running": not done,
        "done": done,
        "current": cur,
        "total": tot,
        "piece": str(piece or ""),
        "marca": str(marca or ""),
        "photos": int(photos),
        "phase": phase,
        "elapsed": round(elapsed, 1),
        "eta": round(eta, 1),
        "percent": 100 if done else (int(100 * cur / tot) if tot else 0),
        "message": message,
        "result": result,
    }
    PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False)
    tmp = PROGRESS_PATH.with_name(f"weld_anotation_progress.{os.getpid()}.tmp")
    try:
        tmp.write_text(data, encoding="utf-8")
        for attempt in range(12):
            try:
                os.replace(str(tmp), str(PROGRESS_PATH))
                return
            except OSError:
                time.sleep(0.05 * (attempt + 1))
        PROGRESS_PATH.write_text(data, encoding="utf-8")
    except OSError:
        pass
    try:
        if tmp.exists():
            tmp.unlink()
    except OSError:
        pass


def read_weld_progress() -> dict:
    if not PROGRESS_PATH.is_file():
        return {
            "running": False,
            "done": False,
            "current": 0,
            "total": 0,
            "piece": "",
            "marca": "",
            "photos": 0,
            "phase": "",
            "elapsed": 0,
            "eta": 0,
            "percent": 0,
            "message": "",
            "result": None,
        }
    try:
        data = json.loads(PROGRESS_PATH.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}
