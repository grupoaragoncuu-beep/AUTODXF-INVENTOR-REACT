"""Ejecuta Acotación JPG de gabinete: geometría de Inventor + dibujo Pillow."""

from __future__ import annotations

import math
import os
from pathlib import Path

from acotacion import classify_assembly, ensure_dir, load_acotacion, local_jpg_dir
from acotacion_progress import reset_progress, write_progress
from job_id import resolve_job
from drawing_bend import save_bend_drawing
from drawing_focus import save_focus_drawing, save_leg_drawing, save_thk_drawing
from drawing_iso import save_iso_drawing
from caras_referencia import ORDEN_CARAS, collect_caras, exportar_cara, mapa_ipt_cara
from drawing_jpg import list_face_cotas, plan_focuses, save_part_drawing
from mesh_view import save_iso_mesh, silhouette, tessellate_document, tessellate_part
from cotas_dossier import alimentar_bd
from photo_layout import _safe as _safe_folder, ensure_tree, folder_dir, slot_dir
from inventor_session import (
    _active_assembly,
    _board_code,
    _classes,
    _classification,
    _copper_busbar,
    _full_name,
    _inventor,
    _name,
    _short,
)

ROOT = Path(__file__).resolve().parents[1]
_CARA_IPT: dict[str, str] = {}


def run_acotacion(payload: dict | None = None) -> dict:
    payload = payload or {}
    cfg = payload.get("config") if isinstance(payload.get("config"), dict) else load_acotacion()
    mode = str(payload.get("mode") or "BOARD").upper()
    limit = int(payload.get("limit") or 0)
    try:
        inv = _inventor()
    except Exception as ex:
        return _finish_progress({"ok": False, "message": str(ex), "files": [], "count": 0})
    assembly = _active_assembly(inv)
    if assembly is None:
        return _finish_progress({"ok": False, "message": "Abre un ensamble (.iam) en Inventor.", "files": [], "count": 0})

    name = _name(assembly)
    path = _full_name(assembly)
    job = resolve_job(str(payload.get("job") or payload.get("jobName") or ""), name, path)
    hit = classify_assembly(name, path, cfg, job)
    prueba = limit > 0
    forzar_gabinete = mode == "BOARD"
    if mode == "TANQUE":
        tipo_flujo = "TANQUE"
    elif forzar_gabinete or prueba:
        tipo_flujo = "BOARD"
    else:
        tipo_flujo = str(hit.get("tipo") or "BOARD")
    flow = (cfg.get("flows") or {}).get(tipo_flujo) or {}
    unit = str(flow.get("unit") or hit.get("unit") or "mm")
    omit = {str(item).strip().lower() for item in (flow.get("omit") or ["Almacén"])}
    corte_cfg = flow.get("corte") if isinstance(flow.get("corte"), dict) else {}
    only_classes = None
    hole_anchor = "center"
    measure_walls = True
    if tipo_flujo == "TANQUE":
        names = corte_cfg.get("classes") or [
            "Maquinados Tank",
            "Maquinados Accesorios Sueltos",
            "Corte",
            "Maquinado",
            "Maquinados",
            "Accesorios Sueltos",
        ]
        only_classes = {str(item).strip().casefold() for item in names if str(item).strip()}
        hole_anchor = str(corte_cfg.get("holeAnchor") or "edge").lower()
        measure_walls = bool(corte_cfg.get("measureWalls", False))
    wanted = {str(item.get("id") or "").upper() for item in (cfg.get("measures") or []) if item.get("enabled")}
    if not wanted:
        wanted = {"LENGTH", "WIDTH", "THK", "HOLE"}

    dest_root, jpg_note = _output_dir(cfg, name, path, hit, job)

    def finish(result: dict) -> dict:
        if jpg_note:
            text = str(result.get("message") or "").rstrip()
            result["message"] = f"{text}\n{jpg_note}" if text else jpg_note
        result.setdefault("folder", str(dest_root))
        return _finish_progress(result)

    global _CARA_IPT
    _CARA_IPT = {}
    files: list[str] = []
    errors: list[str] = []
    sources: list[str] = []
    use_flat = bool(flow.get("despliegue", True))
    board = _board_code(str(payload.get("board") or "B1"))
    layout = cfg.get("photoLayout")
    if tipo_flujo == "TANQUE":
        photos = dest_root / "PIEZAS_ACOTADAS"
        photos.mkdir(parents=True, exist_ok=True)
        dir_f = dir_b = dir_iso = photos
    else:
        photos = ensure_tree(dest_root, layout)
        dir_f = slot_dir(dest_root, layout, "F")
        dir_b = slot_dir(dest_root, layout, "B")
        dir_iso = slot_dir(dest_root, layout, "ISO")
    phase = str(payload.get("phase") or ("ALL" if tipo_flujo == "TANQUE" else "")).upper()
    extra_tanque = ""
    solo_referencia_geo = False

    if tipo_flujo == "TANQUE":
        if phase not in {"CORTE", "DOBLADO", "ARMADO", "REFERENCIA", "ALL"}:
            phase = "ALL"
        pieces = []
        ref_cfg = flow.get("referencia") if isinstance(flow.get("referencia"), dict) else {}
        faces_cfg = ref_cfg.get("faces") if isinstance(ref_cfg.get("faces"), dict) else None
        try:
            _CARA_IPT = mapa_ipt_cara(assembly, faces_cfg) if phase != "REFERENCIA" else {}
        except Exception:
            _CARA_IPT = {}
        doblado_cfg = flow.get("doblado") if isinstance(flow.get("doblado"), dict) else {}
        doblado_classes = {
            str(item).strip().casefold()
            for item in (doblado_cfg.get("classes") or ["Doblado"])
            if str(item).strip()
        }
        ancla_paths = _ancla_ipt_paths(assembly, faces_cfg) if phase != "REFERENCIA" else set()
        if phase in {"CORTE", "DOBLADO", "ALL"}:
            all_parts = _unique_parts(assembly, omit, None)
            jobs = _jobs_tanque(
                all_parts,
                only_classes,
                phase,
                limit,
                doblado_classes,
                cara_map=_CARA_IPT,
                ancla_paths=ancla_paths,
            )
            if not jobs:
                if phase != "ALL":
                    if phase == "DOBLADO":
                        msg = (
                            "No hay piezas de chapa con doblez ni Clasificación Doblado. "
                            "Clasifícalas en Colorimetría o genera Flat Pattern."
                        )
                    else:
                        msg = (
                            "No hay piezas con Clasificación Maquinados Tank, Corte o Accesorios Sueltos. "
                            "Clasifícalas en Colorimetría (iProperty Clasificación)."
                        )
                    return finish({"ok": False, "message": msg, "files": [], "count": 0})
            else:
                d_anchor = str(doblado_cfg.get("holeAnchor") or "edge").lower()
                n_corte = n_doblado = n_maq = 0
                reset_progress(len(jobs), "Listando chapas del tank…")
                for index, (fase, part, qty) in enumerate(jobs, start=1):
                    item = _nombre_jpg(part, tipo_flujo, board)
                    write_progress(
                        current=index,
                        total=len(jobs),
                        piece=item,
                        marca=fase[:1],
                        photos=len(files),
                        phase="piezas",
                    )
                    proceso = _proceso_tank(fase, part)
                    dest = _dir_tank_proceso(dest_root, part, proceso)
                    try:
                        if fase == "CORTE" and proceso == "Maquinado":
                            n_maq += 1
                            _jpg_maquinado(
                                files,
                                errors,
                                sources,
                                part,
                                qty,
                                item,
                                job,
                                unit,
                                dest,
                                wanted=wanted,
                                prueba=prueba,
                            )
                        elif fase == "CORTE":
                            n_corte += 1
                            _jpg_cara(
                                files,
                                errors,
                                sources,
                                part,
                                qty,
                                item,
                                job,
                                unit,
                                dest,
                                prefer_flat=False,
                                hole_anchor=hole_anchor,
                                measure_walls=False,
                                wanted=wanted,
                                prueba=prueba,
                            )
                        else:
                            n_doblado += 1
                            _jpg_doblado(
                                files,
                                errors,
                                sources,
                                part,
                                qty,
                                item,
                                job,
                                unit,
                                dest,
                                hole_anchor=d_anchor,
                                wanted=wanted,
                                prueba=prueba,
                                assembly=assembly,
                            )
                    except Exception as ex:
                        errors.append(f"{item} {fase}: {_short(ex)}")
                pieces.extend(jobs)
                extra_tanque = (
                    f" FASE 1 CORTE: {n_corte} pieza(s); un JPG por cota (X/Y/Ø/SLOT/CUT/LENGTH); a orilla."
                    if n_corte
                    else ""
                )
                if n_maq:
                    extra_tanque += (
                        f" FASE MAQUINADO: {n_maq} pieza(s); vista frontal, Ø / barreno pasado / escalón,"
                        " sin origen; STEP junto al JPG."
                    )
                if n_doblado:
                    extra_tanque += (
                        f" FASE 2 DOBLADO: {n_doblado} chapa(s) (clase Doblado o con doblez); vista alámbrica"
                        f" de la lámina (sin piezas encima) + STEP; un JPG por cota + perfil ID/LEG/THK."
                    )
                elif phase in {"DOBLADO", "ALL"}:
                    extra_tanque += " FASE 2 DOBLADO: 0 chapas (sin clase Doblado y sin Bends detectados)."
        hecho_geo = False
        if phase in {"ARMADO", "REFERENCIA", "ALL"} and _motor_referencia() == "geometria":
            offset = len(pieces)
            dest_ref = dest_root / "COTAS_POR_REFERENCIA"
            try:
                import referencia_geo
                import referencia_snapshot

                reset_progress(offset + 2, "Leyendo geometría del tanque…")

                def _avance_captura(i, total, nombre):
                    write_progress(current=offset + 1, total=offset + 2, piece=nombre, marca="R", photos=len(files), phase="piezas")

                snap = referencia_snapshot.capturar(assembly, progreso=_avance_captura)
                snap["job"], snap["unidad"] = job, unit
                referencia_snapshot.guardar(snap, dest_ref / "_geometria.json.gz")

                def _avance_cara(i, total, cara):
                    write_progress(current=offset + 2, total=offset + 2, piece=cara, marca="R", photos=len(files), phase="piezas")

                res = referencia_geo.exportar(
                    snap, dest_ref, job, unit, files, errors, qty=1, progreso=_avance_cara
                )
            except Exception as ex:
                errors.append(f"REFERENCIA geometría: {_short(ex)}; se usa vista 8711")
                res = {}
            if res:
                hecho_geo = True
                solo_referencia_geo = phase == "REFERENCIA"
                pieces.extend(res.keys())
                extra_tanque += " FASE REFERENCIA (geometría): " + ", ".join(f"{c} {n} tipos" for c, n in res.items()) + "."
                faltan = [c for c in ORDEN_CARAS if c not in res]
                if faltan:
                    extra_tanque += " faltan: " + ", ".join(faltan) + "."
        if phase in {"ARMADO", "REFERENCIA", "ALL"} and not hecho_geo:
            caras = collect_caras(assembly, faces_cfg)
            if limit > 0:
                caras = caras[:limit]
            dest_ref = dest_root / "COTAS_POR_REFERENCIA"
            dest_ref.mkdir(parents=True, exist_ok=True)
            if not caras:
                if phase == "REFERENCIA":
                    return finish(
                        {
                            "ok": False,
                            "message": (
                                "No hay caras TOP/SEGM1–4/BASE para COTAS_POR_REFERENCIA. "
                                "Hace falta un .iam de cara (Segmento 1, Top Cover, Base) o placas IPT S1–S4/BASE/Tank-Lid."
                            ),
                            "files": [],
                            "count": 0,
                        }
                    )
                extra_tanque += " FASE REFERENCIA: 0 caras (sin .iam TOP/SEGM/BASE)."
            else:
                offset = len(pieces)
                reset_progress(offset + len(caras), "Acotando caras de referencia…")
                n_tipos = 0
                detalle = []
                for index, row in enumerate(caras, start=1):
                    cara, assy, qty = row[0], row[1], row[2]
                    ancla_occ = row[3] if len(row) > 3 else None
                    write_progress(
                        current=offset + index,
                        total=offset + len(caras),
                        piece=cara,
                        marca="R",
                        photos=len(files),
                        phase="piezas",
                    )
                    before = len(files)
                    try:
                        n = exportar_cara(
                            files, errors, assy, cara, qty, job, unit, dest_ref, ancla_occ=ancla_occ
                        )
                    except Exception as ex:
                        errors.append(f"{cara}: {_short(ex)}")
                        n = 0
                    tipos = 0
                    cara_dir = dest_ref / cara
                    if cara_dir.is_dir():
                        tipos = sum(1 for p in cara_dir.iterdir() if p.is_dir())
                    n_tipos += tipos
                    detalle.append(f"{cara} {tipos} tipos")
                    _ = n, before
                pieces.extend(caras)
                hay = {c[0] for c in caras}
                faltan = [c for c in ORDEN_CARAS if c not in hay]
                extra_tanque += " FASE REFERENCIA: " + ", ".join(detalle) + "."
                if faltan:
                    extra_tanque += " faltan: " + ", ".join(faltan) + "."
        if phase in {"ARMADO", "ALL"}:
            n_kits = _exportar_armado(
                files,
                errors,
                sources,
                pieces,
                assembly,
                omit,
                flow,
                layout,
                dest_root,
                job,
                unit,
            )
            extra_tanque += (
                f" FASE ARMADO: {n_kits} kit(s); "
                "PIEZAS_ACOTADAS/Armado, X/Y desde el ancla, STEP del .iam y Ø del sólido por hijo."
            )
        if not pieces:
            return finish(
                {
                    "ok": False,
                    "message": (
                        "No hay piezas clasificadas para Corte/Doblado, "
                        "caras para Referencia ni kits Assy Tanks / Assy Loose."
                    ),
                    "files": [],
                    "count": 0,
                }
            )
    else:
        pieces = _unique_parts(assembly, omit)
        extra_tanque = ""
        if limit > 0:
            pieces = pieces[:limit]
        if not pieces:
            return finish(
                {"ok": False, "message": "No hay piezas únicas para acotar (todas Almacén o vacías).", "files": [], "count": 0}
            )
        reset_progress(len(pieces), "Listando piezas únicas…")
        for index, (part, qty) in enumerate(pieces, start=1):
            item = _nombre_jpg(part, tipo_flujo, board)
            write_progress(
                current=index,
                total=len(pieces),
                piece=item,
                marca="F",
                photos=len(files),
                phase="piezas",
            )
            cobre_doblado = _cobre_doblado(part)
            clas = str(_classification(part) or "").strip()
            dir_f_pieza = _dir_f_corte(dest_root, layout, clas) if tipo_flujo == "TANQUE" else dir_f
            if use_flat:
                try:
                    geom_f = _part_geometry(part, unit, use_flat=True)
                except Exception as ex:
                    errors.append(f"{item} F: {_short(ex)}")
                    geom_f = _fallback_geom()
                sources.append(str(geom_f.get("source") or "?"))
                n_feat = sum(1 for row in geom_f["holes"] if row.get("kind") in {"circle", "slot", "arc"})
                if n_feat == 0:
                    errors.append(f"{item}: flat sin barrenos")
                for kind, highlight, value, typ in plan_focuses(geom_f["measures"], geom_f["holes"], wanted, prueba):
                    _ = kind
                    try:
                        files.append(
                            save_part_drawing(
                                _foto_path(dir_f_pieza, part, job, item, "F", por_pieza=True),
                                geom_f["outline"],
                                geom_f["holes"],
                                title=item,
                                subtitle=f"{job}  ·  {hit.get('label')}  ·  qty {qty}  ·  F  ·  {geom_f.get('source')}",
                                unit=unit,
                                measures=geom_f["measures"],
                                highlight=highlight,
                                focus_value=value,
                                typ=typ,
                                hole_anchor=hole_anchor,
                                measure_walls=measure_walls,
                            )
                        )
                    except Exception as ex:
                        errors.append(f"{item} F: {_short(ex)}")
            elif not cobre_doblado:
                try:
                    geom_f = _part_geometry(part, unit, use_flat=False)
                    files.append(
                        save_part_drawing(
                            _foto_path(dir_f_pieza, part, job, item, "F", por_pieza=True),
                            geom_f["outline"],
                            geom_f["holes"],
                            title=item,
                            subtitle=f"{job}  ·  {hit.get('label')}  ·  qty {qty}  ·  F  ·  {geom_f.get('source')}",
                            unit=unit,
                            measures=geom_f["measures"],
                            hole_anchor=hole_anchor,
                            measure_walls=measure_walls,
                        )
                    )
                    sources.append(str(geom_f.get("source") or "3D"))
                except Exception as ex:
                    errors.append(f"{item} F: {_short(ex)}")
            if not cobre_doblado:
                continue
            write_progress(
                current=index,
                total=len(pieces),
                piece=item,
                marca="B",
                photos=len(files),
                phase="piezas",
            )
            mesh = None
            try:
                mesh = tessellate_part(part)
            except Exception as ex:
                errors.append(f"{item} malla: {_short(ex)}")
            try:
                perfil = _perfil_doblez(part, unit, mesh=mesh)
            except Exception as ex:
                errors.append(f"{item} B: {_short(ex)}")
                perfil = None
            if perfil and (perfil.get("segments") or perfil.get("outline")):
                sources.append(str(perfil.get("source") or "perfil"))
                try:
                    files.append(
                        save_bend_drawing(
                            _foto_path(dir_b, part, job, item, "B", por_pieza=True),
                            perfil["outline"],
                            title=item,
                            subtitle=f"{job}  ·  qty {qty}  ·  B",
                            unit=unit,
                            legs=perfil.get("legs") or [],
                            height=float(perfil.get("height") or 0),
                            thk=float(perfil.get("thk") or 0),
                            angles=perfil.get("angles") or [],
                            segments=perfil.get("segments") or [],
                        )
                    )
                except Exception as ex:
                    errors.append(f"{item} B: {_short(ex)}")
            write_progress(
                current=index,
                total=len(pieces),
                piece=item,
                marca="ISO",
                photos=len(files),
                phase="piezas",
            )
            iso_ok = False
            if mesh:
                try:
                    files.append(
                        save_iso_mesh(
                            _foto_path(dir_iso, part, job, item, "ISO", por_pieza=False),
                            mesh,
                            title=item,
                            subtitle=f"{job}  ·  qty {qty}  ·  ISO",
                        )
                    )
                    sources.append("iso-malla")
                    iso_ok = True
                except Exception as ex:
                    errors.append(f"{item} ISO: {_short(ex)}")
            if not iso_ok:
                try:
                    iso = _iso_estanado(part, unit, perfil.get("legs") if perfil else None)
                except Exception as ex:
                    errors.append(f"{item} ISO: {_short(ex)}")
                    iso = None
                if iso and iso.get("edges"):
                    sources.append("iso")
                    try:
                        files.append(
                            save_iso_drawing(
                                _foto_path(dir_iso, part, job, item, "ISO", por_pieza=False),
                                iso["edges"],
                                iso.get("holes") or [],
                                iso.get("balloons") or [],
                                title=item,
                                subtitle=f"{job}  ·  qty {qty}  ·  ISO",
                            )
                        )
                    except Exception as ex:
                        errors.append(f"{item} ISO: {_short(ex)}")

    marker = dest_root / "ultima_salida.txt"
    marker.write_text("\n".join([str(photos), *files[:20]]), encoding="utf-8")
    try:
        abrir = dest_root if tipo_flujo == "TANQUE" else (photos if files else dest_root)
        os.startfile(str(abrir))
    except OSError:
        pass
    extra = ""
    if forzar_gabinete and hit.get("tipo") != "BOARD":
        extra = f" Clasificado como {hit.get('label')}; se ejecutó igual como gabinete (botón Ejecutar gabinete)."
    elif prueba and hit.get("tipo") != "BOARD":
        extra = f" Clasificado como {hit.get('label')}; la prueba corrió igual con lógica de gabinete."
    flat_n = sum(1 for item in sources if item == "despliegue")
    flag = "ON" if use_flat else "OFF"
    if tipo_flujo == "TANQUE":
        extra += extra_tanque
    else:
        extra += f" DESPLIEGUE {flag}: {flat_n}/{len(pieces)} piezas en flat."
    write_progress(
        current=len(pieces),
        total=len(pieces),
        piece="Publicando dossier y BD…",
        marca="",
        photos=len(files),
        phase="bd",
    )
    # PIEZAS_ACOTADAS no cambia en REFERENCIA, y el motor de geometría no toca el modelo.
    # dest_root incluye COTAS_POR_REFERENCIA; photos es solo PIEZAS_ACOTADAS.
    if not solo_referencia_geo:
        try:
            bd = alimentar_bd(str(dest_root), job=job, cfg=cfg, hit=hit)
            extra += " " + str(bd.get("message") or "")
            if bd.get("message") and not bd.get("ok"):
                errors.append(str(bd["message"]))
        except Exception as ex:
            extra += f" BD: {_short(ex)}"
    message = f"Acotación JPG: {len(files)} fotos de {len(pieces)} piezas.{extra}\nCarpeta: {dest_root}"
    if errors:
        message += "\nAvisos: " + "; ".join(errors[:6])
    if not solo_referencia_geo:
        try:
            from roles_inventor import hidratar, last_bags, load_session, pintar_bolsas

            bags = last_bags() or hidratar(assembly, load_session(assembly).get("bags") or {})
            if bags:
                pintar_bolsas(assembly, bags)
        except Exception:
            pass
    return finish({
        "ok": len(files) > 0,
        "message": message,
        "files": files,
        "count": len(files),
        "folder": str(dest_root),
        "tipo": hit.get("tipo"),
        "pieces": len(pieces),
    })


def _finish_progress(result: dict) -> dict:
    total = max(1, int(result.get("pieces") or result.get("count") or 1))
    write_progress(
        current=total,
        total=total,
        piece="Listo" if result.get("ok") else "Terminado con avisos",
        marca="",
        photos=int(result.get("count") or 0),
        phase="listo",
        done=True,
        result=result,
        message=str(result.get("message") or ""),
    )
    return result


def _archivo_jpg(job: str, item: str, marca: str) -> str:
    base = f"{job}__{item}__{marca}"
    for ch in '<>:"/\\|?*':
        base = base.replace(ch, "_")
    return f"{base}.jpg"


def _foto_path(slot: Path, part, job: str, item: str, marca: str, por_pieza: bool) -> Path:
    folder = slot
    if por_pieza:
        folder = _dir_pieza(slot, part, item)
    folder.mkdir(parents=True, exist_ok=True)
    return folder / _archivo_jpg(job, item, marca)


def _dir_pieza(slot: Path, part, item: str) -> Path:
    """Carpeta única por .ipt. En tank la cara/proceso ya vienen en slot."""
    stem = Path(_name(part)).stem or item
    if _CARA_IPT:
        return Path(slot) / _safe_folder(stem)
    parent = Path(_full_name(part) or "").parent.name
    label = stem
    if parent and parent.casefold() not in {stem.casefold(), "assembly", ""}:
        label = f"{stem} ({parent})"
    return Path(slot) / _safe_folder(label)


def _cara_ipt(part) -> str:
    path = str(_full_name(part) or "").replace("\\", "/").lower()
    return str(_CARA_IPT.get(path) or "SIN CARA")


def _proceso_tank(fase: str, part) -> str:
    if str(fase or "").upper() == "DOBLADO":
        return "Doblado"
    keys = _classes(part)
    if "corte" in keys:
        return "Corte"
    if any("almac" in key for key in keys):
        return "Almacén"
    if any("assy" in key or "armado" in key for key in keys):
        return "Armado"
    if keys & {"maquinado", "maquinados", "maquinados accesorios sueltos", "accesorios sueltos"}:
        return "Maquinado"
    return "Corte"


def _dir_tank_proceso(dest_root: Path, part, proceso: str) -> Path:
    cara = _cara_ipt(part)
    folder = Path(dest_root) / "PIEZAS_ACOTADAS" / _safe_folder(cara) / _safe_folder(proceso)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _cobre_doblado(part) -> bool:
    try:
        ok, form, _why = _copper_busbar(part)
        return bool(ok) and form == "B"
    except Exception:
        return False


def _letra_pata(indice: int) -> str:
    n = indice + 1
    texto = ""
    while n:
        n, r = divmod(n - 1, 26)
        texto = chr(65 + r) + texto
    return texto


def _perfil_doblez(part, unit: str, mesh=None) -> dict:
    target = "mm" if str(unit).lower() == "mm" else "in"
    thk = _sheet_thickness(part, unit)
    try:
        uom = part.UnitsOfMeasure
    except Exception:
        uom = None
    look, origin, u_axis, v_axis = _eje_vista_perfil(part, unit)
    if look is None:
        return {"outline": [], "legs": [], "angles": [], "height": 0.0, "thk": thk}
    outline: list = []
    source = "perfil"
    if mesh:
        unit_scale = _to_unit(1.0, uom, target)
        outline, _mask = silhouette(mesh, origin, u_axis, v_axis, look, unit_scale=unit_scale)
        if len(outline) >= 4:
            source = "malla"
    if len(outline) < 4:
        polys = _poligonos_canto(part, look, origin, u_axis, v_axis, uom, target, thk)
        outline = _contorno_opaco(polys, thk)
        if len(outline) < 4:
            outline = _puntos_unicos([p for poly in polys for p in poly])
    outline, u_axis, v_axis = _perfil_apaisado(outline, origin, u_axis, v_axis)
    legs = _patas_de_contorno(outline, thk)
    outline, legs = _orientar_machote(outline, legs, thk)
    legs = _letras_machote(legs)
    xs = [p[0] for p in outline] or [0.0]
    ys = [p[1] for p in outline] or [0.0]
    height = max(ys) - min(ys)
    angles = _angulos_desde_patas(legs)
    inv = _angulos_doblez(part, origin, u_axis, v_axis, uom, target, legs)
    if inv:
        by_i = {i: a for i, a in enumerate(inv)}
        for i, ang in enumerate(angles):
            if i in by_i:
                ang["deg"] = by_i[i]["deg"]
    return {
        "outline": outline,
        "segments": [],
        "legs": legs,
        "angles": angles,
        "height": height,
        "thk": thk,
        "source": source,
    }


def _iso_estanado(part, unit: str, legs: list | None) -> dict:
    target = "mm" if str(unit).lower() == "mm" else "in"
    try:
        uom = part.UnitsOfMeasure
        bodies = part.ComponentDefinition.SurfaceBodies
        body = bodies.Item(1)
        faces = body.Faces
        nfaces = int(faces.Count)
    except Exception:
        return {"edges": [], "holes": [], "balloons": []}
    view = _norm((1.0, 1.0, 1.0))
    up = (0.0, 0.0, 1.0)
    u_axis = _norm(_cross(up, view))
    if abs(_dot(u_axis, u_axis)) < 0.2:
        u_axis = _norm(_cross((0.0, 1.0, 0.0), view))
    v_axis = _norm(_cross(view, u_axis))
    origin = (0.0, 0.0, 0.0)
    try:
        box = part.ComponentDefinition.RangeBox
        origin = (
            (float(box.MinPoint.X) + float(box.MaxPoint.X)) / 2,
            (float(box.MinPoint.Y) + float(box.MaxPoint.Y)) / 2,
            (float(box.MinPoint.Z) + float(box.MaxPoint.Z)) / 2,
        )
    except Exception:
        pass
    edges: list[list[tuple[float, float]]] = []
    holes: list[tuple[float, float, float]] = []
    seen: set[int] = set()
    for fi in range(1, min(nfaces, 200) + 1):
        try:
            face = faces.Item(fi)
            nrm = _normal_cara(face)
            if _dot(nrm, view) <= 0.04:
                continue
            for ei in range(1, int(face.Edges.Count) + 1):
                edge = face.Edges.Item(ei)
                try:
                    key = int(edge.TransientKey)
                except Exception:
                    key = id(edge)
                if key in seen:
                    continue
                seen.add(key)
                pts3 = _muestra_arista(edge)
                if len(pts3) < 2:
                    continue
                edges.append([_proy_uv(p, origin, u_axis, v_axis, uom, target) for p in pts3])
            if int(getattr(face, "SurfaceType", 0)) == 5858 or _es_circulo_cara(face):
                c, rad = _circulo_cara(face, origin, u_axis, v_axis, uom, target)
                if c:
                    holes.append((c[0], c[1], rad))
        except Exception:
            continue
    balloons = _globos_iso(part, origin, u_axis, v_axis, uom, target, legs or [])
    return {"edges": edges, "holes": holes, "balloons": balloons}


def _eje_vista_perfil(part, unit: str):
    """Mirar a lo largo del ANCHO de la solera. El espesor no es un eje del RangeBox plegado."""
    target = "mm" if str(unit).lower() == "mm" else "in"
    try:
        uom = part.UnitsOfMeasure
        try:
            box = part.ComponentDefinition.SurfaceBodies.Item(1).RangeBox
        except Exception:
            box = part.ComponentDefinition.RangeBox
        mn, mx = box.MinPoint, box.MaxPoint
    except Exception:
        return None, None, None, None
    converted = [
        ((1.0, 0.0, 0.0), abs(_to_unit(abs(float(mx.X) - float(mn.X)), uom, target))),
        ((0.0, 1.0, 0.0), abs(_to_unit(abs(float(mx.Y) - float(mn.Y)), uom, target))),
        ((0.0, 0.0, 1.0), abs(_to_unit(abs(float(mx.Z) - float(mn.Z)), uom, target))),
    ]
    ancho_ref = _ancho_solera(part, target)
    if ancho_ref > 0.5:
        converted.sort(key=lambda item: abs(item[1] - ancho_ref))
        look = converted[0][0]
        plano = converted[1:]
        plano.sort(key=lambda item: -item[1])
        u_axis = plano[0][0]
    else:
        converted.sort(key=lambda item: item[1])
        look = converted[1][0] if len(converted) > 1 else converted[0][0]
        u_axis = converted[-1][0]
    origin = (
        (float(mn.X) + float(mx.X)) / 2,
        (float(mn.Y) + float(mx.Y)) / 2,
        (float(mn.Z) + float(mx.Z)) / 2,
    )
    v_axis = _norm(_cross(look, u_axis))
    u_axis = _norm(_cross(v_axis, look))
    return look, origin, u_axis, v_axis


def _ancho_solera(part, target: str) -> float:
    try:
        from inventor_session import _blank_size
        import win32com.client

        sheet = win32com.client.CastTo(part.ComponentDefinition, "SheetMetalComponentDefinition")
        width_in, _length_in = _blank_size(part, sheet)
        return width_in * (25.4 if target == "mm" else 1.0)
    except Exception:
        return 0.0


def _poligonos_canto(part, look, origin, u_axis, v_axis, uom, target, thk: float) -> list[list[tuple[float, float]]]:
    """Caras que miran la cámara (canto del espesor). Sin barrenos de la cara ancha."""
    polys: list[list[tuple[float, float]]] = []
    try:
        faces = part.ComponentDefinition.SurfaceBodies.Item(1).Faces
        total = int(faces.Count)
    except Exception:
        return polys
    for i in range(1, min(total, 180) + 1):
        try:
            face = faces.Item(i)
            if _es_barreno_canto(face, look, thk):
                continue
            nrm = _normal_cara(face)
            cyl_axis = _eje_cilindro(face)
            de_frente = abs(_dot(nrm, look)) > 0.72
            doblez = cyl_axis is not None and abs(_dot(cyl_axis, look)) > 0.8
            if not de_frente and not doblez:
                continue
            loop = None
            for li in range(1, int(face.EdgeLoops.Count) + 1):
                lp = face.EdgeLoops.Item(li)
                if bool(getattr(lp, "IsOuterEdgeLoop", False)) or loop is None:
                    loop = lp
            if loop is None:
                continue
            pts = []
            for ei in range(1, int(loop.Edges.Count) + 1):
                for p in _muestra_arista(loop.Edges.Item(ei), 12):
                    pts.append(_proy_uv(p, origin, u_axis, v_axis, uom, target))
            pts = _puntos_unicos(pts, max(0.25, thk * 0.08))
            if len(pts) < 3:
                continue
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            bw, bh = max(xs) - min(xs), max(ys) - min(ys)
            # el canto es una franja del espesor; la cara ancha se descarta
            if min(bw, bh) > thk * 3.2:
                continue
            polys.append(pts)
        except Exception:
            continue
    return polys


def _es_barreno_canto(face, look, thk: float) -> bool:
    axis = _eje_cilindro(face)
    if axis is None:
        return False
    try:
        rad = abs(_to_unit(float(face.Geometry.Radius), None, "mm"))
    except Exception:
        rad = 0.0
    if rad <= 0:
        return False
    if abs(_dot(axis, look)) > 0.75:
        return False
    return rad < max(thk * 4.0, 18.0)


def _eje_cilindro(face):
    try:
        vec = face.Geometry.AxisVector
        return _norm(_vec(vec))
    except Exception:
        return None


def _contorno_opaco(polys: list[list[tuple[float, float]]], thk: float) -> list[tuple[float, float]]:
    from PIL import Image, ImageDraw, ImageFilter

    pts = [p for poly in polys for p in poly]
    if len(pts) < 3:
        return []
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    span = max(maxx - minx, maxy - miny, thk, 1.0)
    pad = 8
    scale = 520.0 / span
    w = int((maxx - minx) * scale) + pad * 2 + 2
    h = int((maxy - miny) * scale) + pad * 2 + 2
    img = Image.new("L", (max(w, 16), max(h, 16)), 0)
    draw = ImageDraw.Draw(img)
    for poly in polys:
        pix = [((p[0] - minx) * scale + pad, (maxy - p[1]) * scale + pad) for p in poly]
        if len(pix) >= 3:
            draw.polygon(pix, fill=255)
    k = int(max(3, round(thk * scale * 0.9)))
    if k % 2 == 0:
        k += 1
    img = img.filter(ImageFilter.MaxFilter(k))
    img = img.filter(ImageFilter.MinFilter(k))
    contour = _trazar_contorno(img)
    if len(contour) < 4:
        return []
    out = []
    for x, y in contour:
        out.append(((x - pad) / scale + minx, maxy - (y - pad) / scale))
    if out and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) > 0.2:
        out.append(out[0])
    return out


def _trazar_contorno(img) -> list[tuple[int, int]]:
    pix = img.load()
    w, h = img.size
    start = None
    for y in range(h):
        for x in range(w):
            if pix[x, y] > 80:
                start = (x, y)
                break
        if start:
            break
    if start is None:
        return []
    deltas = ((1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1))
    contour = [start]
    cx, cy = start
    prev = 4
    for _ in range(w * h):
        found = None
        for k in range(8):
            d = (prev + k) % 8
            nx, ny = cx + deltas[d][0], cy + deltas[d][1]
            if nx < 0 or ny < 0 or nx >= w or ny >= h:
                continue
            if pix[nx, ny] > 80:
                found = (nx, ny, d)
                break
        if found is None:
            break
        nx, ny, d = found
        if (nx, ny) == start and len(contour) > 8:
            break
        contour.append((nx, ny))
        cx, cy = nx, ny
        prev = (d + 5) % 8
        if len(contour) > 8000:
            break
    step = max(1, len(contour) // 240)
    return contour[::step]


def _erigir_zeta(outline, legs, thk: float):
    """La Z del machote va de pie (HEIGHT grande). La L se deja con el brazo largo horizontal."""
    if len(outline) < 4:
        return outline, legs
    n_h = sum(1 for leg in legs if leg.get("kind") == "H")
    xs, ys = [p[0] for p in outline], [p[1] for p in outline]
    if n_h < 2 or (max(xs) - min(xs)) <= (max(ys) - min(ys)) * 1.05:
        return outline, legs
    rotated = [(p[1], -p[0]) for p in outline]
    return rotated, _patas_de_contorno(rotated, thk)


def _orientar_machote(outline, legs, thk: float):
    """Z de pie, A corta arriba a la derecha, C abajo a la izquierda, B = ancho."""
    outline, legs = _erigir_zeta(outline, legs, thk)
    if len(outline) < 4 or not legs:
        return outline, legs
    vs = [leg for leg in legs if leg.get("kind") == "V"]
    if len(vs) < 2:
        return _orientar_ele(outline, legs, thk)
    top = max(vs, key=lambda leg: float(leg.get("maxy") or 0))
    bot = min(vs, key=lambda leg: float(leg.get("miny") or 0))
    xs = [p[0] for p in outline]
    ys = [p[1] for p in outline]
    if float(top.get("cx") or 0) + 0.5 < float(bot.get("cx") or 0):
        mid = min(xs) + max(xs)
        outline = [(mid - p[0], p[1]) for p in outline]
        legs = _patas_de_contorno(outline, thk)
        vs = [leg for leg in legs if leg.get("kind") == "V"]
        if len(vs) >= 2:
            top = max(vs, key=lambda leg: float(leg.get("maxy") or 0))
            bot = min(vs, key=lambda leg: float(leg.get("miny") or 0))
    if float(top.get("length") or 0) > float(bot.get("length") or 0) + 1.0:
        xs, ys = [p[0] for p in outline], [p[1] for p in outline]
        mx, my = min(xs) + max(xs), min(ys) + max(ys)
        outline = [(mx - p[0], my - p[1]) for p in outline]
        legs = _patas_de_contorno(outline, thk)
    return outline, _completar_alma(outline, legs, thk)


def _orientar_ele(outline, legs, thk: float):
    """L del machote: pata vertical a la derecha, tramo abajo."""
    if len(outline) < 4 or not legs:
        return outline, legs
    vs = [leg for leg in legs if leg.get("kind") == "V"]
    hs = [leg for leg in legs if leg.get("kind") == "H"]
    if len(vs) != 1 or not hs:
        return outline, legs
    xs = [p[0] for p in outline]
    mid = (min(xs) + max(xs)) / 2.0
    if float(vs[0].get("cx") or 0) >= mid - 0.5:
        return outline, legs
    eje = min(xs) + max(xs)
    mirrored = [(eje - p[0], p[1]) for p in outline]
    return mirrored, _patas_de_contorno(mirrored, thk)


def _completar_alma(outline, legs, thk: float) -> list[dict]:
    """En la Z el alma no siempre sale del cluster: B es el ancho de la caja."""
    vs = [leg for leg in legs if leg.get("kind") == "V"]
    if len(vs) < 2 or len(outline) < 4:
        return legs
    xs, ys = [p[0] for p in outline], [p[1] for p in outline]
    minx, maxx = min(xs), max(xs)
    top = max(vs, key=lambda leg: float(leg.get("maxy") or 0))
    bot = min(vs, key=lambda leg: float(leg.get("miny") or 0))
    wy = (float(top.get("miny") or 0) + float(bot.get("maxy") or 0)) / 2.0
    web = {
        "kind": "H",
        "length": maxx - minx,
        "cx": (minx + maxx) / 2.0,
        "cy": wy,
        "minx": minx,
        "maxx": maxx,
        "miny": wy - max(thk, 1.0) / 2.0,
        "maxy": wy + max(thk, 1.0) / 2.0,
    }
    return vs + [web]


def _letras_machote(legs: list[dict]) -> list[dict]:
    """A pata vertical superior, B tramo, C pata vertical inferior. En L: A vertical, B horizontal."""
    if not legs:
        return []
    vs = [leg for leg in legs if leg.get("kind") == "V"]
    hs = [leg for leg in legs if leg.get("kind") == "H"]
    chosen: list[dict] = []
    if len(vs) >= 2 and hs:
        top = max(vs, key=lambda leg: float(leg.get("maxy") or 0))
        bot = min(vs, key=lambda leg: float(leg.get("miny") or 0))
        web = max(hs, key=lambda leg: float(leg.get("length") or 0))
        top["letter"] = "A"
        web["letter"] = "B"
        bot["letter"] = "C"
        chosen = [top, web, bot]
    elif vs and hs:
        vs[0]["letter"] = "A"
        hs[0]["letter"] = "B"
        chosen = [vs[0], hs[0]]
    used = {id(item) for item in chosen}
    extra = [leg for leg in legs if id(leg) not in used]
    extra.sort(key=lambda leg: (float(leg.get("cy") or 0), float(leg.get("cx") or 0)))
    for i, row in enumerate(extra):
        row["letter"] = _letra_pata(len(chosen) + i)
    return chosen + extra


def _angulos_desde_patas(legs: list[dict]) -> list[dict]:
    """Ángulos interiores en el machote: A∠ entre A y B, C∠ entre B y C."""
    by = {str(leg.get("letter") or ""): leg for leg in legs}
    pairs = []
    if "A" in by and "B" in by:
        pairs.append(("A", by["A"], by["B"]))
    if "C" in by and "B" in by:
        pairs.append(("C", by["B"], by["C"]))
    if not pairs and len(legs) >= 2:
        pairs.append((str(legs[0].get("letter") or "A"), legs[0], legs[1]))
    angs = []
    for letter, a, b in pairs:
        if a.get("kind") == "V":
            x = float(a["maxx"]) if float(b.get("cx") or 0) > float(a.get("cx") or 0) else float(a["minx"])
            y = float(b["maxy"]) if float(a.get("cy") or 0) > float(b.get("cy") or 0) else float(b["miny"])
        elif b.get("kind") == "V":
            x = float(b["maxx"]) if float(a.get("cx") or 0) > float(b.get("cx") or 0) else float(b["minx"])
            y = float(a["maxy"]) if float(b.get("cy") or 0) > float(a.get("cy") or 0) else float(a["miny"])
        else:
            x = (float(a["cx"]) + float(b["cx"])) / 2
            y = (float(a["cy"]) + float(b["cy"])) / 2
        angs.append({"letter": letter, "deg": 90.0, "x": x, "y": y})
    return angs


def _perfil_apaisado(outline, origin, u_axis, v_axis):
    if len(outline) < 4:
        return outline, u_axis, v_axis
    xs, ys = [p[0] for p in outline], [p[1] for p in outline]
    if max(ys) - min(ys) <= (max(xs) - min(xs)) * 1.12:
        return outline, u_axis, v_axis
    rotated = [(p[1], -p[0]) for p in outline]
    return rotated, v_axis, tuple(-c for c in u_axis)


def _patas_de_contorno(outline: list[tuple[float, float]], thk: float) -> list[dict]:
    if len(outline) < 4:
        return []
    xs, ys = [p[0] for p in outline], [p[1] for p in outline]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    span_x, span_y = maxx - minx, maxy - miny
    t = max(thk * 1.35, 2.0)
    rows: list[dict] = []
    # barra vertical: espesor en X, largo en Y
    if span_y > t * 2:
        left = [p for p in outline if p[0] <= minx + t * 1.6]
        right = [p for p in outline if p[0] >= maxx - t * 1.6]
        for cluster, side in ((left, "L"), (right, "R")):
            if len(cluster) < 4:
                continue
            cxs, cys = [p[0] for p in cluster], [p[1] for p in cluster]
            bw, bh = max(cxs) - min(cxs), max(cys) - min(cys)
            if bh < t * 2 or bw > t * 3.5:
                continue
            rows.append(
                {
                    "kind": "V",
                    "length": bh,
                    "cx": (min(cxs) + max(cxs)) / 2,
                    "cy": (min(cys) + max(cys)) / 2,
                    "minx": min(cxs),
                    "maxx": max(cxs),
                    "miny": min(cys),
                    "maxy": max(cys),
                    "side": side,
                }
            )
    if span_x > t * 2:
        bands = [
            [p for p in outline if p[1] <= miny + t * 1.6],
            [p for p in outline if p[1] >= maxy - t * 1.6],
            [p for p in outline if miny + t * 2.2 < p[1] < maxy - t * 2.2],
        ]
        for cluster in bands:
            if len(cluster) < 4:
                continue
            cxs, cys = [p[0] for p in cluster], [p[1] for p in cluster]
            bw, bh = max(cxs) - min(cxs), max(cys) - min(cys)
            if bw < t * 2 or bh > t * 3.5:
                continue
            rows.append(
                {
                    "kind": "H",
                    "length": bw,
                    "cx": (min(cxs) + max(cxs)) / 2,
                    "cy": (min(cys) + max(cys)) / 2,
                    "minx": min(cxs),
                    "maxx": max(cxs),
                    "miny": min(cys),
                    "maxy": max(cys),
                }
            )
    # quitar duplicados casi iguales
    uniq: list[dict] = []
    for row in rows:
        if any(abs(row["cx"] - o["cx"]) < t and abs(row["cy"] - o["cy"]) < t and row["kind"] == o["kind"] for o in uniq):
            continue
        uniq.append(row)
    if not uniq:
        return []
    ordered = [uniq[0]]
    rest = uniq[1:]
    while rest:
        last = ordered[-1]
        rest.sort(key=lambda r: math.hypot(r["cx"] - last["cx"], r["cy"] - last["cy"]))
        ordered.append(rest.pop(0))
    for i, row in enumerate(ordered):
        row["letter"] = _letra_pata(i)
    return ordered


def _proy_uv(p, origin, u_axis, v_axis, uom, target: str) -> tuple[float, float]:
    rel = (p[0] - origin[0], p[1] - origin[1], p[2] - origin[2])
    return (
        _to_unit(_dot(rel, u_axis), uom, target),
        _to_unit(_dot(rel, v_axis), uom, target),
    )


def _muestra_arista(edge, n: int = 8) -> list[tuple[float, float, float]]:
    pts: list[tuple[float, float, float]] = []
    try:
        ev = edge.Evaluator
        ext = ev.GetParamExtents()
        lo, hi = float(ext[0]), float(ext[1])
        for i in range(n + 1):
            t = lo + (hi - lo) * i / max(n, 1)
            try:
                pt = ev.GetPointAtParam(t)
                pts.append(_vec(pt if not isinstance(pt, (tuple, list)) else pt))
            except Exception:
                coords = [0.0, 0.0, 0.0]
                try:
                    ev.GetPointAtParam(t, coords)
                    pts.append((float(coords[0]), float(coords[1]), float(coords[2])))
                except Exception:
                    pass
    except Exception:
        pts = []
    if len(pts) < 2:
        for nombre in ("StartVertex", "StopVertex", "EndVertex"):
            try:
                p = getattr(edge, nombre).Point
                pts.append((float(p.X), float(p.Y), float(p.Z)))
            except Exception:
                continue
    return pts


def _puntos_unicos(pts: list[tuple[float, float]], tol: float = 0.35) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for x, y in pts:
        if not (math.isfinite(x) and math.isfinite(y)):
            continue
        if abs(x) > 1e6 or abs(y) > 1e6:
            continue
        if any(math.hypot(x - a, y - b) <= tol for a, b in out):
            continue
        out.append((x, y))
    return out


def _patas_perfil(part, origin, u_axis, v_axis, uom, target, look) -> list[dict]:
    _ = look
    faces = _caras_ancho(part)
    rows = []
    for face in faces:
        pts = []
        try:
            loop = None
            for i in range(1, int(face.EdgeLoops.Count) + 1):
                lp = face.EdgeLoops.Item(i)
                if bool(getattr(lp, "IsOuterEdgeLoop", False)) or loop is None:
                    loop = lp
            if loop is None:
                continue
            for e in range(1, int(loop.Edges.Count) + 1):
                for p in _muestra_arista(loop.Edges.Item(e), 4):
                    pts.append(_proy_uv(p, origin, u_axis, v_axis, uom, target))
        except Exception:
            continue
        pts = _puntos_unicos(pts, 0.8)
        if len(pts) < 2:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        bw = max(xs) - min(xs)
        bh = max(ys) - min(ys)
        if max(bw, bh) < 2.0:
            continue
        kind = "V" if bh >= bw * 0.9 else "H"
        rows.append(
            {
                "kind": kind,
                "length": bh if kind == "V" else bw,
                "cx": (min(xs) + max(xs)) / 2,
                "cy": (min(ys) + max(ys)) / 2,
                "minx": min(xs),
                "maxx": max(xs),
                "miny": min(ys),
                "maxy": max(ys),
            }
        )
    rows.sort(key=lambda r: (r["miny"] + r["maxy"], r["minx"] + r["maxx"]))
    # cadena espacial para A, B, C...
    if not rows:
        return []
    ordered = [rows[0]]
    rest = rows[1:]
    while rest:
        last = ordered[-1]
        rest.sort(key=lambda r: math.hypot(r["cx"] - last["cx"], r["cy"] - last["cy"]))
        ordered.append(rest.pop(0))
    for i, row in enumerate(ordered):
        row["letter"] = _letra_pata(i)
    return ordered


def _caras_ancho(part) -> list:
    out = []
    try:
        faces = part.ComponentDefinition.SurfaceBodies.Item(1).Faces
        total = int(faces.Count)
    except Exception:
        return out
    scored: list[tuple[float, object]] = []
    for i in range(1, min(total, 120) + 1):
        try:
            face = faces.Item(i)
            if int(face.SurfaceType) != 5890:
                continue
            nrm = _normal_cara(face)
            area = _area_caja_cara(face)
            scored.append((area, face, nrm))
        except Exception:
            continue
    if not scored:
        return out
    scored.sort(key=lambda item: item[0], reverse=True)
    tope = scored[0][0] or 1.0
    for area, face, _nrm in scored:
        if area < tope * 0.16:
            continue
        out.append(face)
        if len(out) >= 8:
            break
    return out


def _normal_cara(face) -> tuple[float, float, float]:
    try:
        return _norm(_vec(face.Geometry.Normal))
    except Exception:
        pass
    try:
        ev = face.Evaluator
        params = ev.ParamRangeRect
        u = (float(params[0]) + float(params[1])) / 2
        v = (float(params[2]) + float(params[3])) / 2
        nrm = [0.0, 0.0, 0.0]
        ev.GetNormal((u, v), nrm)
        return _norm((float(nrm[0]), float(nrm[1]), float(nrm[2])))
    except Exception:
        return (0.0, 0.0, 1.0)


def _angulos_doblez(part, origin, u_axis, v_axis, uom, target, legs: list[dict]) -> list[dict]:
    angs: list[dict] = []
    try:
        import win32com.client

        sheet = win32com.client.CastTo(part.ComponentDefinition, "SheetMetalComponentDefinition")
        bends = sheet.Bends
        n = int(bends.Count)
    except Exception:
        n = 0
        bends = None
    for i in range(1, n + 1):
        try:
            bend = bends.Item(i)
            deg = abs(float(bend.Angle.Value) * 180.0 / math.pi)
            if deg > 180:
                deg = 360 - deg
            if deg < 5:
                continue
            x = y = 0.0
            try:
                edge = bend.Edge
                mid = _muestra_arista(edge, 2)
                if mid:
                    x, y = _proy_uv(mid[len(mid) // 2], origin, u_axis, v_axis, uom, target)
            except Exception:
                if i - 1 < len(legs):
                    x, y = float(legs[i - 1]["cx"]), float(legs[i - 1]["cy"])
            letter = _letra_pata(min(i - 1, max(len(legs) - 1, 0)))
            angs.append({"deg": deg, "x": x, "y": y, "letter": letter})
        except Exception:
            continue
    return angs


def _globos_iso(part, origin, u_axis, v_axis, uom, target, legs: list[dict]) -> list[dict]:
    faces = _caras_ancho(part)
    balls = []
    for i, face in enumerate(faces):
        c = _centro_cara(face)
        if c is None:
            continue
        xy = _proy_uv(c, origin, u_axis, v_axis, uom, target)
        letter = legs[i]["letter"] if i < len(legs) else _letra_pata(i)
        dx = 28 + i * 10
        dy = 32 + (i % 2) * 16
        balls.append({"letter": letter, "x": xy[0], "y": xy[1], "tx": xy[0] + dx, "ty": xy[1] + dy})
    return balls


def _centro_cara(face) -> tuple[float, float, float] | None:
    pts = []
    try:
        n = int(face.Edges.Count)
    except Exception:
        return None
    for i in range(1, min(n, 40) + 1):
        try:
            pts.extend(_muestra_arista(face.Edges.Item(i), 2))
        except Exception:
            continue
    if not pts:
        return None
    return (
        sum(p[0] for p in pts) / len(pts),
        sum(p[1] for p in pts) / len(pts),
        sum(p[2] for p in pts) / len(pts),
    )


def _area_caja_cara(face) -> float:
    pts = []
    try:
        n = int(face.Edges.Count)
    except Exception:
        return 0.0
    for i in range(1, min(n, 40) + 1):
        try:
            pts.extend(_muestra_arista(face.Edges.Item(i), 2))
        except Exception:
            continue
    if len(pts) < 3:
        return 0.0
    xs, ys, zs = [p[0] for p in pts], [p[1] for p in pts], [p[2] for p in pts]
    dims = sorted([max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)])
    return dims[-1] * dims[-2]


def _es_circulo_cara(face) -> bool:
    try:
        return int(face.Edges.Count) == 1
    except Exception:
        return False


def _circulo_cara(face, origin, u_axis, v_axis, uom, target):
    try:
        g = face.Geometry
        c = _proy_uv(_vec(g.Center), origin, u_axis, v_axis, uom, target)
        rad = abs(_to_unit(float(g.Radius), uom, target))
        return c, rad
    except Exception:
        return None, 0.0


def _tiene_doblez(part) -> bool:
    try:
        ok, form, _why = _copper_busbar(part)
        if ok:
            return form == "B"
    except Exception:
        pass
    try:
        import win32com.client

        sheet = win32com.client.CastTo(part.ComponentDefinition, "SheetMetalComponentDefinition")
        return int(sheet.Bends.Count) >= 1
    except Exception:
        return False


def _nombre_jpg(part, tipo_flujo: str, board: str) -> str:
    inventor = Path(_name(part)).stem or _name(part)
    if str(tipo_flujo).upper() != "BOARD":
        return inventor
    try:
        ok, form, _why = _copper_busbar(part)
    except Exception:
        return inventor
    if not ok or form not in {"F", "B"}:
        return inventor
    return f"{_board_code(board)}-{form}-{_piece_tail(inventor)}"


def _piece_tail(name: str) -> str:
    chunks = [chunk.strip() for chunk in str(name).replace(".ipt", "").split("-") if chunk.strip()]
    numbered = [chunk for chunk in chunks if not chunk.isalpha()]
    source = numbered if numbered else chunks
    return "-".join(source) if source else name


def _output_dir(cfg: dict, name: str, path: str, hit: dict, job: str = "") -> tuple[Path, str]:
    from job_id import resolve_job

    paths = cfg.get("paths") if isinstance(cfg.get("paths"), dict) else {}
    local, note = local_jpg_dir(str(paths.get("localJpg") or ""))
    dest = ensure_dir(local / resolve_job(job, name, path))
    return dest, note


def _jpg_cara(
    files: list[str],
    errors: list[str],
    sources: list[str],
    part,
    qty,
    item: str,
    job: str,
    unit: str,
    dest_dir: Path,
    *,
    prefer_flat: bool,
    hole_anchor: str,
    measure_walls: bool,
    wanted: set[str],
    prueba: bool,
    omit_assembled_cuts: bool = False,
    allow_flat_fallback: bool = True,
    landscape: bool = True,
    assembly=None,
    alinear_muro: bool = False,
    geom: dict | None = None,
) -> dict:
    """Un JPG por cota de cara (X/Y/Ø/SLOT/CUT/LENGTH). No pisa el mismo archivo."""
    if geom is None:
        geom = _geom_con_features(
            part,
            unit,
            prefer_flat,
            allow_flat_fallback=allow_flat_fallback,
            assembly=assembly,
            alinear_muro=alinear_muro,
        )
        if geom is None:
            errors.append(f"{item}: sin geometría")
            return {}
        if omit_assembled_cuts:
            geom = {**geom, "holes": _filtrar_cortes_ensamblados(geom.get("holes") or [], unit)}
    sources.append(str(geom.get("source") or "?"))
    cotas = list_face_cotas(
        geom.get("outline") or [],
        geom.get("holes") or [],
        geom.get("measures") or {},
        hole_anchor=hole_anchor,
        measure_walls=measure_walls,
        landscape=landscape,
    )
    cotas = _filtrar_cotas(cotas, wanted, prueba)
    if not cotas:
        largo = float((geom.get("measures") or {}).get("LENGTH") or 0)
        if largo > 0.2:
            cotas = [{"kind": "LENGTH", "value": largo, "name": f"LENGTH_{largo:.2f}"}]
    qty_txt = f"qty {qty}" if qty else ""
    if cotas and not prueba:
        folder = _dir_pieza(dest_dir, part, item)
        if folder.is_dir():
            for viejo in folder.glob("*.jpg"):
                try:
                    viejo.unlink()
                except OSError:
                    pass
    for cota in cotas:
        marca = str(cota.get("name") or cota.get("kind") or "COTA")
        try:
            files.append(
                save_part_drawing(
                    _foto_path(dest_dir, part, job, item, marca, por_pieza=True),
                    geom["outline"],
                    geom["holes"],
                    title=f"{item}  {marca}",
                    subtitle=qty_txt,
                    unit=unit,
                    measures=geom["measures"],
                    hole_anchor=hole_anchor,
                    measure_walls=measure_walls,
                    focus=cota,
                    landscape=landscape,
                )
            )
        except Exception as ex:
            errors.append(f"{item} {marca}: {_short(ex)}")
    return geom


def _jpg_maquinado(
    files: list[str],
    errors: list[str],
    sources: list[str],
    part,
    qty,
    item: str,
    job: str,
    unit: str,
    dest_dir: Path,
    *,
    wanted: set[str],
    prueba: bool,
) -> None:
    """Sólido de maquinado: STEP + un JPG por diámetro, barreno o escalón. Sin origen."""
    from maquinado_geo import cotas_de, dibujar, morfologia
    from referencia_geo import preparar_def
    from referencia_snapshot import _def_con_cache
    from step_inventor import exportar_step

    _ = qty, wanted, prueba
    folder = _dir_pieza(dest_dir, part, item)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        morf = morfologia(preparar_def(_def_con_cache(part, {"cache": 0, "nuevas": 0})))
        cotas = cotas_de(morf, unit)
    except Exception as ex:
        errors.append(f"{item} maquinado: {_short(ex)}")
        cotas = []
    if not cotas:
        errors.append(f"{item}: sin morfología de maquinado, se deja el corte 2D")
        _jpg_cara(
            files,
            errors,
            sources,
            part,
            qty,
            item,
            job,
            unit,
            dest_dir,
            prefer_flat=False,
            hole_anchor="edge",
            measure_walls=False,
            wanted=wanted,
            prueba=prueba,
        )
        return
    sources.append("maquinado")
    for viejo in folder.glob("*.jpg"):
        try:
            viejo.unlink()
        except OSError:
            pass
    stem = Path(_name(part)).stem or item
    try:
        exportar_step(part, folder / f"{_safe_folder(stem)}.stp")
    except Exception as ex:
        errors.append(f"{item} STEP: {_short(ex)}")
    for cota in cotas:
        marca = str(cota["name"])
        try:
            files.append(dibujar(_foto_path(dest_dir, part, job, item, marca, por_pieza=True), morf, cota, f"{item}  {marca}"))
        except Exception as ex:
            errors.append(f"{item} {marca}: {_short(ex)}")


def _jpg_doblado(
    files: list[str],
    errors: list[str],
    sources: list[str],
    part,
    qty,
    item: str,
    job: str,
    unit: str,
    dest_dir: Path,
    *,
    hole_anchor: str,
    wanted: set[str],
    prueba: bool,
    assembly=None,
) -> None:
    """Cara de la lámina (vista alámbrica del .ipt, sin lo ensamblado encima) + ID/LEG/THK."""
    wire = _geom_alambrica(part, unit, assembly, errors, item)
    if wire:
        defn = wire.pop("_defn", None)
        marco = wire.pop("_marco", None)
        geom = _jpg_cara(
            files,
            errors,
            sources,
            part,
            qty,
            item,
            job,
            unit,
            dest_dir,
            prefer_flat=False,
            hole_anchor=hole_anchor,
            measure_walls=False,
            wanted=wanted,
            prueba=prueba,
            omit_assembled_cuts=False,
            allow_flat_fallback=False,
            landscape=False,
            assembly=assembly,
            alinear_muro=True,
            geom=wire,
        )
        _vista_y_step(files, errors, part, item, unit, dest_dir, defn, marco)
    else:
        geom = _jpg_cara(
            files,
            errors,
            sources,
            part,
            qty,
            item,
            job,
            unit,
            dest_dir,
            prefer_flat=False,
            hole_anchor=hole_anchor,
            measure_walls=False,
            wanted=wanted,
            prueba=prueba,
            omit_assembled_cuts=True,
            allow_flat_fallback=False,
            landscape=False,
            assembly=assembly,
            alinear_muro=True,
        )
    thk = float(_sheet_thickness(part, unit) or 0)
    if thk <= 0:
        thk = float((geom.get("measures") or {}).get("THK") or 0)
    mesh = None
    try:
        mesh = tessellate_part(part, chord=0.0005)
    except Exception as ex:
        errors.append(f"{item} malla: {_short(ex)}")
    axes = _ejes_doc(part, unit)
    outline = _perfil_en_pie(part, mesh, axes, unit)
    if len(outline) < 3:
        return
    alto_3d = float(axes[1]["size"]) if len(axes) > 1 else 0.0
    ys = [p[1] for p in outline]
    height = max(ys) - min(ys) if ys else 0.0
    if alto_3d < 1 and height > 1:
        alto_3d = height
    xs = [p[0] for p in outline]
    span_x = (max(xs) - min(xs)) if xs else 0.0
    if alto_3d > 0.2:
        try:
            files.append(
                save_focus_drawing(
                    _foto_path(dest_dir, part, job, item, f"ID_{alto_3d:.2f}", por_pieza=True),
                    outline,
                    title=item,
                    unit=unit,
                    value=alto_3d,
                    orient="V",
                )
            )
        except Exception as ex:
            errors.append(f"{item} ID: {_short(ex)}")
    if thk > 0.02:
        try:
            files.append(
                save_thk_drawing(
                    _foto_path(dest_dir, part, job, item, f"THK_{thk:.2f}", por_pieza=True),
                    outline,
                    title=item,
                    unit=unit,
                    thk=thk,
                )
            )
        except Exception as ex:
            errors.append(f"{item} THK: {_short(ex)}")
    if span_x > max(thk * 1.6, 0.2):
        y_hook = min(ys)
        banda = [p for p in outline if p[1] <= y_hook + max(thk * 8, 1.0)]
        if len(banda) >= 2:
            y_hook = max(p[1] for p in banda)
        leg_len = span_x
        try:
            files.append(
                save_leg_drawing(
                    _foto_path(dest_dir, part, job, item, f"LEG_{leg_len:.2f}", por_pieza=True),
                    outline,
                    unit=unit,
                    value=leg_len,
                    xmin=min(xs),
                    xmax=max(xs),
                    y_ref=max(y_hook, min(ys)),
                )
            )
        except Exception as ex:
            errors.append(f"{item} LEG: {_short(ex)}")


def _geom_alambrica(part, unit: str, assembly, errors: list[str], item: str) -> dict | None:
    """Piel de la lámina. None si el snapshot no trae un contorno usable."""
    try:
        from doblado_geo import cara, definicion_lamina

        defn = definicion_lamina(part)
    except Exception as ex:
        errors.append(f"{item} alambrico: {_short(ex)}")
        return None
    if not defn:
        return None
    basis = None
    if assembly is not None:
        try:
            basis = _basis_muro_part(assembly, part)
        except Exception:
            basis = None
        if not basis or basis[0] is None:
            basis = None
    try:
        geom = cara(defn, unit, basis)
    except Exception as ex:
        errors.append(f"{item} alambrico: {_short(ex)}")
        return None
    if not geom or len(geom.get("outline") or []) < 3:
        return None
    outline, holes = _origen_abajo_izquierda(geom["outline"], geom.get("holes") or [])
    geom["outline"] = outline
    geom["holes"] = holes
    xs = [p[0] for p in outline]
    ys = [p[1] for p in outline]
    if xs and ys:
        geom["measures"]["LENGTH"] = round(max(xs) - min(xs), 3)
        geom["measures"]["WIDTH"] = round(max(ys) - min(ys), 3)
    return geom


def _vista_y_step(files, errors, part, item, unit, dest_dir, defn, marco) -> None:
    from doblado_geo import guardar_vista
    from step_inventor import exportar_step

    folder = _dir_pieza(dest_dir, part, item)
    folder.mkdir(parents=True, exist_ok=True)
    if defn is not None and marco is not None:
        try:
            files.append(guardar_vista(defn, marco, folder / "VISTA_ALAMBRICA.jpg", unit))
        except Exception as ex:
            errors.append(f"{item} vista: {_short(ex)}")
    stem = Path(_name(part)).stem or item
    try:
        files.append(str(exportar_step(part, folder / f"{_safe_folder(stem)}.stp")))
    except Exception as ex:
        errors.append(f"{item} STEP: {_short(ex)}")


def _geom_con_features(
    part,
    unit: str,
    prefer_flat: bool,
    allow_flat_fallback: bool = True,
    assembly=None,
    alinear_muro: bool = False,
) -> dict | None:
    last = None
    if prefer_flat:
        order = (True, False) if allow_flat_fallback else (True,)
    else:
        order = (False, True) if allow_flat_fallback else (False,)
    picked = None
    for use_flat in order:
        try:
            cand = _part_geometry(
                part,
                unit,
                use_flat=use_flat,
                assembly=assembly,
                alinear_muro=alinear_muro and not use_flat,
            )
        except Exception:
            continue
        last = cand
        n_feat = sum(
            1
            for row in (cand.get("holes") or [])
            if row.get("kind") in {"circle", "slot", "arc", "cut"} or float(row.get("dia") or 0) > 0
        )
        if n_feat > 0:
            return cand
        if picked is None:
            picked = cand
    return picked or last


def _lazo_es_marcaje(loop, cara=None) -> bool:
    """True si el lazo es marcaje proyectado (split coplanar / sisa rasa), no un corte pasante."""
    try:
        edges = loop.Edges
        total = int(edges.Count)
    except Exception:
        return False
    if total < 3:
        return False
    n_cara = _normal_cara(cara) if cara is not None else None
    splits = 0
    walls = 0
    rasos = 0
    for index in range(1, total + 1):
        try:
            edge = edges.Item(index)
            faces = edge.Faces
            if int(faces.Count) < 2:
                continue
            f0, f1 = faces.Item(1), faces.Item(2)
            n0, n1 = _normal_cara(f0), _normal_cara(f1)
            vecino, n_vecino = f1, n1
            if n_cara is not None and n0 is not None and abs(_dot3(n0, n_cara)) < 0.97:
                vecino, n_vecino = f0, n0
            if n_cara is not None and n_vecino is not None and abs(_dot3(n_vecino, n_cara)) > 0.97:
                splits += 1
                continue
            if n0 is not None and n1 is not None and abs(_dot3(n0, n1)) > 0.97:
                splits += 1
                continue
            walls += 1
            if _span_cara_cm(vecino) < 0.25:
                rasos += 1
        except Exception:
            continue
    if splits > 0 and walls == 0:
        return True
    return walls > 0 and rasos >= max(1, int(walls * 0.6))


def _normal_cara(face) -> tuple[float, float, float] | None:
    try:
        n = face.Geometry.Normal
        vec = (float(n.X), float(n.Y), float(n.Z))
    except Exception:
        return None
    mag = math.sqrt(vec[0] * vec[0] + vec[1] * vec[1] + vec[2] * vec[2]) or 1.0
    return (vec[0] / mag, vec[1] / mag, vec[2] / mag)


def _span_cara_cm(face) -> float:
    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []
    try:
        edges = face.Edges
        total = int(edges.Count)
    except Exception:
        return 1.0
    for index in range(1, total + 1):
        try:
            edge = edges.Item(index)
            for vertex in (edge.StartVertex, edge.StopVertex):
                p = vertex.Point
                xs.append(float(p.X))
                ys.append(float(p.Y))
                zs.append(float(p.Z))
        except Exception:
            continue
    if not xs:
        return 1.0
    return min(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))


def _dot3(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _interior_sin_metal(poly, caras, origin, u_axis, v_axis, uom, target, skip) -> bool:
    """True si el interior del lazo no está tapado por otra cara coplanar (corte pasante)."""
    bb = _bbox2(poly)
    if bb is None:
        return True
    area = max((bb[2] - bb[0]) * (bb[3] - bb[1]), 1e-6)
    for cara in caras or []:
        if cara is skip:
            continue
        try:
            loops = cara.EdgeLoops
            total = int(loops.Count)
        except Exception:
            continue
        for index in range(1, total + 1):
            try:
                loop = loops.Item(index)
                if not bool(getattr(loop, "IsOuterEdgeLoop", False)):
                    continue
                other, _circ = _loop_uv_geom(loop, origin, u_axis, v_axis, uom, target)
            except Exception:
                continue
            obb = _bbox2(other)
            if obb is None:
                continue
            obb_area = max((obb[2] - obb[0]) * (obb[3] - obb[1]), 1e-6)
            cara_in2 = _area_cara(cara) / 6.4516
            if cara_in2 / obb_area < 0.4:
                continue
            ix0, iy0 = max(bb[0], obb[0]), max(bb[1], obb[1])
            ix1, iy1 = min(bb[2], obb[2]), min(bb[3], obb[3])
            if ix1 <= ix0 or iy1 <= iy0:
                continue
            if ((ix1 - ix0) * (iy1 - iy0)) / area >= 0.45:
                return False
    return True


def _bbox2(poly) -> tuple[float, float, float, float] | None:
    pts = [p for p in (poly or []) if len(p) >= 2]
    if len(pts) < 2:
        return None
    xs = [float(p[0]) for p in pts]
    ys = [float(p[1]) for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def _filtrar_cortes_ensamblados(holes: list[dict], unit: str) -> list[dict]:
    """Doblado: la placa derivada hereda siluetas de parches/bases soldadas.

    Se dejan contorno, barrenos, SLOTs y cortes de chapa (ventanas, hendiduras).
    Se quitan islas compactas (3.5×2 parking, 4×4 patches) que no son el recorte de la placa.
    """
    inch = str(unit or "in").lower() != "mm"
    slit_w = 0.8 if inch else 20.0
    slit_l = 5.0 if inch else 120.0
    win_l = 8.0 if inch else 200.0
    win_w = 5.0 if inch else 120.0
    kept: list[dict] = []
    for item in holes or []:
        if str(item.get("kind") or "") != "cut":
            kept.append(item)
            continue
        pts = item.get("pts") or []
        if len(pts) < 3:
            continue
        xs = [float(p[0]) for p in pts if len(p) >= 2]
        ys = [float(p[1]) for p in pts if len(p) >= 2]
        if not xs or not ys:
            continue
        ancho = max(xs) - min(xs)
        alto = max(ys) - min(ys)
        lo, hi = min(ancho, alto), max(ancho, alto)
        if lo < slit_w and hi >= slit_l:
            kept.append(item)
            continue
        if hi >= win_l and lo >= win_w:
            kept.append(item)
            continue
    return kept


def _filtrar_cotas(cotas: list[dict], wanted: set[str], prueba: bool) -> list[dict]:
    keep = {str(k).upper() for k in (wanted or set())}
    if "HOLE" in keep:
        keep |= {"HOLE", "SLOT", "CUT"}
    keep |= {"X", "Y", "LENGTH"}
    rows = [c for c in cotas if str(c.get("kind") or "").upper() in keep and str(c.get("kind") or "").upper() != "WIDTH"]
    if prueba:
        return rows[:1]
    return rows


def _perfil_en_pie(part, mesh, axes: list[dict], unit: str) -> list[tuple[float, float]]:
    outline = _silueta_ranks(part, mesh, axes, look_rank=0, u_rank=1, unit=unit)
    if len(outline) < 4:
        return outline
    xs, ys = [p[0] for p in outline], [p[1] for p in outline]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    if (maxx - minx) > (maxy - miny):
        outline = [(p[1], maxx - p[0]) for p in outline]
    return outline


def _jobs_tanque(
    all_parts,
    only_classes: set[str] | None,
    phase: str,
    limit: int,
    doblado_classes: set[str] | None = None,
    cara_map: dict[str, str] | None = None,
    ancla_paths: set[str] | None = None,
) -> list[tuple[str, object, int]]:
    jobs: list[tuple[str, object, int]] = []
    phase = str(phase or "ALL").upper()
    corte_set = only_classes or set()
    doblado_set = doblado_classes or {"doblado"}
    cara_map = cara_map or {}
    ancla_paths = ancla_paths or set()
    if phase in {"CORTE", "ALL"}:
        corte = [
            (part, qty)
            for part, qty in all_parts
            if _es_pieza_corte(part, corte_set, doblado_set, cara_map, ancla_paths)
        ]
        if limit > 0:
            corte = corte[:limit]
        jobs.extend(("CORTE", part, qty) for part, qty in corte)
    if phase in {"DOBLADO", "ALL"}:
        doblado = [
            (part, qty)
            for part, qty in all_parts
            if _es_pieza_doblado(part, doblado_set, corte_set, cara_map, ancla_paths)
        ]
        if limit > 0:
            doblado = doblado[:limit]
        jobs.extend(("DOBLADO", part, qty) for part, qty in doblado)
    return jobs


def _motor_referencia() -> str:
    """`geometria` (snapshot exacto, por defecto) o `inventor_8711` (capturas, respaldo)."""
    try:
        from caras_referencia import _control_referencia

        motor = str(_control_referencia().get("motor_vista") or "").strip().lower()
    except Exception:
        motor = ""
    return "inventor_8711" if motor == "inventor_8711" else "geometria"


def _ancla_ipt_paths(assembly, faces_cfg=None) -> set[str]:
    paths: set[str] = set()
    try:
        rows = collect_caras(assembly, faces_cfg)
    except Exception:
        return paths
    for row in rows:
        occ = row[3] if len(row) > 3 else None
        if occ is None:
            continue
        try:
            path = str(occ.Definition.Document.FullFileName or "").replace("\\", "/").lower()
        except Exception:
            continue
        if path:
            paths.add(path)
    return paths


def _ipt_path(part) -> str:
    return str(_full_name(part) or "").replace("\\", "/").lower()


def _fase_sin_clasificacion(part, cara_map: dict[str, str], ancla_paths: set[str]) -> str:
    """Sin iProperty Clasificación: paredes S1–S4 = Doblado; el resto = Corte."""
    path = _ipt_path(part)
    cara = str((cara_map or {}).get(path) or "")
    if path in (ancla_paths or set()) and cara in {"SEGM1", "SEGM2", "SEGM3", "SEGM4"}:
        return "DOBLADO"
    if _sheet_con_doblez(part):
        return "DOBLADO"
    return "CORTE"


def _es_pieza_corte(
    part,
    corte_classes: set[str],
    doblado_classes: set[str],
    cara_map: dict[str, str],
    ancla_paths: set[str],
) -> bool:
    clas = _classes(part)
    if clas & corte_classes:
        return True
    if clas:
        return False
    return _fase_sin_clasificacion(part, cara_map, ancla_paths) == "CORTE"


def _es_pieza_doblado(
    part,
    doblado_classes: set[str],
    corte_classes: set[str],
    cara_map: dict[str, str] | None = None,
    ancla_paths: set[str] | None = None,
) -> bool:
    clas = _classes(part)
    if clas & doblado_classes:
        return True
    if clas & corte_classes or clas & {"almacén", "almacen"}:
        return False
    if clas:
        return _sheet_con_doblez(part)
    return _fase_sin_clasificacion(part, cara_map or {}, ancla_paths or set()) == "DOBLADO"


def _sheet_con_doblez(part) -> bool:
    sheet = _sheet_def(part)
    if sheet is None:
        return False
    try:
        if int(sheet.Bends.Count) >= 1:
            return True
    except Exception:
        pass
    try:
        sm = part.ComponentDefinition.Features.SheetMetalFeatures
        for col_name in ("BendFeatures", "ContourFlangeFeatures", "FlangeFeatures", "FoldFeatures"):
            col = getattr(sm, col_name, None)
            if col is not None and int(col.Count) >= 1:
                return True
    except Exception:
        pass
    try:
        if bool(sheet.HasFlatPattern) and int(sheet.FlatPattern.FlatBendResults.Count) >= 1:
            return True
    except Exception:
        pass
    return False


def _dir_f_corte(dest_root: Path, layout, classification: str):
    key = str(classification or "").strip().casefold()
    folder_id = "accesorios_sueltos" if "accesorios" in key else "maquinados_metal"
    return folder_dir(dest_root, layout, folder_id)


def _exportar_armado(
    files: list[str],
    errors: list[str],
    sources: list[str],
    pieces: list,
    assembly,
    omit: set[str],
    flow: dict,
    layout,
    dest_root: Path,
    job: str,
    unit: str,
) -> int:
    """Kits clasificados Assy Tanks / Assy Loose. El Segmento, Top y Base no entran."""
    from armado_kit import es_muro_nombre, exportar_detalle_hijos, exportar_kit
    from step_inventor import exportar_step

    armado_cfg = flow.get("armado") if isinstance(flow.get("armado"), dict) else {}
    classes = {
        str(item).strip().casefold()
        for item in (armado_cfg.get("classes") or ["Assy Tanks", "Assy Loose Accesories"])
        if str(item).strip()
    }
    rows: list[tuple[object, int, str]] = []
    for doc, qty in _unique_subassemblies(assembly, classes, set(omit)):
        nombre = Path(_name(doc)).stem or "kit"
        if es_muro_nombre(nombre):
            errors.append(f"{nombre}: es un muro, no entra a Armado")
            continue
        rows.append((doc, qty, nombre))
    if not rows:
        return 0
    offset = len(pieces)
    reset_progress(offset + len(rows), "Acotando kits Assy…")
    for index, (doc, qty, nombre) in enumerate(rows, start=1):
        item = _safe_folder(nombre)
        write_progress(
            current=offset + index,
            total=offset + len(rows),
            piece=item,
            marca="A",
            photos=len(files),
            phase="piezas",
        )
        clas = str(_classification(doc) or "")
        dest = _dir_armado(dest_root, layout, clas) / item
        dest.mkdir(parents=True, exist_ok=True)
        try:
            exportar_step(doc, dest / f"{item}.stp")
            sources.append("armado-step")
        except Exception as ex:
            errors.append(f"{item} STEP: {_short(ex)}")
        try:
            exportar_kit(files, errors, doc, qty, item, job, unit, dest, dest)
            sources.append("armado")
        except Exception as ex:
            errors.append(f"{item} vistas: {_short(ex)}")
        try:
            if exportar_detalle_hijos(files, errors, doc, job, item, unit, dest):
                sources.append("armado-solido")
        except Exception as ex:
            errors.append(f"{item} sólido: {_short(ex)}")
        pieces.append(item)
    return len(rows)


def _dir_armado(dest_root: Path, layout, classification: str):
    key = str(classification or "").strip().casefold()
    folder_id = "assy_loose" if "loose" in key else "assy_tanks"
    return folder_dir(dest_root, layout, folder_id)


def _unique_subassemblies(assembly, classes: set[str], omit: set[str]) -> list[tuple[object, int]]:
    grouped: dict[str, list] = {}
    try:
        root = str(assembly.FullFileName or "").replace("\\", "/").lower()
    except Exception:
        root = ""

    def walk(occurrences) -> None:
        try:
            total = int(occurrences.Count)
        except Exception:
            return
        for index in range(1, total + 1):
            try:
                occ = occurrences.Item(index)
                if bool(occ.Suppressed):
                    continue
                if int(occ.DefinitionDocumentType) != 12291:
                    continue
                doc = occ.Definition.Document
                key = str(doc.FullFileName or "").replace("\\", "/").lower()
            except Exception:
                continue
            if not key or key == root:
                pass
            else:
                classified = _classes(doc) - omit - {"almacen", "almacén"}
                if classified & classes:
                    grouped.setdefault(key, []).append(doc)
            try:
                walk(occ.SubOccurrences)
            except Exception:
                continue

    try:
        walk(assembly.ComponentDefinition.Occurrences)
    except Exception:
        return []
    rows = [(docs[0], len(docs)) for docs in grouped.values()]
    rows.sort(key=lambda item: _name(item[0]).lower())
    return rows


def _ejes_doc(part, unit: str) -> list[dict]:
    target = "mm" if str(unit).lower() == "mm" else "in"
    try:
        box = part.ComponentDefinition.RangeBox
        uom = part.UnitsOfMeasure
    except Exception:
        return []
    rows = []
    for vec, axis in (((1.0, 0.0, 0.0), "X"), ((0.0, 1.0, 0.0), "Y"), ((0.0, 0.0, 1.0), "Z")):
        raw = abs(float(getattr(box.MaxPoint, axis)) - float(getattr(box.MinPoint, axis)))
        try:
            size = abs(float(uom.ConvertUnits(raw, "cm", target)))
        except Exception:
            size = abs(raw)
        rows.append({"vec": vec, "size": size, "axis": axis})
    rows.sort(key=lambda item: -item["size"])
    return rows


def _silueta_ranks(part, mesh, axes: list[dict], look_rank: int, u_rank: int, unit: str) -> list[tuple[float, float]]:
    if not mesh or len(axes) < 2:
        return []
    look = axes[min(look_rank, len(axes) - 1)]["vec"]
    u_axis = axes[min(u_rank, len(axes) - 1)]["vec"]
    if look == u_axis:
        u_axis = axes[0]["vec"] if look_rank else axes[1]["vec"]
    v_axis = _norm(_cross(look, u_axis))
    u_axis = _norm(_cross(v_axis, look))
    try:
        box = part.ComponentDefinition.RangeBox
        origin = (
            (float(box.MinPoint.X) + float(box.MaxPoint.X)) / 2,
            (float(box.MinPoint.Y) + float(box.MaxPoint.Y)) / 2,
            (float(box.MinPoint.Z) + float(box.MaxPoint.Z)) / 2,
        )
        scale = _to_unit(1.0, part.UnitsOfMeasure, "mm" if str(unit).lower() == "mm" else "in")
    except Exception:
        return []
    outline, _mask = silhouette(mesh, origin, u_axis, v_axis, look, unit_scale=scale, size=1400, min_px=100)
    return outline or []


def _unique_parts(assembly, omit: set[str], only_classes: set[str] | None = None) -> list[tuple[object, int]]:
    grouped: dict[str, list] = {}
    try:
        leaves = assembly.ComponentDefinition.Occurrences.AllLeafOccurrences
        total = int(leaves.Count)
    except Exception:
        return []
    for index in range(1, total + 1):
        try:
            occ = leaves.Item(index)
            if bool(occ.Suppressed):
                continue
            part = occ.Definition.Document
            if int(part.DocumentType) != 12290:
                continue
            key = str(part.FullFileName or "").replace("\\", "/").lower()
            if not key:
                continue
            marked = _classes(part)
            classified = marked - omit - {"almacen", "almacén"}
            if marked and not classified:
                continue
            if only_classes is not None and not classified & only_classes:
                continue
            grouped.setdefault(key, []).append(part)
        except Exception:
            continue
    rows = []
    for parts in grouped.values():
        rows.append((parts[0], len(parts)))
    rows.sort(key=lambda item: _name(item[0]).lower())
    return rows


def _fallback_geom() -> dict:
    return {
        "outline": [(0.0, 0.0), (100.0, 0.0), (100.0, 60.0), (0.0, 60.0)],
        "holes": [],
        "source": "fallback",
        "measures": {"LENGTH": 100.0, "WIDTH": 60.0, "THK": 2.0},
    }


def _part_geometry(part, unit: str, use_flat: bool = True, assembly=None, alinear_muro: bool = False) -> dict:
    thick = _sheet_thickness(part, unit)
    folded = _box_converted(part, unit)
    if use_flat:
        flat = _from_flat(part, unit)
        if flat:
            length = flat["length"]
            width = flat["width"]
            if thick <= 0:
                thick = min(folded) if folded else 2.0
            return {
                "outline": flat["outline"],
                "holes": flat["holes"],
                "source": "despliegue",
                "measures": {
                    "LENGTH": round(length, 3),
                    "WIDTH": round(width, 3),
                    "THK": round(thick, 3),
                    "LEG": round(max(folded) if folded else length, 3),
                },
            }
    length = max(folded)
    width = sorted(folded)[1] if len(folded) > 1 else folded[0]
    if thick <= 0:
        thick = min(folded)
    basis = _basis_muro_part(assembly, part) if alinear_muro and assembly is not None else None
    outline, holes = _silhouette_vertices(part, unit, basis=basis)
    outline, holes = _origen_abajo_izquierda(outline, holes)
    if not _finite_outline(outline):
        outline = [(0.0, 0.0), (length, 0.0), (length, width), (0.0, width)]
        holes = []
    xs = [p[0] for p in outline]
    ys = [p[1] for p in outline]
    if xs and ys:
        length = max(xs) - min(xs)
        width = max(ys) - min(ys)
    return {
        "outline": outline,
        "holes": holes,
        "source": "3D",
        "measures": {
            "LENGTH": round(max(length, 1.0), 3),
            "WIDTH": round(max(width, 1.0), 3),
            "THK": round(max(thick, 0.05), 3),
        },
    }


def _sheet_def(part):
    cdef = part.ComponentDefinition
    try:
        _ = bool(cdef.HasFlatPattern)
        return cdef
    except Exception:
        pass
    import win32com.client

    try:
        return win32com.client.CastTo(cdef, "SheetMetalComponentDefinition")
    except Exception:
        return None


def _sheet_thickness(part, unit: str) -> float:
    sheet = _sheet_def(part)
    if sheet is None:
        return 0.0
    try:
        return abs(_to_unit(float(sheet.Thickness.Value), part.UnitsOfMeasure, "mm" if unit.lower() == "mm" else "in"))
    except Exception:
        return 0.0


def _from_flat(part, unit: str) -> dict | None:
    sheet = _sheet_def(part)
    if sheet is None:
        return None
    try:
        has = bool(sheet.HasFlatPattern)
    except Exception:
        has = False
    if not has:
        try:
            sheet.Unfold()
            try:
                sheet.FlatPattern.ExitEdit()
            except Exception:
                pass
        except Exception:
            return None
    try:
        patron = sheet.FlatPattern
    except Exception:
        return None
    target = "mm" if str(unit).lower() == "mm" else "in"
    uom = part.UnitsOfMeasure
    caja = None
    for getter in (
        lambda: patron.RangeBox,
        lambda: patron.Body.RangeBox,
        lambda: patron.TopFace.Evaluator.RangeBox,
    ):
        try:
            caja = getter()
            if caja is not None:
                break
        except Exception:
            continue
    if caja is None:
        return None
    length, width = _flat_lw(patron, caja, uom, target)
    if length < 1 or width < 1:
        return None
    outline, holes = _extract_flat_2d(patron, caja, uom, target, length, width)
    if outline:
        xs = [p[0] for p in outline]
        ys = [p[1] for p in outline]
        ow, oh = max(xs) - min(xs), max(ys) - min(ys)
        if ow >= length * 0.9 and oh >= width * 0.9:
            length, width = ow, oh
    return {"outline": outline, "holes": holes, "length": length, "width": width}


def _flat_lw(patron, caja, uom, target: str) -> tuple[float, float]:
    dims = sorted(
        abs(_to_unit(float(getattr(caja.MaxPoint, axis)) - float(getattr(caja.MinPoint, axis)), uom, target))
        for axis in ("X", "Y", "Z")
    )
    usable = [d for d in dims if d > 0.2]
    if len(usable) < 2:
        return 0.0, 0.0
    box_w, box_l = usable[-2], usable[-1]
    try:
        api_l = abs(_to_unit(float(patron.Length), uom, target))
        api_w = abs(_to_unit(float(patron.Width), uom, target))
        if min(api_l, api_w) > 1 and abs(max(api_l, api_w) - box_l) / max(box_l, 1) < 0.2:
            return max(api_l, api_w), min(api_l, api_w)
    except Exception:
        pass
    return box_l, box_w


def _extract_flat_2d(patron, caja, uom, target: str, length: float, width: float) -> tuple[list[tuple[float, float]], list[dict]]:
    ox = float(caja.MinPoint.X)
    oy = float(caja.MinPoint.Y)
    span_x = abs(_to_unit(float(caja.MaxPoint.X) - ox, uom, target))
    span_y = abs(_to_unit(float(caja.MaxPoint.Y) - oy, uom, target))
    if span_x < 1:
        span_x = max(length, width)
    if span_y < 1:
        span_y = min(length, width)

    outline: list[tuple[float, float]] = []
    holes: list[dict] = []
    try:
        loops = patron.TopFace.EdgeLoops
        total = int(loops.Count)
    except Exception:
        loops, total = None, 0
    for index in range(1, total + 1):
        try:
            loop = loops.Item(index)
            try:
                is_outer = bool(loop.IsOuterEdgeLoop)
            except Exception:
                is_outer = False
            poly, circles = _loop_xy_geom(loop, ox, oy, uom, target)
            if is_outer:
                if len(poly) >= 3:
                    outline = poly
                continue
            if _lazo_es_marcaje(loop, patron.TopFace):
                continue
            huecos = _huecos_de_lazo(circles, poly)
            if huecos:
                holes.extend(huecos)
            elif len(poly) >= 3:
                holes.append({"kind": "cut", "pts": list(poly)})
        except Exception:
            continue

    holes.extend(_flat_bends_xy(patron, caja, uom, target))
    if not _outline_cubre(outline, span_x, span_y):
        outline = [(0.0, 0.0), (span_x, 0.0), (span_x, span_y), (0.0, span_y)]
    if span_y > span_x + 0.2:
        outline = [(y, span_x - x) for x, y in outline]
        holes = [_rotate_feature(item, span_x) for item in holes]
    outline, holes = _origen_abajo_izquierda(outline, holes)
    return outline, holes


def _origen_abajo_izquierda(outline, holes):
    """El (0,0) debe tocar el metal (cuadrante I), no el aire del bounding box."""
    if len(outline) < 3:
        return outline, holes
    xs = [p[0] for p in outline]
    ys = [p[1] for p in outline]
    min_x, min_y = min(xs), min(ys)
    width = max(xs) - min_x
    height = max(ys) - min_y
    if width < 1 or height < 1:
        return outline, holes
    outline = [(x - min_x, y - min_y) for x, y in outline]
    holes = [_map_xy(item, lambda x, y: (x - min_x, y - min_y)) for item in holes]

    def aplica(fn):
        poly = [fn(x, y) for x, y in outline]
        feats = [_map_xy(item, fn) for item in holes]
        return poly, feats

    candidatos = [
        lambda x, y: (x, y),
        lambda x, y: (width - x, y),
        lambda x, y: (x, height - y),
        lambda x, y: (width - x, height - y),
    ]
    for fn in candidatos:
        poly, feats = aplica(fn)
        if _cero_en_metal(poly):
            return poly, feats
    return outline, holes


def _cero_en_metal(poly, margen: float = 1.6) -> bool:
    if _dist_contorno(0.0, 0.0, poly) <= margen:
        return True
    return _punto_dentro(margen, margen, poly)


def _map_xy(item: dict, fn) -> dict:
    out = dict(item)
    if "x" in out and "y" in out:
        out["x"], out["y"] = fn(float(out["x"]), float(out["y"]))
    for a, b in (("x0", "y0"), ("x1", "y1")):
        if a in out and b in out:
            out[a], out[b] = fn(float(out[a]), float(out[b]))
    if out.get("pts"):
        out["pts"] = [fn(float(p[0]), float(p[1])) for p in out["pts"]]
    return out


def _loop_xy_geom(loop, ox: float, oy: float, uom, target: str):
    poly: list[tuple[float, float]] = []
    circles: list[dict] = []
    for edge, opposed in _edges_ordenadas(loop):
        p0 = _edge_xyz(edge, "start")
        p1 = _edge_xyz(edge, "stop")
        if opposed:
            p0, p1 = p1, p0
        xy0 = _xy(p0, ox, oy, uom, target) if p0 else None
        xy1 = _xy(p1, ox, oy, uom, target) if p1 else None
        circle = _circle_from_edge(edge)
        if circle is not None:
            center, radius, is_arc = circle
            cx, cy = _xy(center, ox, oy, uom, target)
            dia = abs(_to_unit(radius * 2.0, uom, target))
            sweep = None
            try:
                sweep = float(edge.Geometry.SweepAngle)
            except Exception:
                sweep = 2 * math.pi if not is_arc else math.pi
            circles.append(
                {
                    "x": cx,
                    "y": cy,
                    "dia": round(dia, 3),
                    "arc": bool(is_arc or (sweep is not None and 0.3 < abs(sweep) < 6.0)),
                    "sweep": sweep,
                }
            )
            if xy0 and xy1 and dia > 0.4:
                samp = _arco_xy(xy0, xy1, (cx, cy), dia / 2.0)
                if poly:
                    samp = samp[1:]
                poly.extend(samp)
            elif xy1:
                poly.append(xy1)
            continue
        if xy0 and (not poly or math.hypot(poly[-1][0] - xy0[0], poly[-1][1] - xy0[1]) > 0.05):
            poly.append(xy0)
        if xy1:
            poly.append(xy1)
    return _dedupe(poly), circles


def _xyz_to_uv(xyz, origin, u_axis, v_axis, uom, target: str) -> tuple[float, float] | None:
    if not xyz or len(xyz) < 3:
        return None
    rel = (float(xyz[0]) - origin[0], float(xyz[1]) - origin[1], float(xyz[2]) - origin[2])
    x = _to_unit(_dot3(rel, u_axis), uom, target)
    y = _to_unit(_dot3(rel, v_axis), uom, target)
    if not (math.isfinite(x) and math.isfinite(y) and abs(x) < 1e6 and abs(y) < 1e6):
        return None
    return (x, y)


def _loop_uv_geom(loop, origin, u_axis, v_axis, uom, target: str):
    """Igual que el lazo del flat, pero proyectado en la cara 3D (placa doblada)."""
    poly: list[tuple[float, float]] = []
    circles: list[dict] = []
    for edge, opposed in _edges_ordenadas(loop):
        p0 = _edge_xyz(edge, "start")
        p1 = _edge_xyz(edge, "stop")
        if opposed:
            p0, p1 = p1, p0
        xy0 = _xyz_to_uv(p0, origin, u_axis, v_axis, uom, target) if p0 else None
        xy1 = _xyz_to_uv(p1, origin, u_axis, v_axis, uom, target) if p1 else None
        circle = _circle_from_edge(edge)
        if circle is not None:
            center, radius, is_arc = circle
            cxy = _xyz_to_uv(center, origin, u_axis, v_axis, uom, target)
            dia = abs(_to_unit(radius * 2.0, uom, target))
            if cxy and dia > 0.05:
                circles.append({"x": cxy[0], "y": cxy[1], "dia": round(dia, 3)})
            if xy0 and xy1 and cxy and dia > 0.4:
                samp = _arco_xy(xy0, xy1, cxy, dia / 2.0)
                if poly:
                    samp = samp[1:]
                poly.extend(samp)
            elif xy1:
                poly.append(xy1)
            continue
        if xy0 and (not poly or math.hypot(poly[-1][0] - xy0[0], poly[-1][1] - xy0[1]) > 0.05):
            poly.append(xy0)
        if xy1:
            poly.append(xy1)
    return _dedupe(poly), circles


def _edges_ordenadas(loop) -> list:
    try:
        uses = loop.EdgeUses
        total = int(uses.Count)
        rows = []
        for index in range(1, total + 1):
            use = uses.Item(index)
            opposed = False
            try:
                opposed = bool(use.IsOpposedToEdge)
            except Exception:
                pass
            rows.append((use.Edge, opposed))
        if rows:
            return rows
    except Exception:
        pass
    try:
        edges = [loop.Edges.Item(i) for i in range(1, int(loop.Edges.Count) + 1)]
    except Exception:
        return []
    return _encadenar_xyz(edges)


def _encadenar_xyz(edges) -> list:
    if not edges:
        return []

    def key(point):
        if not point:
            return None
        return (round(point[0], 4), round(point[1], 4), round(point[2], 4))

    pending = list(edges[1:])
    chain = [(edges[0], False)]
    cursor = key(_edge_xyz(edges[0], "stop"))
    while pending and cursor:
        found = None
        for item in pending:
            ka = key(_edge_xyz(item, "start"))
            kb = key(_edge_xyz(item, "stop"))
            if ka == cursor:
                found = (item, False, kb)
                break
            if kb == cursor:
                found = (item, True, ka)
                break
        if found is None:
            break
        edge, opposed, cursor = found
        chain.append((edge, opposed))
        pending.remove(edge)
    chain.extend((item, False) for item in pending)
    return chain


def _huecos_de_lazo(circles: list[dict], poly: list | None = None) -> list[dict]:
    """Un lazo interno de Inventor es un solo hueco.

    Barreno real = un lazo cuyo bbox es ~Ø. Ventana/sisa = un lazo 2D (ambos
    lados > 2.4×Ø de los arcos): esos arcos son radios, nunca N barrenos.
    """
    if not circles:
        return []
    grupos = _agrupa_centros(circles)
    if _lazo_es_recorte_2d(grupos, poly):
        return [{"kind": "cut", "pts": list(poly)}]
    if _es_cadena_barrenos(grupos, poly):
        return _barrenos_de_cadena(grupos, poly)
    rows: list[dict] = []
    if len(grupos) == 2:
        a, b = grupos[0], grupos[1]
        dist = math.hypot(a["x"] - b["x"], a["y"] - b["y"])
        dia = (a["dia"] + b["dia"]) / 2
        if dist > max(dia * 0.45, 0.2) and abs(a["dia"] - b["dia"]) <= max(0.2, dia * 0.2):
            rows.append({"kind": "slot", "x0": a["x"], "y0": a["y"], "x1": b["x"], "y1": b["y"], "dia": dia})
            return rows
    for item in grupos:
        rows.append({"kind": "circle", "x": item["x"], "y": item["y"], "dia": item["dia"]})
    return rows


def _lazo_es_recorte_2d(grupos: list[dict], poly: list | None) -> bool:
    """True si el lazo es una abertura 2D: los círculos son filetes, no barrenos."""
    if not poly or len(poly) < 4 or not grupos:
        return False
    xs = [float(p[0]) for p in poly]
    ys = [float(p[1]) for p in poly]
    w = max(xs) - min(xs)
    h = max(ys) - min(ys)
    lo, hi = min(w, h), max(w, h)
    if lo < 0.8 or hi < 1.5:
        return False
    dia = sum(float(g["dia"]) for g in grupos) / len(grupos)
    if dia < 0.12:
        return False
    return lo > dia * 2.4 and hi > dia * 2.4


def _es_cadena_barrenos(grupos: list[dict], poly: list | None) -> bool:
    """3+ Ø iguales, o 2 Ø unidos por un canal más estrecho que el barreno (no es SLOT)."""
    if len(grupos) < 2:
        return False
    dia = sum(float(g["dia"]) for g in grupos) / len(grupos)
    if dia < 0.2:
        return False
    if any(abs(float(g["dia"]) - dia) > max(0.2, dia * 0.2) for g in grupos):
        return False
    if len(grupos) >= 3:
        xs = [float(g["x"]) for g in grupos]
        ys = [float(g["y"]) for g in grupos]
        return (max(xs) - min(xs) > dia * 2 and max(ys) - min(ys) < dia * 0.8) or (
            max(ys) - min(ys) > dia * 2 and max(xs) - min(xs) < dia * 0.8
        )
    cuello = _ancho_canal(poly, grupos[0], grupos[1])
    return cuello is not None and cuello < dia * 0.65


def _barrenos_de_cadena(grupos: list[dict], poly: list | None) -> list[dict]:
    rows = [{"kind": "circle", "x": item["x"], "y": item["y"], "dia": item["dia"]} for item in grupos]
    if poly and len(poly) >= 3:
        rows.append({"kind": "cut", "pts": list(poly), "acota": False})
    return rows


def _ancho_canal(poly: list | None, a: dict, b: dict) -> float | None:
    if not poly or len(poly) < 4:
        return None
    dx = float(b["x"]) - float(a["x"])
    dy = float(b["y"]) - float(a["y"])
    largo = math.hypot(dx, dy)
    if largo < 0.2:
        return None
    ux, uy = dx / largo, dy / largo
    px, py = -uy, ux
    t0, t1 = largo * 0.28, largo * 0.72
    pos: list[float] = []
    neg: list[float] = []
    ax, ay = float(a["x"]), float(a["y"])
    for x, y in _muestras_contorno(poly):
        t = (float(x) - ax) * ux + (float(y) - ay) * uy
        if t < t0 or t > t1:
            continue
        s = (float(x) - ax) * px + (float(y) - ay) * py
        (pos if s >= 0 else neg).append(s)
    if not pos or not neg:
        return None
    return max(pos) - min(neg)


def _muestras_contorno(poly: list, paso: float = 0.4) -> list[tuple[float, float]]:
    closed = list(poly)
    if closed[0] != closed[-1]:
        closed.append(closed[0])
    pts: list[tuple[float, float]] = []
    for i in range(len(closed) - 1):
        x0, y0 = float(closed[i][0]), float(closed[i][1])
        x1, y1 = float(closed[i + 1][0]), float(closed[i + 1][1])
        dist = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(dist / max(paso, 0.05)))
        for k in range(n):
            t = k / n
            pts.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    return pts


def _agrupa_centros(circles: list[dict], tol: float = 0.25) -> list[dict]:
    grupos: list[list[dict]] = []
    for item in circles:
        x, y, dia = float(item["x"]), float(item["y"]), float(item["dia"])
        puesto = False
        for grupo in grupos:
            g = grupo[0]
            radio = max(tol, 0.12 * max(dia, float(g["dia"])))
            if math.hypot(x - float(g["x"]), y - float(g["y"])) <= radio:
                grupo.append(item)
                puesto = True
                break
        if not puesto:
            grupos.append([item])
    out = []
    for grupo in grupos:
        out.append(
            {
                "x": sum(float(c["x"]) for c in grupo) / len(grupo),
                "y": sum(float(c["y"]) for c in grupo) / len(grupo),
                "dia": max(float(c["dia"]) for c in grupo),
            }
        )
    return out


def _xy(point, ox, oy, uom, target: str) -> tuple[float, float]:
    return _to_unit(float(point[0]) - ox, uom, target), _to_unit(float(point[1]) - oy, uom, target)


def _arco_xy(p0, p1, center, radio: float) -> list[tuple[float, float]]:
    a0 = math.atan2(p0[1] - center[1], p0[0] - center[0])
    a1 = math.atan2(p1[1] - center[1], p1[0] - center[0])
    sweep = a1 - a0
    while sweep > math.pi:
        sweep -= 2 * math.pi
    while sweep < -math.pi:
        sweep += 2 * math.pi
    steps = max(4, min(16, int(abs(sweep) * max(radio, 1) / 2) or 4))
    pts = [p0]
    for index in range(1, steps):
        ang = a0 + sweep * index / steps
        pts.append((center[0] + radio * math.cos(ang), center[1] + radio * math.sin(ang)))
    pts.append(p1)
    return pts


def _edge_xyz(edge, which: str):
    names = ("StartVertex", "VertexOne") if which == "start" else ("StopVertex", "EndVertex", "VertexTwo")
    for name in names:
        try:
            p = getattr(edge, name).Point
            return (float(p.X), float(p.Y), float(p.Z))
        except Exception:
            continue
    try:
        ev = edge.Evaluator
        try:
            mn, mx = ev.GetParamExtents()
        except Exception:
            mn, mx = 0.0, 1.0
        t = mn if which == "start" else mx
        pt = ev.GetPointAtParam(t)
        if pt and len(pt) >= 3:
            xyz = (float(pt[0]), float(pt[1]), float(pt[2]))
            if all(math.isfinite(v) and abs(v) < 1e5 for v in xyz):
                return xyz
    except Exception:
        pass
    return None


def _outline_cubre(outline: list[tuple[float, float]], span_u: float, span_v: float) -> bool:
    if len(outline) < 3 or span_u < 1 or span_v < 1:
        return False
    xs = [p[0] for p in outline]
    ys = [p[1] for p in outline]
    ow, oh = max(xs) - min(xs), max(ys) - min(ys)
    return ow >= span_u * 0.88 and oh >= span_v * 0.88


def _inner_circles(patron, origin, u_axis, v_axis, uom, target, min_u, min_v, span_u, span_v, short_side):
    holes: list[dict] = []
    seen: set[tuple[int, int, int]] = set()
    try:
        loops = patron.TopFace.EdgeLoops
        total = int(loops.Count)
    except Exception:
        return holes
    for index in range(1, total + 1):
        try:
            loop = loops.Item(index)
            try:
                if bool(loop.IsOuterEdgeLoop):
                    continue
            except Exception:
                pass
            edges = loop.Edges
            count = int(edges.Count)
        except Exception:
            continue
        for e in range(1, count + 1):
            try:
                edge = edges.Item(e)
            except Exception:
                continue
            circle = _circle_from_edge(edge)
            if circle is None:
                continue
            center, radius, is_arc = circle
            dia = abs(_to_unit(radius * 2.0, uom, target))
            if dia < 1.2 or dia > short_side * 0.55:
                continue
            x, y = _uv(center, origin, u_axis, v_axis, uom, target)
            x, y = x - min_u, y - min_v
            if not (-2 <= x <= span_u + 2 and -2 <= y <= span_v + 2):
                continue
            if is_arc and (x < dia * 0.55 or y < dia * 0.55 or x > span_u - dia * 0.55 or y > span_v - dia * 0.55):
                continue
            key = (int(round(x * 5)), int(round(y * 5)), int(round(dia * 5)))
            if key in seen:
                continue
            seen.add(key)
            holes.append({"kind": "arc" if is_arc else "circle", "x": x, "y": y, "dia": round(dia, 3)})
    return holes


def _fit_blank(
    outline: list[tuple[float, float]],
    holes: list[dict],
    long_side: float,
    short_side: float,
) -> tuple[list[tuple[float, float]], list[dict]]:
    blank_w, blank_h = max(long_side, short_side), min(long_side, short_side)
    if not _outline_cubre(outline, blank_w, blank_h):
        outline = [(0.0, 0.0), (blank_w, 0.0), (blank_w, blank_h), (0.0, blank_h)]
    return outline, holes


def _offset_feat(item: dict, dx: float, dy: float) -> dict:
    out = dict(item)
    for key in ("x", "x0", "x1"):
        if key in out:
            out[key] = float(out[key]) + dx
    for key in ("y", "y0", "y1"):
        if key in out:
            out[key] = float(out[key]) + dy
    if out.get("pts"):
        out["pts"] = [(float(p[0]) + dx, float(p[1]) + dy) for p in out["pts"]]
    return out


def _muesca_arriba(outline, holes, width: float, height: float):
    if len(outline) < 5 or height < 1:
        return outline, holes
    _cx, cy = _centroide(outline)
    if cy <= height * 0.5 + 0.4:
        return outline, holes
    outline = [(width - x, height - y) for x, y in outline]
    rotated = []
    for item in holes:
        out = dict(item)
        if "x" in out and "y" in out:
            out["x"], out["y"] = width - float(out["x"]), height - float(out["y"])
        for a, b in (("x0", "y0"), ("x1", "y1")):
            if a in out and b in out:
                out[a], out[b] = width - float(out[a]), height - float(out[b])
        rotated.append(out)
    return outline, rotated


def _rotate_feature(item: dict, old_w: float) -> dict:
    out = dict(item)
    if "x" in out and "y" in out:
        x, y = float(out["x"]), float(out["y"])
        out["x"], out["y"] = y, old_w - x
    for a, b in (("x0", "y0"), ("x1", "y1")):
        if a in out and b in out:
            x, y = float(out[a]), float(out[b])
            out[a], out[b] = y, old_w - x
    if out.get("pts"):
        out["pts"] = [(p[1], old_w - p[0]) for p in out["pts"]]
    return out


def _flat_bends_xy(patron, caja, uom, target: str) -> list[dict]:
    bends: list[dict] = []
    try:
        ox = float(caja.MinPoint.X)
        oy = float(caja.MinPoint.Y)
        results = patron.FlatBendResults
        total = int(results.Count)
    except Exception:
        return bends
    for index in range(1, total + 1):
        try:
            item = results.Item(index)
            edge = getattr(item, "Edge", None) or getattr(item, "InternalEdge", None)
            if edge is None:
                continue
            p0 = edge.StartVertex.Point
            p1 = edge.EndVertex.Point
            x0, y0 = _xy((float(p0.X), float(p0.Y), float(p0.Z)), ox, oy, uom, target)
            x1, y1 = _xy((float(p1.X), float(p1.Y), float(p1.Z)), ox, oy, uom, target)
            bends.append({"kind": "bend", "x0": x0, "y0": y0, "x1": x1, "y1": y1})
        except Exception:
            continue
    return bends


def _flat_bends_uv(patron, origin, u_axis, v_axis, uom, target, min_u, min_v) -> list[dict]:
    bends: list[dict] = []
    try:
        results = patron.FlatBendResults
        total = int(results.Count)
    except Exception:
        return bends
    for index in range(1, total + 1):
        try:
            item = results.Item(index)
            edge = getattr(item, "Edge", None) or getattr(item, "InternalEdge", None)
            if edge is None:
                continue
            p0 = edge.StartVertex.Point
            p1 = edge.EndVertex.Point
            x0, y0 = _uv((float(p0.X), float(p0.Y), float(p0.Z)), origin, u_axis, v_axis, uom, target)
            x1, y1 = _uv((float(p1.X), float(p1.Y), float(p1.Z)), origin, u_axis, v_axis, uom, target)
            bends.append({"kind": "bend", "x0": x0 - min_u, "y0": y0 - min_v, "x1": x1 - min_u, "y1": y1 - min_v})
        except Exception:
            continue
    return bends


def _uv(point, origin, u_axis, v_axis, uom, target: str) -> tuple[float, float]:
    rel = (float(point[0]) - origin[0], float(point[1]) - origin[1], float(point[2]) - origin[2])
    return _to_unit(_dot(rel, u_axis), uom, target), _to_unit(_dot(rel, v_axis), uom, target)


def _iter_flat_edges(patron):
    faces = []
    for name in ("TopFace", "BottomFace"):
        try:
            faces.append(getattr(patron, name))
        except Exception:
            continue
    try:
        body = patron.Body
        for index in range(1, int(body.Faces.Count) + 1):
            faces.append(body.Faces.Item(index))
    except Exception:
        pass
    seen = set()
    for face in faces:
        try:
            edges = face.Edges
            total = int(edges.Count)
        except Exception:
            continue
        for index in range(1, total + 1):
            try:
                edge = edges.Item(index)
                marker = id(edge)
                if marker in seen:
                    continue
                seen.add(marker)
                yield edge
            except Exception:
                continue


def _circle_from_edge(edge) -> tuple[tuple[float, float, float], float, bool] | None:
    for attr in ("Geometry", "Curve"):
        try:
            geo = getattr(edge, attr)
        except Exception:
            continue
        try:
            center = geo.Center
            radius = abs(float(geo.Radius))
        except Exception:
            continue
        if radius <= 1e-8:
            continue
        try:
            point = (float(center.X), float(center.Y), float(center.Z))
        except Exception:
            if isinstance(center, (tuple, list)) and len(center) >= 3:
                point = (float(center[0]), float(center[1]), float(center[2]))
            else:
                continue
        is_arc = False
        try:
            sweep = abs(float(geo.SweepAngle))
            is_arc = 0.4 < sweep < 5.6
        except Exception:
            try:
                is_arc = int(getattr(geo, "GeometryType", 0) or 0) in {5125, 9218}
            except Exception:
                is_arc = False
        return point, radius, is_arc
    return None


def _cylinders_on_flat(patron, origin, u_axis, v_axis, uom, target, min_u, min_v, span_u, span_v, seen: set) -> list[dict]:
    found: list[dict] = []
    try:
        faces = patron.Body.Faces
        total = int(faces.Count)
    except Exception:
        return found
    normal = _norm(_cross(u_axis, v_axis))
    for index in range(1, total + 1):
        try:
            geo = faces.Item(index).Geometry
            radius = abs(float(geo.Radius))
            axis = _vec(geo.AxisVector)
            base = geo.BasePoint
            base_pt = (float(base.X), float(base.Y), float(base.Z))
        except Exception:
            continue
        denom = _dot(axis, normal)
        if abs(denom) < 1e-8:
            continue
        t = _dot(
            (origin[0] - base_pt[0], origin[1] - base_pt[1], origin[2] - base_pt[2]),
            normal,
        ) / denom
        point = (base_pt[0] + axis[0] * t, base_pt[1] + axis[1] * t, base_pt[2] + axis[2] * t)
        dia = abs(_to_unit(radius * 2.0, uom, target))
        if dia < 1.2 or dia > min(span_u, span_v) * 0.45:
            continue
        x, y = _uv(point, origin, u_axis, v_axis, uom, target)
        x, y = x - min_u, y - min_v
        if not (-2 <= x <= span_u + 2 and -2 <= y <= span_v + 2):
            continue
        key = (int(round(x * 5)), int(round(y * 5)), int(round(dia * 5)))
        if key in seen:
            continue
        seen.add(key)
        found.append({"kind": "circle", "x": x, "y": y, "dia": round(dia, 3)})
    return found


def _slots_from_circles(holes: list[dict]) -> list[dict]:
    slots: list[dict] = []
    used: set[int] = set()
    for i, a in enumerate(holes):
        if a.get("kind") not in {"arc", "circle"} or i in used:
            continue
        for j, b in enumerate(holes):
            if j <= i or b.get("kind") not in {"arc", "circle"} or j in used:
                continue
            if abs(float(a["dia"]) - float(b["dia"])) > 0.4:
                continue
            dist = math.hypot(float(a["x"]) - float(b["x"]), float(a["y"]) - float(b["y"]))
            dia = float(a["dia"])
            limit = dia * 4.2
            if dia * 0.35 < dist < limit:
                used.add(i)
                used.add(j)
                slots.append(
                    {
                        "kind": "slot",
                        "x0": a["x"],
                        "y0": a["y"],
                        "x1": b["x"],
                        "y1": b["y"],
                        "dia": dia,
                    }
                )
                break
    for index, item in enumerate(holes):
        if item.get("kind") == "arc" and index not in used:
            item["kind"] = "circle"
    keep = [item for index, item in enumerate(holes) if index not in used]
    holes.clear()
    holes.extend(keep)
    return slots


def _project_top(part, patron, uom, target: str) -> tuple[list[tuple[float, float]], list[dict]]:
    try:
        face = patron.TopFace
    except Exception:
        return [], []
    origin, u_axis, v_axis = _face_basis(face)
    if origin is None:
        return [], []
    outline: list[tuple[float, float]] = []
    holes: list[dict] = []
    try:
        loops = face.EdgeLoops
        total = int(loops.Count)
    except Exception:
        return [], []
    for index in range(1, total + 1):
        try:
            loop = loops.Item(index)
            pts = _loop_vertices(loop, origin, u_axis, v_axis, uom, target)
            if len(pts) < 3:
                continue
            outer = bool(getattr(loop, "IsOuterEdgeLoop", False))
            if outer or not outline:
                outline = _rect_outline(pts)
            else:
                hole = _as_hole(pts)
                holes.append({"kind": "circle", **hole} if hole else {"kind": "slot", "pts": pts})
        except Exception:
            continue
    return outline, holes


def _box_converted(part, unit: str) -> list[float]:
    target = "mm" if str(unit).lower() == "mm" else "in"
    try:
        box = part.ComponentDefinition.RangeBox
        uom = part.UnitsOfMeasure
        dims = []
        for axis in ("X", "Y", "Z"):
            raw = abs(float(getattr(box.MaxPoint, axis)) - float(getattr(box.MinPoint, axis)))
            dims.append(abs(float(uom.ConvertUnits(raw, "cm", target))))
        usable = sorted(d for d in dims if d > 0.05)
        return usable or [100.0, 60.0, 2.0]
    except Exception:
        return [100.0, 60.0, 2.0]


def _flat_features(part, patron, caja, uom, target: str) -> tuple[list[tuple[float, float]], list[dict]]:
    origin_x = float(caja.MinPoint.X)
    origin_y = float(caja.MinPoint.Y)
    outline: list[tuple[float, float]] = []
    holes: list[dict] = []
    try:
        cara = patron.TopFace
        lazos = cara.EdgeLoops
        total = int(lazos.Count)
    except Exception:
        return outline, holes
    for index in range(1, total + 1):
        try:
            lazo = lazos.Item(index)
            pts = _loop_xy(lazo, origin_x, origin_y, uom, target)
            if len(pts) < 3:
                continue
            outer = bool(getattr(lazo, "IsOuterEdgeLoop", False))
            if outer or not outline:
                outline = _rect_outline(pts)
                continue
            hole = _as_hole(pts)
            if hole:
                holes.append({"kind": "circle", **hole})
            else:
                holes.append({"kind": "slot", "pts": pts})
        except Exception:
            continue
    return outline, holes


def _loop_xy(loop, origin_x: float, origin_y: float, uom, target: str) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    try:
        edges = loop.Edges
        total = min(int(edges.Count), 80)
    except Exception:
        return pts
    for index in range(1, total + 1):
        try:
            edge = edges.Item(index)
            for vertex in (edge.StartVertex, edge.EndVertex):
                p = vertex.Point
                x = _to_unit(float(p.X) - origin_x, uom, target)
                y = _to_unit(float(p.Y) - origin_y, uom, target)
                if math.isfinite(x) and math.isfinite(y) and abs(x) < 1e6 and abs(y) < 1e6:
                    pts.append((x, y))
        except Exception:
            continue
    return _dedupe(pts)


def _flat_bends(patron, caja, uom, target: str) -> list[dict]:
    origin_x = float(caja.MinPoint.X)
    origin_y = float(caja.MinPoint.Y)
    bends: list[dict] = []
    try:
        results = patron.FlatBendResults
        total = int(results.Count)
    except Exception:
        return bends
    for index in range(1, total + 1):
        try:
            item = results.Item(index)
            edge = getattr(item, "Edge", None) or getattr(item, "InternalEdge", None)
            if edge is None:
                continue
            p0 = edge.StartVertex.Point
            p1 = edge.EndVertex.Point
            bends.append(
                {
                    "kind": "bend",
                    "x0": _to_unit(float(p0.X) - origin_x, uom, target),
                    "y0": _to_unit(float(p0.Y) - origin_y, uom, target),
                    "x1": _to_unit(float(p1.X) - origin_x, uom, target),
                    "y1": _to_unit(float(p1.Y) - origin_y, uom, target),
                }
            )
        except Exception:
            continue
    return bends


def _occ_de_part(assembly, part):
    want = str(_full_name(part) or "").replace("\\", "/").lower()
    if not want:
        return None
    try:
        occs = assembly.ComponentDefinition.Occurrences.AllLeafOccurrences
        total = int(occs.Count)
    except Exception:
        return None
    for index in range(1, total + 1):
        try:
            occ = occs.Item(index)
            if bool(occ.Suppressed):
                continue
            path = str(occ.Definition.Document.FullFileName or "").replace("\\", "/").lower()
        except Exception:
            continue
        if path == want:
            return occ
    return None


def _basis_muro_part(assembly, part):
    """UV de la placa: Y mundo arriba, look hacia afuera del tanque. Origen en el plano de la cara."""
    face = _largest_plane(part)
    origin, u0, v0 = _face_basis(face) if face is not None else (None, None, None)
    occ = _occ_de_part(assembly, part)
    if origin is None or occ is None:
        return origin, u0, v0
    try:
        from armado_kit import _centro_doc, _centro_occ, _mat4
    except Exception:
        return origin, u0, v0
    m = _mat4(occ)
    if m is None:
        return origin, u0, v0
    look = None
    try:
        n = face.Geometry.Normal
        look = _vec(n)
    except Exception:
        look = None
    if look is None:
        ejes = _ejes_doc(part, "in")
        look = ejes[-1]["vec"] if ejes else (0.0, 0.0, 1.0)

    def to_world(v):
        return (
            m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
            m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
            m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2],
        )

    def to_part(w):
        return (
            m[0][0] * w[0] + m[1][0] * w[1] + m[2][0] * w[2],
            m[0][1] * w[0] + m[1][1] * w[1] + m[2][1] * w[2],
            m[0][2] * w[0] + m[1][2] * w[1] + m[2][2] * w[2],
        )

    tank = _centro_doc(assembly)
    plate = _centro_occ(occ)
    if tank is not None and plate is not None:
        afuera = (plate[0] - tank[0], plate[1] - tank[1], plate[2] - tank[2])
        look_w = to_world(look)
        if _dot(look_w, afuera) < 0:
            look = (-look[0], -look[1], -look[2])
    y_part = to_part((0.0, 1.0, 0.0))
    v = (
        y_part[0] - look[0] * _dot(y_part, look),
        y_part[1] - look[1] * _dot(y_part, look),
        y_part[2] - look[2] * _dot(y_part, look),
    )
    if v[0] * v[0] + v[1] * v[1] + v[2] * v[2] < 1e-8:
        x_part = to_part((1.0, 0.0, 0.0))
        v = (
            x_part[0] - look[0] * _dot(x_part, look),
            x_part[1] - look[1] * _dot(x_part, look),
            x_part[2] - look[2] * _dot(x_part, look),
        )
    v = _norm(v)
    u = _norm(_cross(v, look))
    v = _norm(_cross(look, u))
    if u is None or v is None:
        return origin, u0, v0
    if _dot(v, y_part) < 0:
        v = (-v[0], -v[1], -v[2])
        u = (-u[0], -u[1], -u[2])
    return origin, u, v


def _silhouette_vertices(part, unit: str, basis=None) -> tuple[list[tuple[float, float]], list[dict]]:
    caras = _caras_placa_doblada(part)
    if not caras:
        return [], []
    face = caras[0]
    if basis and basis[0] is not None:
        origin, u_axis, v_axis = basis
    else:
        origin, u_axis, v_axis = _face_basis(face)
    if origin is None:
        return [], []
    target = "mm" if str(unit).lower() == "mm" else "in"
    try:
        uom = part.UnitsOfMeasure
    except Exception:
        uom = None
    outline: list[tuple[float, float]] = []
    holes: list[dict] = []
    max_area = _area_cara(face) or 1.0
    for cara in caras:
        area = _area_cara(cara)
        if area < max_area * 0.12:
            continue
        try:
            loops = cara.EdgeLoops
            count = int(loops.Count)
        except Exception:
            continue
        for index in range(1, count + 1):
            try:
                loop = loops.Item(index)
                poly, circles = _loop_uv_geom(loop, origin, u_axis, v_axis, uom, target)
                outer = bool(getattr(loop, "IsOuterEdgeLoop", False))
                if outer:
                    if len(poly) > len(outline):
                        outline = poly
                    continue
                if _lazo_es_marcaje(loop, cara) and not _interior_sin_metal(
                    poly, caras, origin, u_axis, v_axis, uom, target, cara
                ):
                    continue
                huecos = _huecos_de_lazo(circles, poly)
                if huecos:
                    holes.extend(huecos)
                elif len(poly) >= 3:
                    holes.append({"kind": "cut", "pts": list(poly)})
            except Exception:
                continue
    return outline, holes


def _caras_placa_doblada(part) -> list:
    """Caras planas de la pared (misma normal), la de más lazos internos primero."""
    rows = []
    try:
        bodies = part.ComponentDefinition.SurfaceBodies
        for b in range(1, int(bodies.Count) + 1):
            faces = bodies.Item(b).Faces
            for f in range(1, int(faces.Count) + 1):
                face = faces.Item(f)
                try:
                    if int(face.SurfaceType) != 5890:
                        continue
                    area = _area_cara(face)
                    inner = max(int(face.EdgeLoops.Count) - 1, 0)
                except Exception:
                    continue
                if area <= 0:
                    continue
                rows.append((inner, area, face))
    except Exception:
        return []
    if not rows:
        return []
    rows.sort(key=lambda item: (item[0], item[1]), reverse=True)
    principal = rows[0][2]
    n_ref = _normal_cara(principal)
    if n_ref is None:
        return [principal]
    try:
        root = principal.Geometry.RootPoint
        offset = _dot3(n_ref, (float(root.X), float(root.Y), float(root.Z)))
    except Exception:
        return [principal]
    mismas = []
    for inner, area, face in rows:
        n = _normal_cara(face)
        if n is None or _dot3(n, n_ref) < 0.98:
            continue
        try:
            p = face.Geometry.RootPoint
            off = _dot3(n_ref, (float(p.X), float(p.Y), float(p.Z)))
        except Exception:
            continue
        if abs(off - offset) > 0.08:
            continue
        mismas.append(face)
    return mismas or [principal]


def _area_cara(face) -> float:
    try:
        return abs(float(face.Evaluator.Area))
    except Exception:
        try:
            return float(int(face.Edges.Count))
        except Exception:
            return 0.0


def _largest_plane(part):
    caras = _caras_placa_doblada(part)
    return caras[0] if caras else None


def _face_basis(face):
    try:
        plane = face.Geometry
        origin = (float(plane.RootPoint.X), float(plane.RootPoint.Y), float(plane.RootPoint.Z))
        normal = _vec(plane.Normal)
    except Exception:
        return None, None, None
    tangent = (1.0, 0.0, 0.0)
    if abs(_dot(normal, tangent)) > 0.9:
        tangent = (0.0, 1.0, 0.0)
    u_axis = _cross(normal, tangent)
    u_axis = _norm(u_axis)
    v_axis = _norm(_cross(normal, u_axis))
    return origin, u_axis, v_axis


def _loop_vertices(loop, origin, u_axis, v_axis, uom, target: str) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    try:
        edges = loop.Edges
        total = min(int(edges.Count), 80)
    except Exception:
        return pts
    for index in range(1, total + 1):
        try:
            edge = edges.Item(index)
            for vertex in (edge.StartVertex, edge.EndVertex):
                p = vertex.Point
                rel = (float(p.X) - origin[0], float(p.Y) - origin[1], float(p.Z) - origin[2])
                x = _to_unit(_dot(rel, u_axis), uom, target)
                y = _to_unit(_dot(rel, v_axis), uom, target)
                if math.isfinite(x) and math.isfinite(y) and abs(x) < 1e6 and abs(y) < 1e6:
                    pts.append((x, y))
        except Exception:
            continue
    return _dedupe(pts)


def _to_unit(value: float, uom, target: str) -> float:
    try:
        if uom is not None:
            return float(uom.ConvertUnits(float(value), "cm", target))
    except Exception:
        pass
    return float(value) * (10.0 if target == "mm" else 1 / 2.54)


def _outer_from_face(patron, origin, u_axis, v_axis, uom, target: str):
    keys: set[str] = set()
    try:
        face = patron.TopFace
        loops = face.EdgeLoops
        total = int(loops.Count)
    except Exception:
        return [], keys
    for index in range(1, total + 1):
        try:
            loop = loops.Item(index)
            try:
                is_outer = bool(loop.IsOuterEdgeLoop)
            except Exception:
                is_outer = False
            if not is_outer:
                continue
            poly, edge_keys = _loop_poly(loop, origin, u_axis, v_axis, uom, target)
            if len(poly) >= 3:
                return poly, edge_keys
        except Exception:
            continue
    return [], keys


def _loop_poly(loop, origin, u_axis, v_axis, uom, target: str):
    keys: set[str] = set()
    ordered: list[tuple[object, bool]] = []
    try:
        uses = loop.EdgeUses
        total = int(uses.Count)
        for index in range(1, total + 1):
            use = uses.Item(index)
            edge = use.Edge
            keys.add(_edge_key(edge))
            opposed = False
            try:
                opposed = bool(use.IsOpposedToEdge)
            except Exception:
                pass
            ordered.append((edge, opposed))
    except Exception:
        try:
            edges = loop.Edges
            total = int(edges.Count)
            raw = []
            for index in range(1, total + 1):
                edge = edges.Item(index)
                keys.add(_edge_key(edge))
                raw.append(edge)
            ordered = _encadenar(raw)
        except Exception:
            return [], keys
    pts: list[tuple[float, float]] = []
    for edge, opposed in ordered:
        sample = _edge_poly(edge, origin, u_axis, v_axis, uom, target)
        if opposed:
            sample = list(reversed(sample))
        pts.extend(sample)
    return _dedupe(pts), keys


def _edge_key(edge) -> str:
    for attr in ("TransientKey", "InternalName"):
        try:
            value = getattr(edge, attr)
            if value is not None:
                return str(value)
        except Exception:
            continue
    try:
        a = edge.StartVertex.Point
        b = edge.EndVertex.Point
        return f"{round(float(a.X), 4)}_{round(float(a.Y), 4)}_{round(float(b.X), 4)}_{round(float(b.Y), 4)}"
    except Exception:
        return str(id(edge))


def _edge_poly(edge, origin, u_axis, v_axis, uom, target: str) -> list[tuple[float, float]]:
    try:
        a = edge.StartVertex.Point
        b = edge.EndVertex.Point
        p0 = _uv((float(a.X), float(a.Y), float(a.Z)), origin, u_axis, v_axis, uom, target)
        p1 = _uv((float(b.X), float(b.Y), float(b.Z)), origin, u_axis, v_axis, uom, target)
    except Exception:
        return []
    if not all(math.isfinite(v) for v in p0 + p1):
        return []
    circle = _circle_from_edge(edge)
    if circle is None:
        return [p0, p1]
    center, radius, _is_arc = circle
    c = _uv(center, origin, u_axis, v_axis, uom, target)
    radio = abs(_to_unit(radius, uom, target))
    if radio < 0.2 or not all(math.isfinite(v) for v in c):
        return [p0, p1]
    a0 = math.atan2(p0[1] - c[1], p0[0] - c[0])
    a1 = math.atan2(p1[1] - c[1], p1[0] - c[0])
    sweep = a1 - a0
    while sweep > math.pi:
        sweep -= 2 * math.pi
    while sweep < -math.pi:
        sweep += 2 * math.pi
    steps = max(4, min(24, int(abs(sweep) * radio / 1.8) or 4))
    mid = []
    for index in range(1, steps):
        ang = a0 + sweep * index / steps
        mid.append((c[0] + radio * math.cos(ang), c[1] + radio * math.sin(ang)))
    return [p0] + mid + [p1]


def _encadenar(edges) -> list[tuple[object, bool]]:
    if not edges:
        return []
    def ends(edge):
        a = edge.StartVertex.Point
        b = edge.EndVertex.Point
        return (round(float(a.X), 4), round(float(a.Y), 4), round(float(a.Z), 4)), (
            round(float(b.X), 4),
            round(float(b.Y), 4),
            round(float(b.Z), 4),
        )

    pending = list(edges[1:])
    chain = [(edges[0], False)]
    try:
        _s, cursor = ends(edges[0])
    except Exception:
        return [(e, False) for e in edges]
    while pending:
        found = None
        for item in pending:
            try:
                a, b = ends(item)
            except Exception:
                continue
            if a == cursor:
                found = (item, False, b)
                break
            if b == cursor:
                found = (item, True, a)
                break
        if found is None:
            break
        edge, opposed, cursor = found
        chain.append((edge, opposed))
        pending.remove(edge)
    chain.extend((e, False) for e in pending)
    return chain


def _centroide(poly: list[tuple[float, float]]) -> tuple[float, float]:
    area = _area(poly)
    if abs(area) < 1e-9:
        return (
            sum(p[0] for p in poly) / len(poly),
            sum(p[1] for p in poly) / len(poly),
        )
    cx = cy = 0.0
    last = poly[-1]
    for point in poly:
        cross = last[0] * point[1] - point[0] * last[1]
        cx += (last[0] + point[0]) * cross
        cy += (last[1] + point[1]) * cross
        last = point
    return cx / (6 * area), cy / (6 * area)


def _area(poly: list[tuple[float, float]]) -> float:
    total = 0.0
    last = poly[-1]
    for point in poly:
        total += last[0] * point[1] - point[0] * last[1]
        last = point
    return total * 0.5


def _punto_dentro(x: float, y: float, poly: list[tuple[float, float]]) -> bool:
    inside = False
    j = len(poly) - 1
    for i, (xi, yi) in enumerate(poly):
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            xhit = (xj - xi) * (y - yi) / ((yj - yi) or 1e-18) + xi
            if x < xhit:
                inside = not inside
        j = i
    return inside


def _dist_seg(px, py, x1, y1, x2, y2) -> float:
    dx, dy = x2 - x1, y2 - y1
    den = dx * dx + dy * dy
    if den < 1e-12:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / den))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def _dist_contorno(x: float, y: float, poly: list[tuple[float, float]]) -> float:
    best = 1e9
    last = poly[-1]
    for point in poly:
        best = min(best, _dist_seg(x, y, last[0], last[1], point[0], point[1]))
        last = point
    return best


def _hueco_interior(item: dict, outline: list[tuple[float, float]]) -> bool:
    if len(outline) < 3:
        return True
    x = float(item.get("x") if "x" in item else item.get("cx") or 0)
    y = float(item.get("y") if "y" in item else item.get("cy") or 0)
    dia = abs(float(item.get("dia") or 0))
    if not _punto_dentro(x, y, outline):
        return False
    if _dist_contorno(x, y, outline) <= max(1.4, dia * 0.55):
        return False
    return True


def _rect_outline(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return [(min(xs), min(ys)), (max(xs), min(ys)), (max(xs), max(ys)), (min(xs), max(ys))]


def _finite_outline(outline: list[tuple[float, float]]) -> bool:
    if len(outline) < 3:
        return False
    xs = [p[0] for p in outline]
    ys = [p[1] for p in outline]
    if not all(math.isfinite(v) for v in xs + ys):
        return False
    span = max(max(xs) - min(xs), max(ys) - min(ys))
    return 0.5 < span < 1e5


def _as_hole(pts: list[tuple[float, float]]) -> dict | None:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    cx = sum(xs) / len(xs)
    cy = sum(ys) / len(ys)
    radii = [math.hypot(p[0] - cx, p[1] - cy) for p in pts]
    if not radii:
        return None
    r = sum(radii) / len(radii)
    spread = max(radii) - min(radii)
    if r < 0.05 or spread > r * 0.55:
        return None
    return {"x": cx, "y": cy, "dia": round(r * 2, 3)}


def _dedupe(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    clean: list[tuple[float, float]] = []
    for point in pts:
        if not clean or math.hypot(point[0] - clean[-1][0], point[1] - clean[-1][1]) > 1e-4:
            clean.append(point)
    return clean


def _token(value, unit: str) -> str:
    try:
        number = f"{float(value):.2f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        number = "0"
    return f"{number}{unit}"


def _vec(obj) -> tuple[float, float, float]:
    try:
        return (float(obj.X), float(obj.Y), float(obj.Z))
    except Exception:
        if isinstance(obj, (tuple, list)) and len(obj) >= 3:
            return (float(obj[0]), float(obj[1]), float(obj[2]))
    return (0.0, 0.0, 1.0)


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b) -> tuple[float, float, float]:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a) -> tuple[float, float, float]:
    length = math.hypot(a[0], math.hypot(a[1], a[2]))
    if length <= 1e-12:
        return (1.0, 0.0, 0.0)
    return (a[0] / length, a[1] / length, a[2] / length)
