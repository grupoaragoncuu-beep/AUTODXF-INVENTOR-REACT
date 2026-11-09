import unittest
from pathlib import Path
from unittest.mock import patch

import awis_run


class AwisRunTest(unittest.TestCase):
    def test_rechaza_un_paso_desconocido(self):
        result = awis_run.run_awis("otro")
        self.assertFalse(result["ok"])
        self.assertIn("desconocido", result["message"])

    def test_el_modulo_usa_el_exe_empaquetado(self):
        found = awis_run.awis_exe()
        self.assertIsNotNone(found)
        self.assertEqual(found, awis_run._EMPAQUETADO)
        self.assertTrue(found.is_file())

    def test_solids_resume_el_conteo(self):
        log = "Assembly: TANK.iam\nSolids: 12\nSkipped: 1\n"
        with patch.object(awis_run, "awis_exe", return_value=Path("FaceDrawingVerify.exe")), patch(
            "awis_run.subprocess.run"
        ) as run:
            run.return_value.returncode = 0
            run.return_value.stdout = log.encode()
            run.return_value.stderr = b""
            result = awis_run.run_awis("solids")
        self.assertTrue(result["ok"])
        self.assertIn("12", result["message"])
        self.assertEqual(run.call_args.args[0][1], "--solids")


if __name__ == "__main__":
    unittest.main()
