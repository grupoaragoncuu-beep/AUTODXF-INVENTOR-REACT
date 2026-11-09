"""La ruta del dossier sale de erp_jobs: PRODUCTO\\CLIENTE\\job."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from acotacion import _dossier_path, _segmentos_dossier


class RutaDossierTests(unittest.TestCase):
    def test_producto_cliente_y_job(self) -> None:
        ruta = _segmentos_dossier(
            r"\\srv\ARGA METALS CORPORATE SYSTEM",
            "TANKS",
            "VANTRAN",
            "06-30-2467TANK261079",
            "DOSSIER FILES",
            "JPGS",
        )
        self.assertTrue(
            ruta.endswith(
                r"\TANKS\VANTRAN\06-30-2467TANK261079\DOSSIER FILES\JPGS"
            )
        )

    def test_sin_cliente_no_inventa_carpeta(self) -> None:
        ruta = _segmentos_dossier(
            r"\\srv\ARGA METALS CORPORATE SYSTEM",
            "TANKS",
            "",
            "06-30-2467TANK261079",
            "DOSSIER FILES",
            "JPGS",
        )
        self.assertTrue(
            ruta.endswith(r"\TANKS\06-30-2467TANK261079\DOSSIER FILES\JPGS")
        )

    def test_la_carpeta_corporativa_no_es_producto(self) -> None:
        ruta = _segmentos_dossier(
            r"\\srv\ARGA METALS CORPORATE SYSTEM",
            "ARGA METALS CORPORATE SYSTEM",
            "TANKS",
            "06-30-2467TANK261079",
            "DOSSIER FILES",
            "JPGS",
        )
        self.assertNotIn(r"SYSTEM\ARGA METALS CORPORATE SYSTEM", ruta)
        self.assertTrue(ruta.endswith(r"\TANKS\06-30-2467TANK261079\DOSSIER FILES\JPGS"))

    def test_el_job_sale_de_la_carpeta_elegida(self) -> None:
        cfg = {
            "paths": {
                "corporateRoot": r"\\srv\ARGA METALS CORPORATE SYSTEM",
                "dossierFolder": "DOSSIER FILES",
                "jpgsFolder": "JPGS",
            }
        }
        with patch(
            "acotacion.cargar_eleccion",
            return_value={
                "producto": "TANKS",
                "cliente": "VANTRAN",
                "job": "06-30-2467TANK261079",
                "raiz": r"\\srv\ARGA METALS CORPORATE SYSTEM",
            },
        ):
            ruta = _dossier_path(cfg, {"dossierProduct": "TANKS"}, "", "", "06-30-2467TANK261079")
        self.assertTrue(
            ruta.endswith(r"\TANKS\VANTRAN\06-30-2467TANK261079\DOSSIER FILES\JPGS")
        )


if __name__ == "__main__":
    unittest.main()
