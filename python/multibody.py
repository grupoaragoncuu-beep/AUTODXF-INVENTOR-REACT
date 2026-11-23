"""Multibody a IAM sobre el ensamble abierto.

Cada .ipt con dos o más sólidos se publica como un IPT por cuerpo y un IAM
que los junta, en la carpeta del ensamble principal. La ocurrencia se
cambia con Add y después Delete.

El sólido queda suelto: no hay vínculo al IPT original. Material, apariencia
y iProperties de diseño se copian. Las restricciones de la ocurrencia no.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from inventor_session import _active_assembly, _full_name, _inventor, _short

PART_DOC = 12290
ASSEMBLY_DOC = 12291
_NEW_BODY = 20485


def run_multibody(opener=None) -> dict:
    try:
        inv, assembly = (opener or _open_session)()
    except Exception as ex:
        return _fail(_short(ex), connected=False)
    if assembly is None:
        return _fail("Abre un ensamble .iam y vuelve a lanzar Multibody.")
    folder = _output_folder(assembly)
    if folder is None:
        return _fail("Guarda el ensamble. Los archivos nuevos se crean en esa carpeta.")
    folder.mkdir(parents=True, exist_ok=True)

    silent, screen = _quiet_on(inv)
    txn = None
    processed: list[str] = []
    failed: list[dict] = []
    replaced = 0
    try:
        jobs, problems = collect_jobs(assembly)
        failed.extend(problems)
        protected = protected_paths(inv, assembly)
        part_template = _template(inv, PART_DOC)
        asm_template = _template(inv, ASSEMBLY_DOC)
        ready: list[tuple[dict, Path]] = []
        for job in jobs:
            label = _doc_label(job["part"])
            try:
                bodies = solid_bodies(job["definition"])
                if len(bodies) < 2:
                    raise RuntimeError("No hay dos sólidos válidos.")
                iam_path = publish_part(
                    inv,
                    job,
                    bodies,
                    folder,
                    protected,
                    part_template,
                    asm_template,
                )
            except Exception as ex:
                _add_fail(failed, label, _short(ex))
                continue
            ready.append((job, iam_path))
        if ready:
            txn = _begin_txn(inv, assembly)
            for job, iam_path in ready:
                label = _doc_label(job["part"])
                placed = _replace_job(job, iam_path, failed)
                replaced += placed
                if placed:
                    processed.append(label)
                elif not _already_failed(failed, label):
                    _add_fail(failed, label, "El IAM quedó en disco, pero la ocurrencia no se reemplazó.")
            _finish_txn(txn, replaced)
            txn = None
    except Exception as ex:
        _abort_txn(txn)
        return _fail(_short(ex), folder=str(folder))
    finally:
        _quiet_off(inv, silent, screen)
        _refresh_view(inv)

    return {
        "ok": not failed,
        "message": _message(processed, failed, replaced, folder),
        "folder": str(folder),
        "processed": processed,
        "failed": failed,
        "replaced": replaced,
        "inventorConnected": True,
    }


def collect_jobs(assembly) -> tuple[list[dict], list[dict]]:
    """Una entrada por IPT y una ocurrencia por uso dentro de cada definición."""
    jobs: dict[str, dict] = {}
    order: list[str] = []
    failed: list[dict] = []
    seen: set[str] = set()

    def walk(doc) -> None:
        key = _doc_key(doc)
        if key in seen:
            return
        seen.add(key)
        try:
            occurrences = doc.ComponentDefinition.Occurrences
        except Exception as ex:
            _add_fail(failed, _doc_label(doc), _short(ex))
            return
        for occ in _iter_collection(occurrences):
            try:
                suppressed = bool(occ.Suppressed)
            except Exception:
                suppressed = False
            if suppressed:
                continue
            try:
                kind = int(occ.DefinitionDocumentType)
            except Exception:
                continue
            if kind == ASSEMBLY_DOC:
                try:
                    walk(occ.Definition.Document)
                except Exception as ex:
                    _add_fail(failed, _occ_name(occ), _short(ex))
                continue
            if kind != PART_DOC:
                continue
            try:
                part = occ.Definition.Document
                definition = occ.Definition
                if not is_multibody(definition):
                    continue
                matrix = _capture_matrix(occ)
            except Exception as ex:
                _add_fail(failed, _occ_name(occ), _short(ex))
                continue
            part_key = _doc_key(part)
            job = jobs.get(part_key)
            if job is None:
                job = {"part": part, "definition": definition, "hits": []}
                jobs[part_key] = job
                order.append(part_key)
            job["hits"].append({
                "parent": doc,
                "name": _occ_name(occ),
                "matrix": matrix,
            })

    walk(assembly)
    return [jobs[key] for key in order], failed


def is_multibody(definition) -> bool:
    bodies = definition.SurfaceBodies
    if int(bodies.Count) <= 1:
        return False
    return len(solid_bodies(definition)) >= 2


def solid_bodies(definition) -> list:
    found = []
    for body in _iter_collection(definition.SurfaceBodies):
        try:
            solid = bool(body.IsSolid)
        except Exception:
            solid = True
        if not solid:
            continue
        volume = body_volume(body)
        if volume is not None and volume <= 0:
            continue
        found.append(body)
    return found


def body_volume(body) -> float | None:
    volume = getattr(body, "Volume", None)
    if volume is None:
        return None
    if callable(volume):
        for args in ((0.01,), ()):
            try:
                return float(volume(*args))
            except Exception:
                continue
        return None
    try:
        return float(volume)
    except (TypeError, ValueError):
        return None


def clean_name(name: str) -> str:
    cleaned = re.sub(r"[^\w\-]", "_", name or "", flags=re.UNICODE)
    return (cleaned[:80] or "pieza")


def allocate_names(folder: Path, base: str, count: int, protected: set[str]) -> tuple[Path, list[Path]] | None:
    blocked = {item.lower() for item in protected}
    for generation in range(1, 40):
        suffix = "_MB" if generation == 1 else f"_MB{generation}"
        iam = folder / f"{base}{suffix}.iam"
        ipts = [folder / f"{base}{suffix}_{index}.ipt" for index in range(1, count + 1)]
        paths = [iam, *ipts]
        if any(str(path).lower() in blocked for path in paths):
            continue
        if _take_paths(paths):
            return iam, ipts
    return None


def protected_paths(inv, assembly) -> set[str]:
    paths: set[str] = set()
    seen: set[str] = set()

    def remember(doc) -> None:
        full = _full_name(doc)
        if full:
            paths.add(full.lower())

    def walk(doc) -> None:
        key = _doc_key(doc)
        if key in seen:
            return
        seen.add(key)
        remember(doc)
        try:
            if int(doc.DocumentType) != ASSEMBLY_DOC:
                return
            occurrences = doc.ComponentDefinition.Occurrences
        except Exception:
            return
        for occ in _iter_collection(occurrences):
            try:
                kind = int(occ.DefinitionDocumentType)
                if kind not in (PART_DOC, ASSEMBLY_DOC):
                    continue
                walk(occ.Definition.Document)
            except Exception:
                continue

    walk(assembly)
    try:
        for doc in _iter_collection(inv.Documents):
            remember(doc)
    except Exception:
        pass
    return paths


def publish_part(inv, job: dict, bodies: list, folder: Path, protected: set[str], part_template: str, asm_template: str) -> Path:
    base = clean_name(Path(_doc_label(job["part"])).stem)
    claimed = allocate_names(folder, base, len(bodies), protected)
    if claimed is None:
        raise RuntimeError("No hay un nombre libre en la carpeta del ensamble.")
    iam_path, ipt_paths = claimed
    written: list[Path] = []
    try:
        for body, ipt_path in zip(bodies, ipt_paths):
            _write_part(inv, job, body, ipt_path, part_template)
            written.append(ipt_path)
        _write_assembly(inv, ipt_paths, iam_path, asm_template)
        written.append(iam_path)
    except Exception:
        _discard(written)
        raise
    for path in written:
        protected.add(str(path).lower())
    return iam_path


def replace_hit(hit: dict, iam_path: str) -> None:
    parent = hit["parent"]
    if not _modifiable(parent):
        raise RuntimeError("El subensamble no se puede modificar.")
    occ = _find_occurrence(parent, hit["name"])
    if occ is None:
        raise RuntimeError("La ocurrencia ya no está en el ensamble.")
    grounded = bool(getattr(occ, "Grounded", False))
    new_occ = parent.ComponentDefinition.Occurrences.Add(iam_path, hit["matrix"])
    try:
        new_occ.Grounded = grounded
    except Exception:
        pass
    try:
        occ.Delete()
    except Exception as ex:
        try:
            new_occ.Delete()
        except Exception:
            pass
        raise RuntimeError(_short(ex)) from ex
    try:
        new_occ.Name = hit["name"]
    except Exception:
        pass


def clear_sketches(part) -> None:
    """Quita bocetos sueltos. En Inventor se ven amarillos porque nadie los consume."""
    definition = part.ComponentDefinition
    for name in ("Sketches", "Sketches3D"):
        collection = getattr(definition, name, None)
        if collection is None:
            continue
        for sketch in list(_iter_collection(collection)):
            try:
                sketch.ExitEdit()
            except Exception:
                pass
            try:
                sketch.Delete()
            except Exception:
                continue


def _replace_job(job: dict, iam_path: Path, failed: list[dict]) -> int:
    placed = 0
    label = _doc_label(job["part"])
    for hit in job["hits"]:
        try:
            replace_hit(hit, str(iam_path))
            placed += 1
        except Exception as ex:
            _add_fail(failed, f"{label} / {hit['name']}", _short(ex))
    return placed


def _write_part(inv, job: dict, body, ipt_path: Path, template: str) -> None:
    doc = inv.Documents.Add(PART_DOC, template, False)
    try:
        _match_units(job["part"], doc)
        _copy_material(job["definition"], doc)
        paint = _read_appearance(body, job["definition"])
        _apply_appearance(paint, doc.ComponentDefinition, None)
        _add_base_body(inv, doc, body)
        try:
            doc.Update()
        except Exception:
            pass
        try:
            new_body = doc.ComponentDefinition.SurfaceBodies.Item(1)
            _apply_appearance(paint, doc.ComponentDefinition, new_body)
        except Exception:
            pass
        clear_sketches(doc)
        _copy_props(job["part"], doc, ipt_path.stem)
        doc.SaveAs(str(ipt_path), False)
    finally:
        _close_quiet(doc)


def _write_assembly(inv, ipt_paths: list[Path], iam_path: Path, template: str) -> None:
    doc = inv.Documents.Add(ASSEMBLY_DOC, template, False)
    try:
        occurrences = doc.ComponentDefinition.Occurrences
        identity = inv.TransientGeometry.CreateMatrix()
        for ipt_path in ipt_paths:
            occ = occurrences.Add(str(ipt_path), identity)
            try:
                occ.Grounded = True
            except Exception:
                pass
            try:
                occ.Name = ipt_path.stem
            except Exception:
                pass
        doc.SaveAs(str(iam_path), False)
    finally:
        _close_quiet(doc)


def _add_base_body(inv, doc, body) -> None:
    try:
        copied = inv.TransientBRep.Copy(body)
    except Exception as ex:
        raise RuntimeError(f"No se pudo copiar el sólido: {_short(ex)}") from ex
    features = doc.ComponentDefinition.Features.NonParametricBaseFeatures
    errors: list[Exception] = []
    for attempt in (
        lambda: features.Add(copied),
        lambda: features.Add(copied, _NEW_BODY),
    ):
        try:
            attempt()
            return
        except Exception as ex:
            errors.append(ex)
    try:
        group = inv.TransientObjects.CreateObjectCollection()
        group.Add(copied)
        features.Add(group)
    except Exception as ex:
        errors.append(ex)
        detail = _short(errors[-1]) if errors else "sin detalle"
        raise RuntimeError(f"No se pudo copiar el sólido: {detail}") from ex


def _copy_material(source_def, new_doc) -> None:
    new_def = new_doc.ComponentDefinition
    material = getattr(source_def, "Material", None)
    name = ""
    try:
        name = str(getattr(material, "Name", "") or "")
    except Exception:
        name = ""
    if name:
        try:
            new_def.Material = new_doc.Materials.Item(name)
            return
        except Exception:
            pass
    if material is not None:
        try:
            new_def.Material = material
            return
        except Exception:
            pass
    try:
        new_doc.ActiveMaterial = source_def.Document.ActiveMaterial
    except Exception:
        pass


def _read_appearance(body, definition):
    try:
        paint = body.Appearance
        if paint is not None:
            return paint
    except Exception:
        pass
    try:
        return definition.Appearance
    except Exception:
        return None


def _apply_appearance(paint, definition, body) -> None:
    if paint is None:
        return
    if body is not None:
        try:
            body.Appearance = paint
            return
        except Exception:
            pass
    try:
        definition.Appearance = paint
    except Exception:
        pass


def _copy_props(source, target, part_number: str) -> None:
    try:
        src = source.PropertySets.Item("Design Tracking Properties")
        dst = target.PropertySets.Item("Design Tracking Properties")
    except Exception:
        return
    for key in ("Description", "Stock Number", "Project", "Designer"):
        try:
            dst.Item(key).Value = src.Item(key).Value
        except Exception:
            continue
    try:
        dst.Item("Part Number").Value = part_number
    except Exception:
        pass


def _match_units(source, target) -> None:
    try:
        target.UnitsOfMeasure.LengthUnits = source.UnitsOfMeasure.LengthUnits
    except Exception:
        pass


def _take_paths(paths: list[Path]) -> bool:
    for path in paths:
        if path.exists() and not os.access(path, os.W_OK):
            return False
    try:
        for path in paths:
            if path.exists():
                path.unlink()
        return True
    except OSError:
        return False


def _discard(paths: list[Path]) -> None:
    for path in paths:
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass


def _find_occurrence(parent, name: str):
    try:
        occurrences = parent.ComponentDefinition.Occurrences
    except Exception:
        return None
    for occ in _iter_collection(occurrences):
        if _occ_name(occ) == name:
            return occ
    return None


def _capture_matrix(occ):
    matrix = occ.Transformation
    try:
        return matrix.Copy()
    except Exception:
        return matrix


def _modifiable(doc) -> bool:
    try:
        return bool(doc.IsModifiable)
    except Exception:
        return True


def _iter_collection(collection):
    try:
        total = int(collection.Count)
    except Exception:
        return
    for index in range(1, total + 1):
        try:
            yield collection.Item(index)
        except Exception:
            continue


def _template(inv, kind: int) -> str:
    try:
        return str(inv.FileManager.GetTemplateFile(kind) or "")
    except Exception:
        return ""


def _output_folder(assembly) -> Path | None:
    full = _full_name(assembly)
    if not full:
        return None
    return Path(full).parent


def _doc_key(doc) -> str:
    full = _full_name(doc).lower()
    return full or f"unsaved:{id(doc)}"


def _doc_label(doc) -> str:
    full = _full_name(doc)
    if full:
        return Path(full).name
    try:
        return str(doc.DisplayName or "pieza")
    except Exception:
        return "pieza"


def _occ_name(occ) -> str:
    try:
        name = str(occ.Name or "")
    except Exception:
        name = ""
    return name or "ocurrencia"


def _close_quiet(doc) -> None:
    try:
        doc.Close(True)
    except Exception:
        pass


def _add_fail(failed: list[dict], name: str, message: str) -> None:
    if any(item["name"] == name for item in failed):
        return
    failed.append({"name": name, "message": message})


def _already_failed(failed: list[dict], label: str) -> bool:
    prefix = f"{label} / "
    return any(item["name"] == label or str(item["name"]).startswith(prefix) for item in failed)


def _message(processed: list[str], failed: list[dict], replaced: int, folder: Path) -> str:
    if not processed and not failed:
        return "No hay piezas con más de un sólido."
    parts = []
    if processed:
        parts.append(
            f"Convertidas ({replaced} ocurrencias): {', '.join(processed)}. Carpeta: {folder}."
        )
    if failed:
        parts.append(f"{len(failed)} con error.")
    if replaced:
        parts.append(
            "El ensamble quedó modificado, sin guardar. Las restricciones de esas ocurrencias no se copian."
        )
    return " ".join(parts)


def _fail(message: str, folder: str = "", connected: bool = True) -> dict:
    return {
        "ok": False,
        "message": message,
        "folder": folder,
        "processed": [],
        "failed": [],
        "replaced": 0,
        "inventorConnected": connected,
    }


def _open_session():
    inv = _inventor()
    return inv, _active_assembly(inv)


def _quiet_on(inv) -> tuple[bool, bool]:
    silent = bool(getattr(inv, "SilentOperation", False))
    screen = bool(getattr(inv, "ScreenUpdating", True))
    try:
        inv.SilentOperation = True
    except Exception:
        pass
    try:
        inv.ScreenUpdating = False
    except Exception:
        pass
    return silent, screen


def _quiet_off(inv, silent: bool, screen: bool) -> None:
    try:
        inv.SilentOperation = silent
    except Exception:
        pass
    try:
        inv.ScreenUpdating = screen
    except Exception:
        pass


def _begin_txn(inv, doc):
    manager = getattr(inv, "TransactionManager", None)
    if manager is None:
        return None
    try:
        return manager.StartGlobalTransaction(doc, "Multibody a IAM")
    except Exception:
        try:
            return manager.StartTransaction(doc, "Multibody a IAM")
        except Exception:
            return None


def _finish_txn(txn, replaced: int) -> None:
    if txn is None:
        return
    try:
        if replaced:
            txn.End()
        else:
            txn.Abort()
    except Exception:
        pass


def _abort_txn(txn) -> None:
    if txn is None:
        return
    try:
        txn.Abort()
    except Exception:
        pass


def _refresh_view(inv) -> None:
    try:
        inv.ActiveView.Update()
    except Exception:
        pass
