"""Árbol del dossier: producto, cliente y job son carpetas, no un nombre armado."""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "acotacion-jpg.json"
STORE = ROOT / "config" / "dossier_eleccion.json"
RAIZ_X = r"X:\ARGA METALS CORPORATE SYSTEM"
DIAS_JOB = 15
NOMBRE_EFORT = "Efort Weld Files"
PUNTERO_EFORT = Path(os.environ.get("LOCALAPPDATA", "")) / "AutoDXF" / "efort_weld_dir.txt"


def raiz_productos() -> str:
    """La unidad X: es la que se recorre en el explorador. Si no está, el UNC del config."""
    if os.path.isdir(RAIZ_X):
        return RAIZ_X
    try:
        data = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    except Exception:
        return ""
    paths = data.get("paths") if isinstance(data, dict) else {}
    return str((paths or {}).get("corporateRoot") or "").rstrip("\\/")


def _dirs(ruta: str) -> list[str]:
    try:
        nombres = [entry.name for entry in os.scandir(ruta) if entry.is_dir(follow_symlinks=False)]
    except OSError:
        return []
    nombres.sort(key=str.casefold)
    return nombres


def listar_productos(*, raiz: str = "") -> dict:
    base = raiz or raiz_productos()
    if not base or not os.path.isdir(base):
        return {
            "ok": False,
            "raiz": base,
            "nombres": [],
            "message": "No se encuentra la carpeta de productos.",
        }
    return {"ok": True, "raiz": base, "nombres": _dirs(base), "message": ""}


def listar_clientes(producto: str, *, raiz: str = "") -> dict:
    base = raiz or raiz_productos()
    ruta = os.path.join(base, str(producto or "").strip())
    if not producto or not os.path.isdir(ruta):
        return {"ok": False, "nombres": [], "message": "Ese producto no está en el árbol."}
    return {"ok": True, "nombres": _dirs(ruta), "message": ""}


def listar_jobs(
    producto: str,
    cliente: str,
    *,
    raiz: str = "",
    dias: int = DIAS_JOB,
    ahora: float | None = None,
    edad_de=os.path.getctime,
) -> dict:
    """Jobs cuya carpeta lleva como máximo `dias` días. Los más viejos no reciben dossier."""
    base = raiz or raiz_productos()
    ruta = os.path.join(base, str(producto or "").strip(), str(cliente or "").strip())
    if not os.path.isdir(ruta):
        return {"ok": False, "jobs": [], "message": "Ese cliente no está en el árbol."}
    momento = time.time() if ahora is None else float(ahora)
    limite = float(dias) * 86400
    jobs: list[dict] = []
    try:
        entradas = list(os.scandir(ruta))
    except OSError:
        return {"ok": False, "jobs": [], "message": "No se pudo leer la carpeta del cliente."}
    for entry in entradas:
        if not entry.is_dir(follow_symlinks=False):
            continue
        if entry.name.casefold() == "dossier files":
            continue
        try:
            creado = float(edad_de(entry.path))
        except OSError:
            continue
        edad = momento - creado
        if edad > limite:
            continue
        jobs.append({"nombre": entry.name, "dias": int(edad // 86400)})
    jobs.sort(key=lambda item: (item["dias"], str(item["nombre"]).casefold()))
    return {"ok": True, "jobs": jobs, "message": ""}


def cargar_eleccion() -> dict:
    try:
        data = json.loads(STORE.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    producto = str(data.get("producto") or "").strip()
    cliente = str(data.get("cliente") or "").strip()
    job = str(data.get("job") or "").strip()
    raiz = str(data.get("raiz") or "").strip()
    if not (producto and cliente and job):
        return {}
    return {"producto": producto, "cliente": cliente, "job": job, "raiz": raiz}


def guardar_eleccion(producto: str, cliente: str, job: str) -> dict:
    producto = str(producto or "").strip()
    cliente = str(cliente or "").strip()
    job = str(job or "").strip()
    raiz = raiz_productos()
    destino = os.path.join(raiz, producto, cliente, job)
    if not os.path.isdir(destino):
        return {"ok": False, "message": "Esa carpeta de job no existe en el dossier."}
    data = {"producto": producto, "cliente": cliente, "job": job, "raiz": raiz}
    try:
        STORE.parent.mkdir(parents=True, exist_ok=True)
        STORE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "message": f"No se pudo guardar la elección. {exc}"}
    efort = publicar_efort_weld(producto, cliente, job, raiz=raiz)
    if not efort:
        return {"ok": False, "message": "No se pudo crear Efort Weld Files en el job."}
    dossier = os.path.join(destino, "DOSSIER FILES", "JPGS")
    return {"ok": True, "message": dossier, "dossier": dossier, "efort": efort, **data}


def _segmento(nombre: str) -> str:
    texto = str(nombre or "").strip()
    if not texto or texto in {".", ".."} or any(caracter in texto for caracter in "\\/"):
        return ""
    return texto


def ruta_efort_weld(producto: str, cliente: str, job: str, *, raiz: str = "") -> str:
    """``CORPORATE\\PRODUCTO\\CLIENTE\\job\\Efort Weld Files``. Al lado de DOSSIER FILES."""
    producto, cliente, job = _segmento(producto), _segmento(cliente), _segmento(job)
    base = (raiz or raiz_productos()).rstrip("\\/")
    if not (producto and cliente and job and base):
        return ""
    return os.path.join(base, producto, cliente, job, NOMBRE_EFORT)


def publicar_efort_weld(
    producto: str,
    cliente: str,
    job: str,
    *,
    raiz: str = "",
    puntero: Path | None = None,
) -> str:
    """Crea la carpeta en el job elegido y deja la ruta para el bridge de Inventor."""
    destino = ruta_efort_weld(producto, cliente, job, raiz=raiz)
    if not destino:
        return ""
    job_dir = os.path.dirname(destino)
    if not os.path.isdir(job_dir):
        return ""
    if os.path.basename(destino).casefold() != NOMBRE_EFORT.casefold():
        return ""
    try:
        os.makedirs(destino, exist_ok=True)
        archivo = puntero or PUNTERO_EFORT
        archivo.parent.mkdir(parents=True, exist_ok=True)
        archivo.write_text(destino, encoding="utf-8")
    except OSError:
        return ""
    return destino


def ruta_jpgs(producto: str, cliente: str, job: str, *, raiz: str = "") -> str:
    producto, cliente, job = _segmento(producto), _segmento(cliente), _segmento(job)
    base = (raiz or raiz_productos()).rstrip("\\/")
    if not (producto and cliente and job and base):
        return ""
    return os.path.join(base, producto, cliente, job, "DOSSIER FILES", "JPGS")


def vaciar_carpeta(ruta: str) -> int:
    """Borra el contenido. La carpeta se queda. No sigue un acceso fuera de ella."""
    if not ruta or not os.path.isdir(ruta):
        return 0
    base = os.path.abspath(ruta)
    n = 0
    for entry in list(os.scandir(base)):
        destino = os.path.abspath(entry.path)
        if os.path.normcase(os.path.commonpath([base, destino])) != os.path.normcase(base):
            continue
        if entry.is_dir(follow_symlinks=False):
            shutil.rmtree(destino)
        else:
            os.remove(destino)
        n += 1
    return n


def _jpg_local(job: str) -> str:
    job = _segmento(job)
    if not job:
        return ""
    try:
        from acotacion import load_acotacion, local_jpg_dir

        cfg = load_acotacion()
        configured = str((cfg.get("paths") or {}).get("localJpg") or "")
        folder, _note = local_jpg_dir(configured, create=False)
    except Exception:
        return ""
    destino = Path(folder) / job
    if destino.name != job or destino.parent.name.casefold() != "jpg" or not destino.is_dir():
        return ""
    return str(destino)


def borrar_filas(producto: str, cliente: str, job: str) -> int:
    """Quita de cotas_dossier las filas de este producto, cliente y job."""
    producto, cliente, job = _segmento(producto), _segmento(cliente), _segmento(job)
    if not (producto and cliente and job):
        return 0
    largo = f"\\{producto}\\{cliente}\\{job}\\"
    corto = f"\\{producto}\\{job}\\"
    cliente_en_ruta = f"\\{producto}\\{cliente}\\"
    from cotas_dossier import _db_target

    target = _db_target()
    if not target:
        raise RuntimeError("sin conexión a la base")
    import psycopg2

    with psycopg2.connect(**target) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM public.cotas_dossier
                WHERE strpos(replace(ruta, '/', '\\'), %s) > 0
                   OR (
                        job = %s
                        AND strpos(replace(ruta, '/', '\\'), %s) > 0
                        AND strpos(replace(ruta, '/', '\\'), %s) = 0
                   )
                """,
                (largo, job, corto, cliente_en_ruta),
            )
            filas = int(cur.rowcount)
        conn.commit()
    return filas


def quitar_exportacion(producto: str, cliente: str, job: str, *, raiz: str = "") -> dict:
    """Vacía DOSSIER FILES\\JPGS de ese job y borra sus filas. El modelo se queda."""
    jpgs = ruta_jpgs(producto, cliente, job, raiz=raiz)
    if not jpgs:
        return {"ok": False, "message": "Falta producto, cliente o job."}
    job_dir = os.path.dirname(os.path.dirname(jpgs))
    if not os.path.isdir(job_dir):
        return {"ok": False, "message": "Esa carpeta de job no existe en el dossier."}
    try:
        carpetas = vaciar_carpeta(jpgs) if os.path.isdir(jpgs) else 0
    except OSError as exc:
        return {"ok": False, "message": f"No se pudieron borrar los JPG del job. {exc}"}
    local = "" if raiz else _jpg_local(job)
    if local:
        try:
            vaciar_carpeta(local)
        except OSError:
            pass
    try:
        filas = borrar_filas(producto, cliente, job)
    except Exception as exc:
        return {
            "ok": False,
            "carpetas": carpetas,
            "message": f"Se vació JPGS ({carpetas}). La base no se pudo limpiar. {exc}",
        }
    return {
        "ok": True,
        "filas": filas,
        "carpetas": carpetas,
        "message": (
            f"Exportación quitada. {filas} filas en la base y "
            f"{carpetas} elementos en DOSSIER FILES\\JPGS. El modelo del job sigue en su carpeta."
        ),
    }


def atender(payload: str) -> dict:
    try:
        data = json.loads(payload or "{}")
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    accion = str(data.get("accion") or "productos").strip().casefold()
    if accion == "productos":
        return listar_productos()
    if accion == "clientes":
        return listar_clientes(str(data.get("producto") or ""))
    if accion == "jobs":
        return listar_jobs(str(data.get("producto") or ""), str(data.get("cliente") or ""))
    if accion == "actual":
        eleccion = cargar_eleccion()
        return {"ok": bool(eleccion), **eleccion}
    if accion == "elegir":
        return guardar_eleccion(
            str(data.get("producto") or ""),
            str(data.get("cliente") or ""),
            str(data.get("job") or ""),
        )
    if accion == "quitar":
        return quitar_exportacion(
            str(data.get("producto") or ""),
            str(data.get("cliente") or ""),
            str(data.get("job") or ""),
        )
    return {"ok": False, "message": "Acción desconocida."}
