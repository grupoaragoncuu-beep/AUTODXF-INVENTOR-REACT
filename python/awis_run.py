"""Los tres pasos del plugin AWIS Welding, lanzados desde el módulo."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_EMPAQUETADO = ROOT / "tools" / "AWIS" / "FaceDrawingVerify.exe"
_COLEGA = Path(r"c:\Users\Ing. Cano\Documents\Cotas de Soldadura\_verify\bin\Debug\net10.0-windows\FaceDrawingVerify.exe")
CREATE_NO_WINDOW = 0x08000000

PASOS = {
    "solids": "--solids",
    "classify": "--classify",
    "drawings": "--drawings",
}


def awis_exe() -> Path | None:
    candidatos: list[Path] = []
    override = os.environ.get("AUTODXF_AWIS", "").strip().strip('"')
    if override:
        candidatos.append(Path(override))
    candidatos.append(_EMPAQUETADO)
    candidatos.append(_COLEGA)
    release = _COLEGA.parent.parent / "Release" / "net10.0-windows" / "FaceDrawingVerify.exe"
    candidatos.append(release)
    vistos: set[str] = set()
    for ruta in candidatos:
        clave = str(ruta).lower()
        if clave in vistos:
            continue
        vistos.add(clave)
        if ruta.is_file():
            return ruta
    return None


def run_awis(paso: str) -> dict:
    flag = PASOS.get((paso or "").strip().lower())
    if flag is None:
        return {"ok": False, "message": "Paso de AWIS desconocido.", "log": ""}

    exe = awis_exe()
    if exe is None:
        return {
            "ok": False,
            "message": "Falta el programa AWIS en esta instalación. FaceDrawingVerify.exe debe ir en tools\\AWIS.",
            "log": "",
        }

    from dossier_arbol import cargar_eleccion, publicar_efort_weld

    eleccion = cargar_eleccion()
    if not eleccion:
        return {
            "ok": False,
            "message": "Elige producto, cliente y job en el módulo antes de AWIS.",
            "log": "",
        }
    destino = publicar_efort_weld(
        eleccion["producto"],
        eleccion["cliente"],
        eleccion["job"],
        raiz=str(eleccion.get("raiz") or ""),
    )
    if not destino:
        return {
            "ok": False,
            "message": "No está la carpeta del job. Vuelve a elegirla en el módulo.",
            "log": "",
        }
    env = os.environ.copy()
    env["AUTODXF_EFORT_WELD"] = destino

    try:
        completed = subprocess.run(
            [str(exe), flag],
            cwd=str(exe.parent),
            capture_output=True,
            timeout=7200,
            creationflags=CREATE_NO_WINDOW,
            env=env,
        )
    except subprocess.TimeoutExpired as error:
        text = _decode(error.stdout) + _decode(error.stderr)
        return {"ok": False, "message": "AWIS superó 2 horas.", "log": text.strip()}
    except OSError as error:
        return {"ok": False, "message": f"No se pudo iniciar AWIS: {error}", "log": ""}

    text = _decode(completed.stdout)
    error_text = _decode(completed.stderr).strip()
    if error_text:
        text = f"{text}\n{error_text}".strip()
    return {
        "ok": completed.returncode == 0,
        "message": _resumen(flag, completed.returncode, text),
        "log": text.strip(),
    }


def _resumen(flag: str, code: int, output: str) -> str:
    if "No tank assembly" in output:
        return "Abre el ensamble del tanque en Inventor y vuelve a intentar."
    if code != 0:
        utiles = [linea.strip() for linea in output.splitlines() if linea.strip()]
        return utiles[-1] if utiles else "AWIS no terminó."
    if flag == "--solids":
        solids = _valor(output, "Solids:")
        return f"Sólidos de soldadura creados: {solids}." if solids else "Sólidos de soldadura listos."
    if flag == "--classify":
        return "Clasificación cerrada."
    if flag == "--drawings":
        photos = _valor(output, "Photos:")
        folder = _valor(output, "Fotos:")
        if photos and folder:
            return f"Cotas listas: {photos} fotos en {folder}."
        return f"Cotas listas: {photos} fotos." if photos else "Cotas de soldadura listas."
    return "AWIS terminó."


def _valor(output: str, prefix: str) -> str:
    found = ""
    for linea in output.splitlines():
        texto = linea.strip()
        if texto.startswith(prefix):
            found = texto.split(":", 1)[-1].strip()
    return found


def _decode(data: bytes | str | None) -> str:
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    return data.decode("utf-8", errors="replace")
