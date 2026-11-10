"""Publica JPG al share y registra public.cotas_dossier (fail-soft)."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from acotacion import _dossier_path
from dossier_arbol import cargar_eleccion

_CLASIF = (
    "Corte/Plasma y Laser/Corte metal",
    "Corte/Plasma y Laser/Corte Busbar",
    "Corte/Maquinado/Maquinados metal",
    "Corte/Maquinado/Corte Busbar",
    "Corte/Maquinado/Piezas Soldadas",
    "Corte/Maquinado/Accesorios Sueltos por pieza",
    "Corte/Maquinado/Accesorios Sueltos",
    "Corte/Maquinado/Inspeccion Visual",
    "Doblado/Metal",
    "Doblado/Busbar",
    "Estañado Busbar",
    "SIN CLASIFICACION",
)


CLASIFICACION_WELD = "Weld"


def evidencias_weld(carpeta: str, *, job: str, cliente: str, producto: str) -> list[dict]:
    """Una fila de cotas_dossier por JPG ya publicado en JPGS\\Weld."""
    root = Path(str(carpeta or ""))
    if not root.is_dir():
        return []
    filas = []
    archivos = [src for src in root.glob("*.jpg")]
    archivos.extend(src for src in root.glob("*/*.jpg"))
    for src in sorted(archivos):
        if src.suffix.lower() not in {".jpg", ".jpeg"}:
            continue
        filas.append(
            {
                "cliente": cliente or "SIN_CLIENTE",
                "producto": producto or "",
                "job": job,
                "type": "TYP",
                "cantidad_spoteos": 1,
                "nombre_archivo": src.name,
                "ruta": _canon_unc(str(src)),
                "clasificacion": CLASIFICACION_WELD,
                "seleccionadas": "si",
                "valores": "",
            }
        )
    return filas


def alimentar_weld(carpeta: str, *, job: str, completo: bool = False) -> dict:
    """INSERT/UPDATE de los JPG de soldadura. En corrida completa quita los cordones que ya no están."""
    job = str(job or "").strip()
    root = str(carpeta or "").strip()
    if not job or not root or not Path(root).is_dir():
        return {"ok": False, "count": 0, "message": "BD: sin carpeta Weld o job."}
    eleccion = cargar_eleccion()
    if eleccion and str(eleccion.get("job") or "").casefold() == job.casefold():
        cliente = str(eleccion.get("cliente") or "") or "SIN_CLIENTE"
        producto = str(eleccion.get("producto") or "")
    else:
        cliente, producto = "SIN_CLIENTE", ""
    filas = evidencias_weld(root, job=job, cliente=cliente, producto=producto)
    try:
        import psycopg2
    except ImportError:
        return {"ok": False, "count": 0, "message": "BD: falta psycopg2."}
    target = _db_target()
    if not target:
        return {"ok": False, "count": 0, "message": "BD: sin conexión NestingPro."}
    nombres = [fila["nombre_archivo"] for fila in filas]
    marca = _canon_unc(str(Path(root)))
    n = 0
    try:
        with psycopg2.connect(**target) as conn:
            with conn.cursor() as cur:
                for fila in filas:
                    if _guardar_evidencia(cur, fila):
                        n += 1
                if completo and nombres:
                    cur.execute(
                        """
                        DELETE FROM public.cotas_dossier
                        WHERE job = %s
                          AND clasificacion = %s
                          AND strpos(replace(ruta, '/', '\\'), %s) > 0
                          AND NOT (nombre_archivo = ANY(%s))
                        """,
                        (job, CLASIFICACION_WELD, marca, nombres),
                    )
                elif completo:
                    cur.execute(
                        """
                        DELETE FROM public.cotas_dossier
                        WHERE job = %s
                          AND clasificacion = %s
                          AND strpos(replace(ruta, '/', '\\'), %s) > 0
                        """,
                        (job, CLASIFICACION_WELD, marca),
                    )
            conn.commit()
    except Exception as ex:
        return {"ok": False, "count": n, "message": f"BD: {ex}"}
    return {
        "ok": True,
        "count": n,
        "message": f"BD cotas_dossier: {n} evidencias de soldadura. {root}",
    }


def _guardar_evidencia(cur, fila: dict) -> bool:
    cur.execute(
        """
        SELECT id FROM public.cotas_dossier
        WHERE job = %s AND ruta = %s
        ORDER BY id DESC LIMIT 1
        """,
        (fila["job"], fila["ruta"]),
    )
    prev = cur.fetchone()
    if prev:
        cur.execute(
            """
            UPDATE public.cotas_dossier
            SET cliente = %s, producto = %s, type = %s, cantidad_spoteos = %s,
                nombre_archivo = %s, clasificacion = %s, seleccionadas = %s, valores = %s
            WHERE id = %s
            """,
            (
                fila["cliente"],
                fila["producto"],
                fila["type"],
                fila["cantidad_spoteos"],
                fila["nombre_archivo"],
                fila["clasificacion"],
                fila["seleccionadas"],
                fila["valores"],
                int(prev[0]),
            ),
        )
        return True
    cur.execute(
        """
        INSERT INTO public.cotas_dossier
            (cliente, producto, job, type, cantidad_spoteos,
             nombre_archivo, ruta, clasificacion, seleccionadas, valores)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            fila["cliente"],
            fila["producto"],
            fila["job"],
            fila["type"],
            fila["cantidad_spoteos"],
            fila["nombre_archivo"],
            fila["ruta"],
            fila["clasificacion"],
            fila["seleccionadas"],
            fila["valores"],
        ),
    )
    return True


def alimentar_bd(carpeta_local: str, *, job: str, cfg: dict, hit: dict) -> dict:
    """Copia el árbol a DOSSIER FILES\\JPGS e INSERT/UPDATE cotas_dossier."""
    dossier = str(hit.get("dossier") or _dossier_path(cfg, hit, "", "", job) or "").strip()
    root = str(carpeta_local or "").strip()
    if not job or not root or not Path(root).is_dir():
        return {"ok": False, "count": 0, "message": "BD: sin carpeta local o job."}
    via_planos = _via_planos(root, job=job, cfg=cfg, hit=hit, dossier=dossier)
    if via_planos is not None:
        return via_planos
    return _via_local(root, job=job, hit=hit, dossier=dossier)


def _via_planos(carpeta: str, *, job: str, cfg: dict, hit: dict, dossier: str) -> dict | None:
    planos = Path(str((cfg.get("paths") or {}).get("cotasProject") or "")).resolve()
    if not planos.is_dir():
        return None
    extra = str(planos)
    if extra not in sys.path:
        sys.path.insert(0, extra)
    try:
        from cotas_dossier_registro import (  # type: ignore
            _etiquetas_job_dossier,
            armar_arbol_dossier_jpgs,
            guardar_contexto_dossier,
            publicar_y_sincronizar_dossier,
        )
    except Exception:
        return None
    try:
        if dossier:
            armar_arbol_dossier_jpgs(dossier)
            job_root = str(Path(dossier).parent.parent)
            eleccion = cargar_eleccion()
            if eleccion and str(eleccion.get("job") or "").casefold() == str(job).casefold():
                cli = str(eleccion.get("cliente") or "")
                prod = str(eleccion.get("producto") or "")
            else:
                cli, prev_prod = _etiquetas_job_dossier(job)
                prod = prev_prod or str(hit.get("dossierProduct") or "")
            guardar_contexto_dossier(
                job=job,
                cliente=cli,
                producto=prod,
                job_root=job_root,
                dossier_files=str(Path(dossier).parent),
                dossier_jpgs=dossier,
            )
        n = int(publicar_y_sincronizar_dossier(carpeta, job=job) or 0)
        donde = dossier or carpeta
        return {
            "ok": n > 0,
            "count": n,
            "message": f"BD cotas_dossier: {n} evidencias. {donde}",
        }
    except Exception as ex:
        return {"ok": False, "count": 0, "message": f"BD: {ex}"}


def _via_local(carpeta: str, *, job: str, hit: dict, dossier: str) -> dict:
    try:
        import psycopg2
    except ImportError:
        return {"ok": False, "count": 0, "message": "BD: falta psycopg2."}
    target = _db_target()
    if not target:
        return {"ok": False, "count": 0, "message": "BD: sin conexión NestingPro."}
    n = 0
    eleccion = cargar_eleccion()
    if eleccion and str(eleccion.get("job") or "").casefold() == str(job).casefold():
        cliente = str(eleccion.get("cliente") or "")
        producto = str(eleccion.get("producto") or "")
    else:
        cliente, producto = "", ""
    producto = producto or str(hit.get("dossierProduct") or "")
    cliente = cliente or "SIN_CLIENTE"
    for src in Path(carpeta).rglob("*"):
        if not src.is_file() or src.suffix.lower() not in {".jpg", ".jpeg"}:
            continue
        ruta_db = _publicar(src, dossier) or str(src)
        ruta_db = _canon_unc(ruta_db)
        clase = _proceso(ruta_db)
        if "almacen" in clase.casefold() or "almacén" in clase.casefold():
            continue
        try:
            with psycopg2.connect(**target) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id FROM public.cotas_dossier
                        WHERE job = %s AND ruta = %s
                        ORDER BY id DESC LIMIT 1
                        """,
                        (job, ruta_db),
                    )
                    prev = cur.fetchone()
                    sel = _seleccion(ruta_db, clase)
                    if prev:
                        cur.execute(
                            """
                            UPDATE public.cotas_dossier
                            SET cliente = %s, producto = %s, type = 'TYP', cantidad_spoteos = 1,
                                nombre_archivo = %s, clasificacion = %s, seleccionadas = %s
                            WHERE id = %s
                            """,
                            (cliente, producto, src.name, clase, sel, int(prev[0])),
                        )
                    else:
                        cur.execute(
                            """
                            INSERT INTO public.cotas_dossier
                                (cliente, producto, job, type, cantidad_spoteos,
                                 nombre_archivo, ruta, clasificacion, seleccionadas, valores)
                            VALUES (%s, %s, %s, 'TYP', 1, %s, %s, %s, %s, '')
                            """,
                            (cliente, producto, job, src.name, ruta_db, clase, sel),
                        )
                conn.commit()
            n += 1
        except Exception:
            continue
    donde = dossier or carpeta
    return {
        "ok": n > 0,
        "count": n,
        "message": f"BD cotas_dossier: {n} evidencias. {donde}",
    }


def _publicar(src: Path, dossier: str) -> str:
    if not dossier:
        return ""
    rel = _relativo(src)
    dst = Path(dossier) / rel
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return str(dst)
    except OSError:
        return ""


def _relativo(src: Path) -> str:
    parts = list(src.parts)
    for i, part in enumerate(parts):
        if part.upper() in {
            "PIEZAS_ACOTADAS",
            "COTAS_POR_REFERENCIA",
            "ENSAMBLES_INDEPENDIENTES",
        }:
            return str(Path(*parts[i:]))
    return src.name


_CARAS_TANK = {
    "segm1",
    "segm2",
    "segm3",
    "segm4",
    "top",
    "base",
    "front",
    "back",
    "left",
    "right",
    "bottom",
    "otros",
}


def _seleccion(ruta: str, clase: str) -> str:
    """El VSM de TANKS muestra la fila solo si seleccionadas = si.

    Corte exacto entra a Tank Assembly. Doblado/Metal a Bending.
    Maquinado a Tank Machining. Referencia a Final Dimensions.
    """
    parts = [p.casefold() for p in str(ruta or "").replace("/", "\\").split("\\") if p]
    texto = str(clase or "").casefold()
    if "cotas_por_referencia" in parts or texto == "cotas_por_referencia":
        return "si"
    if texto == "corte":
        return "si"
    if texto.startswith("doblado") and "busbar" not in texto:
        return "si"
    if "maquinado" in texto and "busbar" not in texto:
        return "si"
    if "corte" in parts:
        i = parts.index("corte")
        nxt = parts[i + 1] if i + 1 < len(parts) else ""
        if nxt not in {"plasma y laser", "maquinado"}:
            return "no"
    return "si"


def _proceso(ruta: str) -> str:
    """Clasificación que el VSM de TANKS reconoce.

    Ignora la cara (SEGM / BASE / TOP) y lee la carpeta de proceso.
    No escribe Corte/Plasma y Laser: esa sección no existe en el dossier de tanks.
    """
    raw = str(ruta or "").replace("/", "\\")
    low = raw.casefold()
    if "\\cotas_por_referencia\\" in f"\\{low}\\" or low.endswith("\\cotas_por_referencia"):
        return "COTAS_POR_REFERENCIA"
    if "\\ensambles_independientes\\" in f"\\{low}\\" or low.endswith("\\ensambles_independientes"):
        return "ENSAMBLES_INDEPENDIENTES"
    for item in sorted(_CLASIF, key=len, reverse=True):
        needle = item.replace("/", "\\").casefold()
        if needle in low:
            return item
    parts = [p.casefold() for p in raw.split("\\") if p]
    if "jpgs" in parts:
        parts = parts[parts.index("jpgs") + 1 :]
    while parts and parts[0] in {"piezas_acotadas", "board"}:
        parts = parts[1:]
    while parts and parts[0] in _CARAS_TANK:
        parts = parts[1:]
    if not parts:
        return ""
    proc = parts[0]
    if proc == "doblado":
        if any("busbar" in p for p in parts):
            return "Doblado/Busbar"
        return "Doblado/Metal"
    if proc == "maquinado":
        if any("busbar" in p for p in parts):
            return "Corte/Maquinado/Corte Busbar"
        return "Maquinado"
    if proc in {"corte", "armado"}:
        return "Corte"
    return ""


def _canon_unc(ruta: str) -> str:
    raw = str(ruta or "").replace("/", "\\")
    marker = "ARGA METALS CORPORATE SYSTEM"
    idx = raw.upper().find(marker)
    if idx < 0:
        return raw
    if raw.upper().startswith("\\\\192.168.2.80\\"):
        return raw
    rest = raw[idx + len(marker) :].lstrip("\\")
    unc = (
        r"\\192.168.2.80\Users\Administrator\Desktop\Grupo Arga Metals"
        r"\ARGA METALS CORPORATE SYSTEM"
    )
    return unc + (("\\" + rest) if rest else "")


def _db_target() -> dict | None:
    try:
        from catalog import _nesting_target

        block = _nesting_target()
        if block and block.get("host"):
            return {
                "host": block["host"],
                "port": int(block.get("port") or 5433),
                "dbname": block.get("dbname") or block.get("database"),
                "user": block.get("user") or "postgres",
                "password": block.get("password") or "",
                "connect_timeout": 5,
            }
    except Exception:
        pass
    host = os.environ.get("NESTING_DB_HOST", "192.168.2.80").strip()
    if not host:
        return None
    return {
        "host": host,
        "port": int(os.environ.get("NESTING_DB_PORT", "5433") or "5433"),
        "dbname": os.environ.get("NESTING_DB_NAME", "nestingpro_db"),
        "user": os.environ.get("NESTING_DB_USER", "postgres"),
        "password": os.environ.get("NESTING_DB_PASSWORD", "nesting123"),
        "connect_timeout": 5,
    }
