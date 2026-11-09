"""La carpeta JPG no debe intentar crear el perfil de otro usuario de Windows."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from acotacion import ensure_dir, local_jpg_dir


class LocalJpgTests(unittest.TestCase):
    def test_otro_usuario_no_crea_su_perfil(self):
        ajeno = Path(r"C:\Users\NoSuchLaptopUser\Documents\AUTODXF INVENTOR REACT\JPG")
        with tempfile.TemporaryDirectory() as tmp:
            with patch("acotacion.ROOT", Path(tmp)):
                folder, note = local_jpg_dir(str(ajeno))
            self.assertEqual(folder, Path(tmp) / "JPG")
            self.assertTrue(folder.is_dir())
            self.assertIn("NoSuchLaptopUser", note)
            self.assertIn("acceso denegado", note)
        self.assertFalse(Path(r"C:\Users\NoSuchLaptopUser").exists())

    def test_la_ruta_de_este_usuario_se_respeta(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "fotos"
            folder, note = local_jpg_dir(str(target))
            self.assertEqual(folder, target)
            self.assertEqual(note, "")
            self.assertTrue(target.is_dir())

    def test_sin_ruta_usa_jpg_junto_al_modulo(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("acotacion.ROOT", Path(tmp)):
                folder, note = local_jpg_dir("")
            self.assertEqual(folder, Path(tmp) / "JPG")
            self.assertEqual(note, "")
            self.assertTrue(folder.is_dir())

    def test_ensure_dir_crea_solo_lo_que_falta(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "a" / "b"
            self.assertEqual(ensure_dir(dest), dest)
            self.assertTrue(dest.is_dir())
            self.assertEqual(ensure_dir(dest), dest)


if __name__ == "__main__":
    unittest.main()
