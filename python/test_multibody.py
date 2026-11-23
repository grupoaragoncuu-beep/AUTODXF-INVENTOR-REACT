import tempfile
import unittest
from pathlib import Path

import multibody


class _List:
    def __init__(self, items=None):
        self.items = list(items or [])

    @property
    def Count(self):
        return len(self.items)

    def Item(self, index):
        return self.items[index - 1]

    def Add(self, item):
        self.items.append(item)
        return item


class _Body:
    def __init__(self, solid=True, volume=1.0, appearance="Pintura", explode=False):
        self.IsSolid = solid
        self.Appearance = appearance
        self.explode = explode
        self._volume = volume
        self.Faces = _List()

    def Volume(self, tolerance=0.01):
        return self._volume


class _Props:
    def __init__(self):
        self.values = {}

    def Item(self, key):
        slot = self.values.setdefault(key, type("Slot", (), {"Value": ""})())
        return slot


class _PropSets:
    def __init__(self, source=None):
        self._sets = {"Design Tracking Properties": source or _Props()}

    def Item(self, key):
        return self._sets[key]


class _Features:
    def __init__(self, definition):
        self.NonParametricBaseFeatures = self
        self.definition = definition
        self.added = []

    def Add(self, body, operation=None):
        if getattr(body, "explode", False):
            raise RuntimeError("copia rota")
        self.added.append(body)
        created = _Body(appearance=None)
        self.definition.SurfaceBodies.items.append(created)
        self.definition.Sketches.items.append(_Sketch(self.definition.Sketches))
        return created


class _Sketch:
    def __init__(self, owner):
        self.owner = owner

    def ExitEdit(self):
        return None

    def Delete(self):
        if self in self.owner.items:
            self.owner.items.remove(self)


class _Sketches:
    def __init__(self):
        self.items = []

    @property
    def Count(self):
        return len(self.items)

    def Item(self, index):
        return self.items[index - 1]


class _Def:
    def __init__(self, doc, bodies=None):
        self.Document = doc
        self.SurfaceBodies = _List(bodies or [])
        self.Material = type("Material", (), {"Name": "Acero"})()
        self.Appearance = "Rojo"
        self.Features = _Features(self)
        self.Sketches = _Sketches()
        self.Parent = doc
        self.Occurrences = _OccList()
        self.Occurrences.parent = doc


class _Doc:
    def __init__(self, path, kind, bodies=None, name=""):
        self.FullFileName = path
        self.DisplayName = name or (Path(path).name if path else "nuevo")
        self.DocumentType = kind
        self.ComponentDefinition = _Def(self, bodies)
        self.IsModifiable = True
        self.PropertySets = _PropSets()
        self.Materials = _List([self.ComponentDefinition.Material])
        self.UnitsOfMeasure = type("Units", (), {"LengthUnits": 11272})()
        self.saved = ""
        self.closed = False

    def SaveAs(self, path, copy_as):
        self.FullFileName = path
        self.saved = path
        Path(path).write_text("x", encoding="utf-8")

    def Close(self, skip_save):
        self.closed = True

    def Update(self):
        return None


class _Occ:
    def __init__(self, name, doc, parent, matrix=None, suppressed=False):
        self.Name = name
        self.Definition = doc.ComponentDefinition
        self.DefinitionDocumentType = doc.DocumentType
        self.ParentDocument = parent
        self.Transformation = matrix or object()
        self.Suppressed = suppressed
        self.Grounded = False
        self.deleted = False
        self._parent_doc = parent

    def Delete(self):
        self.deleted = True
        listing = self._parent_doc.ComponentDefinition.Occurrences
        if self in listing.items:
            listing.items.remove(self)
        listing.deleted.append(self)


class _LockedOcc(_Occ):
    def Delete(self):
        raise RuntimeError("bloqueado")


class _OccList:
    def __init__(self):
        self.items = []
        self.deleted = []
        self.app = None
        self.parent = None

    @property
    def Count(self):
        return len(self.items)

    def Item(self, index):
        return self.items[index - 1]

    def Add(self, path, matrix=None):
        source = None
        docs = list(self.app.Documents.items) if self.app is not None else []
        for doc in docs:
            saved = str(getattr(doc, "saved", "") or "")
            full = str(getattr(doc, "FullFileName", "") or "")
            if str(path) in {saved, full}:
                source = doc
                break
        if source is None:
            source = _Doc(str(path), multibody.ASSEMBLY_DOC)
            source.saved = str(path)
        occ = _Occ(Path(str(path)).stem, source, self.parent, matrix)
        occ._parent_doc = self.parent
        self.items.append(occ)
        return occ


class _Docs:
    def __init__(self, app, items):
        self.app = app
        self.items = list(items)

    @property
    def Count(self):
        return len(self.items)

    def Item(self, index):
        return self.items[index - 1]

    def Add(self, kind, template="", visible=False):
        return self.app._add_doc(kind)


class _App:
    def __init__(self, docs):
        self.Documents = _Docs(self, docs)
        self.FileManager = type("FM", (), {"GetTemplateFile": lambda self, kind: ""})()
        self.TransientGeometry = self
        self.TransientBRep = self
        self.TransientObjects = self
        self.TransactionManager = self
        self.SilentOperation = False
        self.ScreenUpdating = True
        self.ActiveView = type("View", (), {"Update": lambda self: None})()
        self.created = []
        self.txn = None
        self.identity = object()

    def _add_doc(self, kind):
        doc = _Doc("", kind)
        doc.ComponentDefinition.Occurrences.app = self
        doc.ComponentDefinition.Occurrences.parent = doc
        self.created.append(doc)
        self.Documents.items.append(doc)
        return doc

    def CreateMatrix(self):
        return self.identity

    def Copy(self, body):
        if getattr(body, "explode", False):
            raise RuntimeError("copia rota")
        return body

    def CreateObjectCollection(self):
        return _List()

    def StartGlobalTransaction(self, doc, name):
        self.txn = type("Txn", (), {"ended": False, "aborted": False})()
        self.txn.End = lambda: setattr(self.txn, "ended", True)
        self.txn.Abort = lambda: setattr(self.txn, "aborted", True)
        return self.txn


def _part(path, bodies, name=""):
    return _Doc(path, multibody.PART_DOC, bodies, name)


def _assembly(path, occurrences):
    doc = _Doc(path, multibody.ASSEMBLY_DOC)
    for occ in occurrences:
        occ._parent_doc = doc
        doc.ComponentDefinition.Occurrences.items.append(occ)
    return doc


class MultibodyTest(unittest.TestCase):
    def test_el_nombre_conserva_letras_y_cambia_simbolos(self):
        self.assertEqual(multibody.clean_name("Tapa frontal"), "Tapa_frontal")
        self.assertEqual(multibody.clean_name("A/B"), "A_B")
        self.assertEqual(multibody.clean_name("ñandú"), "ñandú")
        self.assertEqual(multibody.clean_name("///"), "___")

    def test_el_volumen_acepta_metodo_o_propiedad(self):
        self.assertEqual(multibody.body_volume(_Body(volume=2)), 2.0)
        self.assertEqual(multibody.body_volume(type("B", (), {"Volume": 3.5})()), 3.5)
        self.assertIsNone(multibody.body_volume(type("B", (), {})()))

    def test_solo_cuenta_como_multibody_con_dos_solidos(self):
        one = _Def(None, [_Body(), _Body(solid=False)])
        two = _Def(None, [_Body(), _Body(volume=0), _Body()])
        self.assertFalse(multibody.is_multibody(one))
        self.assertTrue(multibody.is_multibody(two))
        self.assertEqual(len(multibody.solid_bodies(two)), 2)

    def test_el_nombre_no_pisa_el_ensamble_ni_un_archivo_protegido(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            main = folder / "Tanque.iam"
            main.write_text("iam", encoding="utf-8")
            busy = folder / "Caja_MB.iam"
            busy.write_text("previo", encoding="utf-8")
            protected = {str(main).lower(), str(busy).lower()}
            iam, ipts = multibody.allocate_names(folder, "Tanque", 2, protected)
            self.assertEqual(iam.name, "Tanque_MB.iam")
            iam2, ipts2 = multibody.allocate_names(folder, "Caja", 1, protected)
            self.assertEqual(iam2.name, "Caja_MB2.iam")
            self.assertTrue(busy.exists())
            self.assertEqual([path.name for path in ipts], ["Tanque_MB_1.ipt", "Tanque_MB_2.ipt"])
            self.assertEqual(ipts2[0].name, "Caja_MB2_1.ipt")

    def test_recorre_cada_definicion_una_vez_y_junta_los_usos(self):
        multi = _part(r"C:\job\Caja.ipt", [_Body(), _Body()])
        single = _part(r"C:\job\Tapa.ipt", [_Body()])
        sub = _assembly(r"C:\job\Sub.iam", [_Occ("Caja:1", multi, None)])
        top = _assembly(
            r"C:\job\Tanque.iam",
            [
                _Occ("Sub:1", sub, None),
                _Occ("Sub:2", sub, None),
                _Occ("Caja:1", multi, None),
                _Occ("Tapa:1", single, None),
                _Occ("Caja:2", multi, None, suppressed=True),
            ],
        )
        jobs, failed = multibody.collect_jobs(top)
        self.assertEqual(failed, [])
        self.assertEqual(len(jobs), 1)
        self.assertEqual(sorted(hit["name"] for hit in jobs[0]["hits"]), ["Caja:1", "Caja:1"])
        parents = {hit["parent"] for hit in jobs[0]["hits"]}
        self.assertEqual(parents, {sub, top})

    def test_convierte_y_reemplaza_sin_perder_el_archivo_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            multi = _part(str(folder / "Caja.ipt"), [_Body(), _Body()])
            multi.PropertySets.Item("Design Tracking Properties").Item("Description").Value = "lateral"
            top = _assembly(str(folder / "Tanque.iam"), [_Occ("Caja:1", multi, None)])
            app = _App([top, multi])
            top.ComponentDefinition.Occurrences.app = app
            result = multibody.run_multibody(lambda: (app, top))

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["processed"], ["Caja.ipt"])
        self.assertEqual(result["replaced"], 1)
        self.assertTrue(app.txn.ended)
        iam = next(doc for doc in app.created if doc.DocumentType == multibody.ASSEMBLY_DOC)
        parts = [doc for doc in app.created if doc.DocumentType == multibody.PART_DOC]
        self.assertEqual(Path(iam.saved).name, "Caja_MB.iam")
        self.assertEqual([Path(doc.saved).name for doc in parts], ["Caja_MB_1.ipt", "Caja_MB_2.ipt"])
        self.assertTrue(all(doc.closed for doc in parts))
        self.assertEqual(parts[0].ComponentDefinition.Material.Name, "Acero")
        self.assertEqual(parts[0].PropertySets.Item("Design Tracking Properties").Item("Part Number").Value, "Caja_MB_1")
        self.assertEqual(parts[0].PropertySets.Item("Design Tracking Properties").Item("Description").Value, "lateral")
        self.assertEqual(len(iam.ComponentDefinition.Occurrences.items), 2)
        self.assertTrue(all(occ.Grounded for occ in iam.ComponentDefinition.Occurrences.items))
        self.assertEqual(parts[0].ComponentDefinition.Sketches.items, [])
        self.assertEqual(parts[1].ComponentDefinition.Sketches.items, [])
        replacement = top.ComponentDefinition.Occurrences.items[0]
        self.assertEqual(replacement.Name, "Caja:1")
        self.assertTrue(replacement.Definition.Document.saved.endswith("Caja_MB.iam"))
        self.assertNotIn(multi, [item.Definition.Document for item in top.ComponentDefinition.Occurrences.items])

    def test_si_no_puede_borrar_la_vieja_quita_la_nueva(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            multi = _part(str(folder / "Caja.ipt"), [_Body(), _Body()])
            locked = _LockedOcc("Caja:1", multi, None)
            top = _assembly(str(folder / "Tanque.iam"), [locked])
            app = _App([top, multi])
            top.ComponentDefinition.Occurrences.app = app
            result = multibody.run_multibody(lambda: (app, top))

        self.assertFalse(result["ok"])
        self.assertEqual(result["replaced"], 0)
        self.assertTrue(app.txn.aborted)
        self.assertEqual(len(top.ComponentDefinition.Occurrences.items), 1)
        self.assertIs(top.ComponentDefinition.Occurrences.items[0], locked)
        self.assertTrue(top.ComponentDefinition.Occurrences.deleted)

    def test_un_cuerpo_roto_no_reemplaza_la_pieza(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            multi = _part(str(folder / "Caja.ipt"), [_Body(), _Body(explode=True)])
            occ = _Occ("Caja:1", multi, None)
            top = _assembly(str(folder / "Tanque.iam"), [occ])
            app = _App([top, multi])
            result = multibody.run_multibody(lambda: (app, top))

        self.assertFalse(result["ok"])
        self.assertEqual(result["replaced"], 0)
        self.assertIs(top.ComponentDefinition.Occurrences.items[0], occ)
        self.assertIn("copiar", result["failed"][0]["message"])

    def test_sin_multibody_y_sin_ensamble_guardado(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            single = _part(str(folder / "Tapa.ipt"), [_Body()])
            top = _assembly(str(folder / "Tanque.iam"), [_Occ("Tapa:1", single, None)])
            app = _App([top])
            ready = multibody.run_multibody(lambda: (app, top))
        self.assertTrue(ready["ok"])
        self.assertIn("No hay piezas", ready["message"])

        unsaved = _Doc("", multibody.ASSEMBLY_DOC)
        missing = multibody.run_multibody(lambda: (app, unsaved))
        self.assertFalse(missing["ok"])
        self.assertIn("Guarda el ensamble", missing["message"])


if __name__ == "__main__":
    unittest.main()
