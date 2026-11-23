"""Jobs de Ingeniería en proceso y su carpeta MODEL CORE FILES\\AutoDXF.

El VSM guarda ``local_path`` como lo ve el contenedor (``/mnt/server_data/...``).
Aquí se traduce a la unidad X: o al UNC del share, que es donde AutoDXF escribe
y donde el ANS lee los DXF.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFIJO_DOCKER = "/mnt/server_data/"
MARCA = "ARGA METALS CORPORATE SYSTEM"
API_DEFAULT = "http://192.168.2.80:8010"
RAIZ_X = os.path.join("X:\\", MARCA)
RAIZ_SERVIDOR = r"C:\Users\Administrator\Desktop\Grupo Arga Metals"
EXCLUIR_AL_PUBLICAR = {
    "processed files",
    "procesados",
    "nesting",
    "from_step",
    "step",
    "__pycache__",
}


def url_api() -> str:
    ruta = ROOT / "config" / "vsm_jobs.json"
    try:
        data = json.loads(ruta.read_text(encoding="utf-8-sig"))
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return str(data.get("api") or API_DEFAULT).strip().rstrip("/") or API_DEFAULT


def raiz_corporativa() -> str:
    ruta = ROOT / "config" / "acotacion-jpg.json"
    try:
        data = json.loads(ruta.read_text(encoding="utf-8-sig"))
    except Exception:
        return ""
    paths = data.get("paths") if isinstance(data, dict) else {}
    if not isinstance(paths, dict):
        return ""
    return str(paths.get("corporateRoot") or "").strip()


def a_windows(local_path: str, *, existe=os.path.isdir, corporate_root: str = "") -> str:
    """Traduce el ``local_path`` del VSM a una carpeta que esta PC puede escribir."""
    raw = str(local_path or "").strip()
    if not raw:
        return ""
    if raw.startswith(PREFIJO_DOCKER):
        resto = raw[len(PREFIJO_DOCKER) :].replace("/", "\\").strip("\\")
        candidatos = [
            os.path.join("X:\\", resto),
            _unc_desde_raiz(corporate_root, resto),
            os.path.join(RAIZ_SERVIDOR, resto),
        ]
        candidatos = [c for c in candidatos if c]
        for candidato in candidatos:
            if existe(candidato) or _prefijo_existe(candidato, existe):
                return candidato
        return candidatos[0] if candidatos else ""
    return os.path.normpath(raw.replace("/", "\\"))


def carpeta_autodxf(local_path: str, *, existe=os.path.isdir, corporate_root: str = "") -> str:
    actual = a_windows(local_path, existe=existe, corporate_root=corporate_root)
    if not actual:
        return ""
    nombre = os.path.basename(actual).casefold()
    padre = os.path.basename(os.path.dirname(actual)).casefold()
    if nombre == "autodxf" and padre == "model core files":
        return actual
    if nombre == "model core files":
        return os.path.join(actual, "AutoDXF")
    return os.path.join(actual, "MODEL CORE FILES", "AutoDXF")


def ruta_permitida(carpeta: str) -> bool:
    norm = os.path.normcase(os.path.normpath(str(carpeta or "")))
    if not norm or os.path.normcase(MARCA) not in norm:
        return False
    return os.path.basename(norm).casefold() == "autodxf"


def en_proceso_ingenieria(job: dict) -> bool:
    """La misma columna EN PROCESO de Ingeniería: etapa inventor abierta."""
    if not isinstance(job, dict):
        return False
    status = str(job.get("status") or "pending").strip().lower()
    history = job.get("history") if isinstance(job.get("history"), list) else []
    tiene_inventor = any(str(h.get("stage") or "").strip().lower() == "inventor" for h in history if isinstance(h, dict))
    if status == "inventor":
        visible = True
    elif bool(job.get("has_unfused_pieces")) or tiene_inventor:
        visible = True
    else:
        visible = False
    if not visible:
        return False
    try:
        qty = max(1, int(job.get("quantity") or 1))
    except (TypeError, ValueError):
        qty = 1
    activos = 0
    for indice in range(1, qty + 1):
        unidad = [h for h in history if isinstance(h, dict) and h.get("unit_index") == indice]
        unidad.sort(key=lambda h: str(h.get("start_time") or ""), reverse=True)
        etapa = str(unidad[0].get("stage") or "").strip().lower() if unidad else status
        if etapa == "deleted":
            continue
        if etapa == "inventor" or (etapa == "pending") or status != "inventor":
            activos += 1
    if activos <= 0:
        return False
    inventor = [
        h
        for h in history
        if isinstance(h, dict)
        and str(h.get("stage") or "").strip().lower() == "inventor"
        and h.get("unit_index") in (None, "")
    ]
    inventor.sort(key=lambda h: str(h.get("start_time") or ""), reverse=True)
    if inventor and inventor[0].get("end_time"):
        return False
    return True


def armar_lista(
    crudos: list,
    *,
    existe=os.path.isdir,
    corporate_root: str = "",
) -> dict:
    jobs: list[dict] = []
    sin_carpeta = 0
    for crudo in crudos or []:
        if not isinstance(crudo, dict) or not en_proceso_ingenieria(crudo):
            continue
        destino = carpeta_autodxf(
            str(crudo.get("local_path") or ""),
            existe=existe,
            corporate_root=corporate_root,
        )
        if not destino or not ruta_permitida(destino):
            sin_carpeta += 1
            continue
        try:
            cantidad = max(1, int(crudo.get("quantity") or 1))
        except (TypeError, ValueError):
            cantidad = 1
        try:
            dxf_count = int(crudo.get("dxf_count") or 0)
        except (TypeError, ValueError):
            dxf_count = 0
        jobs.append(
            {
                "id": crudo.get("id"),
                "job_number": str(crudo.get("job_number") or "").strip(),
                "client": str(crudo.get("client") or "").strip(),
                "product": str(crudo.get("product") or "").strip(),
                "quantity": cantidad,
                "dxf_count": dxf_count,
                "autodxf": destino,
            }
        )
    jobs.sort(key=lambda item: str(item.get("job_number") or "").casefold())
    mensaje = f"{len(jobs)} jobs en Ingeniería, en proceso."
    if sin_carpeta:
        mensaje += f" {sin_carpeta} sin carpeta en el share."
    return {"ok": True, "jobs": jobs, "message": mensaje}


def descargar_jobs(url: str, *, timeout: float = 25) -> list:
    pedido = urllib.request.Request(
        url.rstrip("/") + "/jobs/?limit=5000",
        headers={"Accept": "application/json"},
    )
    with urllib.request.urlopen(pedido, timeout=timeout) as respuesta:
        data = json.loads(respuesta.read().decode("utf-8"))
    if not isinstance(data, list):
        raise ValueError("El VSM no devolvió la lista de jobs.")
    return data


def listar_en_proceso() -> dict:
    try:
        crudos = descargar_jobs(url_api())
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError, OSError) as ex:
        return {"ok": False, "jobs": [], "message": f"No se pudo leer Ingeniería en el VSM. {ex}"}
    return armar_lista(crudos, corporate_root=raiz_corporativa())


def asegurar_autodxf(carpeta: str) -> dict:
    destino = os.path.normpath(str(carpeta or "").strip())
    if not ruta_permitida(destino):
        return {"ok": False, "message": "La carpeta del job no está en el share corporativo."}
    job_dir = os.path.dirname(os.path.dirname(destino))
    if not os.path.isdir(job_dir):
        return {"ok": False, "message": "No se encuentra la carpeta del job en el servidor."}
    try:
        os.makedirs(destino, exist_ok=True)
    except OSError as ex:
        return {"ok": False, "message": f"No se pudo crear AutoDXF. {ex}"}
    return {"ok": True, "message": destino}


def publicar_dxf_en_raiz(carpeta: str) -> dict:
    """Sube los DXF de las subcarpetas Cal a la raíz de AutoDXF.

    Ingeniería cuenta solo los archivos de esa raíz. El ANS no debe ver la
    misma pieza dos veces, así que el archivo sale de la subcarpeta.
    ``Processed Files`` se queda donde el ANS lo dejó.
    """
    root = Path(carpeta)
    if root.name.casefold() != "autodxf":
        anidada = root / "AutoDXF"
        root = anidada if anidada.is_dir() else root
    if not root.is_dir() or root.name.casefold() != "autodxf":
        return {"ok": False, "movidos": 0, "message": "No está la carpeta AutoDXF."}
    if not ruta_permitida(str(root)):
        return {"ok": False, "movidos": 0, "message": "La carpeta del job no está en el share corporativo."}
    movidos = 0
    for sub in list(root.iterdir()):
        if not sub.is_dir() or sub.name.casefold() in EXCLUIR_AL_PUBLICAR:
            continue
        for dxf in list(sub.glob("*.dxf")):
            destino = root / dxf.name
            try:
                if destino.exists():
                    destino.unlink()
                dxf.replace(destino)
            except OSError:
                continue
            movidos += 1
        try:
            if not any(sub.iterdir()):
                sub.rmdir()
        except OSError:
            pass
    return {"ok": True, "movidos": movidos, "message": str(root)}


def _unc_desde_raiz(corporate_root: str, resto: str) -> str:
    root = str(corporate_root or "").strip().rstrip("\\/")
    if not root or not resto:
        return ""
    if os.path.basename(root).casefold() == MARCA.casefold() and resto.casefold().startswith(MARCA.casefold()):
        return os.path.join(os.path.dirname(root), resto)
    return os.path.join(root, resto)


def _prefijo_existe(candidato: str, existe) -> bool:
    """El job puede no tener aún la carpeta, pero el share sí."""
    actual = os.path.normpath(candidato)
    vistos = set()
    while actual and actual not in vistos:
        vistos.add(actual)
        if existe(actual):
            marca = os.path.normcase(MARCA)
            return marca in os.path.normcase(actual)
        padre = os.path.dirname(actual)
        if padre == actual:
            break
        actual = padre
    return False
