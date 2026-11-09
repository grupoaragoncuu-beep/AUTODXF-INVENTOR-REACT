"""Rutas y clasificación de Acotación JPG. Nada de producto va quemado en el motor."""

from __future__ import annotations

import json
import re
from pathlib import Path

from dossier_arbol import cargar_eleccion

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "acotacion-jpg.json"


def _windows_profile(path: Path) -> str:
    """Nombre de perfil en C:\\Users\\<nombre>. Vacío si no es un perfil local."""
    parts = Path(path).parts
    if len(parts) < 3 or not re.fullmatch(r"[A-Za-z]:\\", parts[0]):
        return ""
    if parts[1].casefold() != "users":
        return ""
    return str(parts[2])


def ensure_dir(path: Path) -> Path:
    """Crea la carpeta sin recrear ancestros que ya existen.

    En Windows, mkdir(parents=True) sube hasta C:\\Users\\<otro usuario> y
    lanza WinError 5 (acceso denegado) aunque esa carpeta no haya que crearla
    o no se pueda crear.
    """
    path = Path(path)
    if path.is_dir():
        return path
    missing: list[Path] = []
    current = path
    while not current.exists():
        missing.append(current)
        parent = current.parent
        if parent == current:
            break
        current = parent
    for folder in reversed(missing):
        try:
            folder.mkdir(exist_ok=True)
        except FileExistsError:
            continue
        except OSError:
            if folder.is_dir():
                continue
            raise
    if not path.is_dir():
        raise OSError(f"No se pudo crear la carpeta {path}")
    return path


def _mismo_perfil(path: Path) -> bool:
    """True si `path` no es un perfil local, o es el de esta sesión.

    Windows puede mostrar el mismo perfil como ``Ing. Cano`` y ``ING~1.CAN``.
    """
    owner = _windows_profile(path)
    if not owner:
        return True
    home = Path.home()
    mine = _windows_profile(home)
    if mine and owner.casefold() == mine.casefold():
        return True
    try:
        perfil = Path(path.anchor) / "Users" / owner
        return perfil.resolve() == home.resolve()
    except OSError:
        return False


def local_jpg_dir(configured: str = "", *, create: bool = True) -> tuple[Path, str]:
    """Carpeta JPG usable en esta PC.

    Si la ruta guardada es de otro usuario de Windows, no se intenta crear
    (eso produce WinError 5 sobre C:\\Users\\...). Se usa JPG junto al módulo.
    Devuelve (carpeta, aviso). El aviso va vacío cuando se usa la ruta pedida.
    """
    fallback = ROOT / "JPG"
    raw = str(configured or "").strip().strip('"')
    if not raw:
        if create:
            ensure_dir(fallback)
        return fallback, ""
    candidate = Path(raw)
    owner = _windows_profile(candidate)
    mine = _windows_profile(Path.home())
    if owner and not _mismo_perfil(candidate):
        if create:
            ensure_dir(fallback)
        return fallback, (
            f"Esta PC no puede crear {candidate}: el usuario de Windows es \"{mine}\" "
            f"y la ruta guardada es de \"{owner}\" (acceso denegado). "
            f"Los JPG se guardan en {fallback}."
        )
    if not create:
        return candidate, ""
    try:
        ensure_dir(candidate)
    except OSError as ex:
        ensure_dir(fallback)
        return fallback, (
            f"No pude crear {candidate} ({ex}). Los JPG se guardan en {fallback}."
        )
    return candidate, ""


def load_acotacion() -> dict:
    data: dict = {}
    if CONFIG.is_file():
        try:
            loaded = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
            if isinstance(loaded, dict):
                data = loaded
        except (OSError, json.JSONDecodeError):
            data = {}
    paths = data.get("paths") if isinstance(data.get("paths"), dict) else None
    if not isinstance(paths, dict):
        return data
    try:
        resolved, note = local_jpg_dir(str(paths.get("localJpg") or ""))
    except OSError:
        return data
    if not note:
        return data
    data = dict(data)
    data["paths"] = {**paths, "localJpg": str(resolved)}
    return data


def save_acotacion(catalog: dict) -> dict:
    if not isinstance(catalog, dict):
        return {"ok": False, "message": "La configuración no es válida."}
    current = load_acotacion()
    merged = {**current, **catalog}
    if isinstance(catalog.get("photoLayout"), dict):
        merged["photoLayout"] = catalog["photoLayout"]
    elif "photoLayout" not in merged and isinstance(current.get("photoLayout"), dict):
        merged["photoLayout"] = current["photoLayout"]
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "message": "Rutas, árbol de fotos y lógica de cotas guardadas.", "config": merged}


def classify_assembly(name: str, path: str, catalog: dict | None = None, job: str = "") -> dict:
    cfg = catalog or load_acotacion()
    text_name = f"{name or ''} {Path(path or '').stem}".replace("/", "\\")
    text_path = str(path or "").replace("/", "\\")
    rules = cfg.get("classify") if isinstance(cfg.get("classify"), list) else []
    for raw in rules:
        if not isinstance(raw, dict) or raw.get("enabled") is False:
            continue
        field = str(raw.get("field") or "nombre").lower()
        haystack = text_path if field == "ruta" else text_name
        if field == "ruta":
            haystack = f"{text_name} | {text_path}"
        pattern = str(raw.get("pattern") or "").strip()
        if not pattern:
            continue
        try:
            if not re.search(pattern, haystack, re.IGNORECASE):
                continue
        except re.error:
            continue
        tipo = str(raw.get("tipo") or "TANQUE").upper()
        if tipo not in {"BOARD", "TANQUE"}:
            tipo = "TANQUE"
        flows = cfg.get("flows") if isinstance(cfg.get("flows"), dict) else {}
        flow = flows.get(tipo) if isinstance(flows.get(tipo), dict) else {}
        result = {
            "ok": True,
            "tipo": tipo,
            "familia": str(raw.get("familia") or tipo),
            "rule": str(raw.get("id") or ""),
            "label": str(flow.get("label") or tipo),
            "unit": str(flow.get("unit") or ("mm" if tipo == "BOARD" else "in")),
            "picks": list(flow.get("picks") or []),
            "views": list(flow.get("views") or []),
            "dossierProduct": str(flow.get("dossierProduct") or ""),
            "message": f"{flow.get('label') or tipo}. Regla: {raw.get('id')}.",
        }
        result["dossier"] = _dossier_path(cfg, result, name, path, job)
        return result
    default = str(cfg.get("defaultTipo") or "TANQUE").upper()
    if default not in {"BOARD", "TANQUE"}:
        default = "TANQUE"
    flows = cfg.get("flows") if isinstance(cfg.get("flows"), dict) else {}
    flow = flows.get(default) if isinstance(flows.get(default), dict) else {}
    result = {
        "ok": True,
        "tipo": default,
        "familia": default,
        "rule": "default",
        "label": str(flow.get("label") or default),
        "unit": str(flow.get("unit") or "in"),
        "picks": list(flow.get("picks") or []),
        "views": list(flow.get("views") or []),
        "dossierProduct": str(flow.get("dossierProduct") or ""),
        "message": f"Sin coincidencia. Se usa {flow.get('label') or default}.",
    }
    result["dossier"] = _dossier_path(cfg, result, name, path, job)
    return result


def _segmentos_dossier(
    root: str,
    producto: str,
    cliente: str,
    job: str,
    dossier: str,
    jpgs: str,
) -> str:
    """``CORPORATE\\PRODUCTO\\CLIENTE\\job\\DOSSIER FILES\\JPGS``."""
    corp = "arga metals corporate system"
    partes = [str(root or "").rstrip("\\/")]
    prod = str(producto or "").strip()
    cli = str(cliente or "").strip()
    if prod and prod.casefold() != corp and "\\" not in prod and "/" not in prod:
        partes.append(prod)
    if (
        cli
        and cli.casefold() not in {corp, prod.casefold()}
        and "\\" not in cli
        and "/" not in cli
    ):
        partes.append(cli)
    partes += [str(job or "").strip(), str(dossier or "").strip(), str(jpgs or "").strip()]
    return "\\".join(parte for parte in partes if parte)


def _dossier_path(cfg: dict, hit: dict, name: str, path: str, job: str = "") -> str:
    from job_id import resolve_job

    paths = cfg.get("paths") if isinstance(cfg.get("paths"), dict) else {}
    root = str(paths.get("corporateRoot") or "").rstrip("\\/")
    job = resolve_job(job, name, path)
    dossier = str(paths.get("dossierFolder") or "DOSSIER FILES")
    jpgs = str(paths.get("jpgsFolder") or "JPGS")
    eleccion = cargar_eleccion()
    cliente = ""
    producto = ""
    if eleccion and str(eleccion.get("job") or "").casefold() == job.casefold():
        producto = str(eleccion.get("producto") or "")
        cliente = str(eleccion.get("cliente") or "")
        if eleccion.get("raiz"):
            root = str(eleccion.get("raiz") or "").rstrip("\\/")
    if not producto:
        producto = str(hit.get("dossierProduct") or "")
    if not root:
        return ""
    return _segmentos_dossier(root, producto, cliente, job, dossier, jpgs)
