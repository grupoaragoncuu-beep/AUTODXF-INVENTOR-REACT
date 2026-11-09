"""Snapshot liviano del tanque para COTAS_POR_REFERENCIA (lo único que habla con Inventor).

Por .ipt único: trazos de aristas (`CalculateStrokes`) y facetas (`CalculateFacets`) en
cm de pieza. Por instancia: matriz, muro (bolsas de Confirmar muros, sesión cruda) y si
es placa. Los .ipt se guardan en caché por ruta y fecha: la segunda corrida solo lee
matrices.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import time
from pathlib import Path

from inventor_session import _name, _occ_key

TOL_TRAZO_CM = 0.01
TOL_FACETA_CM = 0.02
CACHE_VERSION = 2


def _cache_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    d = Path(base) / "AutoDXF" / "geo_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _clave(texto) -> str:
    return str(texto or "").replace("\\", "/").strip().lower()


def _r(vals, nd: int = 5) -> list[float]:
    return [round(float(x), nd) for x in vals]


def _cuerpo_crudo(body) -> dict:
    """Trazos y facetas de un solo sólido, índices 1-based de ese cuerpo."""
    sv: list[float] = []
    si: list[int] = []
    fv: list[float] = []
    fi: list[int] = []
    try:
        res = body.CalculateStrokes(TOL_TRAZO_CM, 0, 0, [], [])
        sv.extend(_r(res[2]))
        si.extend(int(i) for i in res[-1])
    except Exception:
        pass
    try:
        res = body.CalculateFacets(TOL_FACETA_CM, 0, 0, [], [], [])
        fv.extend(_r(res[2], 4))
        fi.extend(int(i) for i in res[-1])
    except Exception:
        pass
    return {"sv": sv, "si": si, "fv": fv, "fi": fi}


def _pegar(dest: dict, raw: dict) -> None:
    bsv = len(dest["sv"]) // 3
    bfv = len(dest["fv"]) // 3
    dest["sv"].extend(raw["sv"])
    dest["si"].extend(int(i) + bsv for i in raw["si"])
    dest["fv"].extend(raw["fv"])
    dest["fi"].extend(int(i) + bfv for i in raw["fi"])


def _cuerpos(doc) -> list:
    try:
        bodies = doc.ComponentDefinition.SurfaceBodies
        return [bodies.Item(i) for i in range(1, int(bodies.Count) + 1)]
    except Exception:
        return []


def _def_cruda(doc) -> dict:
    dest = {"sv": [], "si": [], "fv": [], "fi": []}
    for body in _cuerpos(doc):
        _pegar(dest, _cuerpo_crudo(body))
    return dest


def cuerpos_crudos(doc) -> list[dict]:
    """Un snapshot por sólido, para quedarse con la lámina y dejar fuera lo que va encima."""
    out = []
    for body in _cuerpos(doc):
        raw = _cuerpo_crudo(body)
        if raw["sv"] or raw["fv"]:
            out.append(raw)
    return out


def _def_con_cache(doc, stats: dict) -> dict:
    path = str(getattr(doc, "FullFileName", "") or "")
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = 0.0
    try:
        dirty = bool(doc.Dirty)
    except Exception:
        dirty = False
    firma = f"{CACHE_VERSION}|{_clave(path)}|{mtime:.0f}|{TOL_TRAZO_CM}|{TOL_FACETA_CM}"
    archivo = _cache_dir() / (hashlib.sha1(firma.encode("utf-8")).hexdigest() + ".json.gz")
    usar_cache = bool(mtime) and not dirty
    if usar_cache and archivo.is_file():
        try:
            with gzip.open(archivo, "rt", encoding="utf-8") as fh:
                raw = json.load(fh)
            stats["cache"] += 1
            return raw
        except Exception:
            pass
    raw = _def_cruda(doc)
    stats["nuevas"] += 1
    if usar_cache:
        try:
            with gzip.open(archivo, "wt", encoding="utf-8") as fh:
                json.dump(raw, fh, separators=(",", ":"))
        except Exception:
            pass
    return raw


def _bolsas(assembly) -> dict[str, tuple[str, bool]]:
    """ruta_ocurrencia → (cara, placa) desde la sesión guardada de Confirmar muros."""
    try:
        from roles_inventor import _ruta_iam, load_session
        from roles_muros import bags_ensamble

        bags = load_session(assembly).get("bags") or bags_ensamble(_ruta_iam(assembly)) or {}
    except Exception:
        bags = {}
    out: dict[str, tuple[str, bool]] = {}
    for cara, miembros in bags.items():
        if not isinstance(miembros, list):
            continue
        for m in miembros:
            ruta = _clave(m.get("ruta_ocurrencia")) if isinstance(m, dict) else ""
            if ruta:
                out.setdefault(ruta, (str(cara).upper(), bool(m.get("placa_rol"))))
    return out


def _centro_tanque(assembly) -> list[float] | None:
    try:
        box = assembly.ComponentDefinition.RangeBox
        return [(float(box.MinPoint.X) + float(box.MaxPoint.X)) / 2, (float(box.MinPoint.Y) + float(box.MaxPoint.Y)) / 2, (float(box.MinPoint.Z) + float(box.MaxPoint.Z)) / 2]
    except Exception:
        return None


def _matriz(occ) -> list[list[float]] | None:
    try:
        m = occ.Transformation
        try:
            datos = m.GetMatrixData([0.0] * 16)
            if isinstance(datos, (list, tuple)) and len(datos) == 16:
                d = [float(x) for x in datos]
                return [d[0:4], d[4:8], d[8:12]]
        except Exception:
            pass
        return [[float(m.Cell(r, c)) for c in range(1, 5)] for r in range(1, 4)]
    except Exception:
        return None


def _tipo(stem: str) -> str:
    return re.sub(r"_\d+$", "", Path(stem or "TIPO").stem.strip() or "TIPO")


def capturar(assembly, progreso=None) -> dict:
    """Geometría mínima del tanque abierto, lista para `referencia_geo.exportar`."""
    t0 = time.time()
    bolsas = _bolsas(assembly)
    try:
        leaves = assembly.ComponentDefinition.Occurrences.AllLeafOccurrences
        total = int(leaves.Count)
    except Exception:
        return {"occs": [], "defs": {}, "anclas": {}}
    stats = {"cache": 0, "nuevas": 0}
    defs: dict[str, dict] = {}
    tipos: dict[str, str] = {}
    occs = []
    anclas: dict[str, str] = {}
    for i in range(1, total + 1):
        try:
            occ = leaves.Item(i)
            if bool(occ.Suppressed):
                continue
            doc = occ.Definition.Document
            nombre = str(occ.Name)
            key = _clave(_occ_key(occ)) or nombre.lower()
            dkey = _clave(doc.FullFileName)
        except Exception:
            continue
        if dkey not in defs:
            if callable(progreso):
                progreso(i, total, Path(dkey).name)
            defs[dkey] = _def_con_cache(doc, stats)
            tipos[dkey] = _tipo(_name(doc) or nombre.split(":")[0])
        m = _matriz(occ)
        if m is None:
            continue
        cara, placa = bolsas.get(key, ("", False))
        occs.append({"key": key, "def": dkey, "m": m, "name": nombre, "tipo": tipos[dkey], "cara": cara, "placa": placa})
        if placa and cara and cara not in anclas:
            anclas[cara] = key
    return {
        "version": CACHE_VERSION,
        "assembly": str(getattr(assembly, "FullFileName", "") or ""),
        "centro_tanque": _centro_tanque(assembly),
        "anclas": anclas,
        "occs": occs,
        "defs": defs,
        "stats": {**stats, "occs": len(occs), "segundos": round(time.time() - t0, 2)},
    }


def guardar(snap: dict, dest: str | Path) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(dest, "wt", encoding="utf-8") as fh:
        json.dump(snap, fh, separators=(",", ":"))
    return dest
