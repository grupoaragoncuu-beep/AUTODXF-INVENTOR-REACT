"""El listado de jobs sale de las carpetas y deja fuera los de más de 15 días."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dossier_arbol import (
    listar_clientes,
    listar_jobs,
    listar_productos,
    publicar_efort_weld,
    quitar_exportacion,
    ruta_efort_weld,
)


class ArbolDossierTests(unittest.TestCase):
    def test_productos_y_clientes_son_las_carpetas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "TANKS", "VANTRAN").mkdir(parents=True)
            Path(tmp, "RADIATORS", "OTC").mkdir(parents=True)
            Path(tmp, "nota.txt").write_text("x", encoding="utf-8")
            productos = listar_productos(raiz=tmp)
            self.assertEqual(productos["nombres"], ["RADIATORS", "TANKS"])
            clientes = listar_clientes("TANKS", raiz=tmp)
            self.assertEqual(clientes["nombres"], ["VANTRAN"])

    def test_un_job_de_mas_de_15_dias_no_aparece(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cliente = Path(tmp, "TANKS", "VANTRAN")
            reciente = cliente / "06-30-2299TANK261632"
            viejo = cliente / "06-30-1000TANK100000"
            reciente.mkdir(parents=True)
            viejo.mkdir()
            (cliente / "leeme.txt").write_text("x", encoding="utf-8")
            ahora = 1_000_000.0

            def edad(path: str) -> float:
                if str(path).endswith("100000"):
                    return ahora - 16 * 86400
                return ahora - 2 * 86400

            res = listar_jobs("TANKS", "VANTRAN", raiz=tmp, ahora=ahora, edad_de=edad)
            self.assertEqual([item["nombre"] for item in res["jobs"]], ["06-30-2299TANK261632"])
            self.assertEqual(res["jobs"][0]["dias"], 2)

    def test_el_dia_15_sigue_y_el_siguiente_no(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cliente = Path(tmp, "TANKS", "VANTRAN")
            (cliente / "JUSTO").mkdir(parents=True)
            (cliente / "PASADO").mkdir()
            ahora = 2_000_000.0

            def edad(path: str) -> float:
                if str(path).endswith("PASADO"):
                    return ahora - (15 * 86400 + 1)
                return ahora - 15 * 86400

            res = listar_jobs("TANKS", "VANTRAN", raiz=tmp, ahora=ahora, edad_de=edad)
            self.assertEqual([item["nombre"] for item in res["jobs"]], ["JUSTO"])

    def test_quitar_vacia_los_jpg_y_deja_el_modelo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            jpgs = Path(tmp, "TANKS", "VANTRAN", "06-30-2299TANK261632", "DOSSIER FILES", "JPGS")
            pieza = jpgs / "PIEZAS_ACOTADAS"
            pieza.mkdir(parents=True)
            (pieza / "cota.jpg").write_text("x", encoding="utf-8")
            modelo = Path(tmp, "TANKS", "VANTRAN", "06-30-2299TANK261632", "MODEL CORE FILES")
            modelo.mkdir()
            (modelo / "tanque.iam").write_text("x", encoding="utf-8")
            (jpgs.parent / "notas.txt").write_text("se queda", encoding="utf-8")
            with patch("dossier_arbol.borrar_filas", return_value=4):
                res = quitar_exportacion("TANKS", "VANTRAN", "06-30-2299TANK261632", raiz=tmp)
            self.assertTrue(res["ok"])
            self.assertEqual(res["filas"], 4)
            self.assertTrue(jpgs.is_dir())
            self.assertEqual(list(jpgs.iterdir()), [])
            self.assertTrue((modelo / "tanque.iam").is_file())
            self.assertTrue((jpgs.parent / "notas.txt").is_file())

    def test_efort_queda_en_el_job_y_no_en_dossier(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp, "TANKS", "VANTRAN", "JOB1")
            job.mkdir(parents=True)
            puntero = Path(tmp, "puntero.txt")
            destino = publicar_efort_weld(
                "TANKS", "VANTRAN", "JOB1", raiz=tmp, puntero=puntero
            )
            self.assertEqual(destino, str(job / "Efort Weld Files"))
            self.assertTrue(Path(destino).is_dir())
            self.assertFalse((job / "DOSSIER FILES").exists())
            self.assertEqual(puntero.read_text(encoding="utf-8"), destino)

    def test_efort_rechaza_un_job_con_separador(self) -> None:
        self.assertEqual(ruta_efort_weld("TANKS", "VANTRAN", r"..\OTRO", raiz=r"X:\A"), "")

    def test_quitar_no_acepta_un_job_con_ruta(self) -> None:
        res = quitar_exportacion("TANKS", "VANTRAN", r"..\OTRO")
        self.assertFalse(res["ok"])


if __name__ == "__main__":
    unittest.main()
