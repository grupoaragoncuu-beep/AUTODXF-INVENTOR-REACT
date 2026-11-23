"""El selector de DXF solo ofrece jobs de Ingeniería en proceso y su AutoDXF."""

from __future__ import annotations

import os
import tempfile
import unittest

from vsm_jobs import (
    armar_lista,
    asegurar_autodxf,
    carpeta_autodxf,
    en_proceso_ingenieria,
    publicar_dxf_en_raiz,
)


def _job(numero: str, status: str = "inventor", history=None, local=None, **extra) -> dict:
    fila = {
        "id": extra.pop("id", 1),
        "job_number": numero,
        "client": "VANTRAN",
        "product": "TANKS",
        "quantity": 1,
        "status": status,
        "dxf_count": 14,
        "local_path": local
        or "/mnt/server_data/ARGA METALS CORPORATE SYSTEM/TANKS/VANTRAN/" + numero,
        "history": history
        if history is not None
        else [
            {"stage": "pending", "unit_index": None, "start_time": "2026-11-11T09:00:00", "end_time": "2026-11-11T09:35:00"},
            {"stage": "inventor", "unit_index": None, "start_time": "2026-11-11T09:35:00", "end_time": None},
        ],
    }
    fila.update(extra)
    return fila


class VsmJobsTests(unittest.TestCase):
    def test_vantran_en_proceso_entra_y_el_cerrado_no(self) -> None:
        abierto = _job("VANTRAN PRUEBA 1")
        cerrado = _job(
            "VANTRAN PRUEBA 9",
            history=[
                {
                    "stage": "inventor",
                    "unit_index": None,
                    "start_time": "2026-11-01T09:00:00",
                    "end_time": "2026-11-02T09:00:00",
                }
            ],
        )
        self.assertTrue(en_proceso_ingenieria(abierto))
        self.assertFalse(en_proceso_ingenieria(cerrado))
        self.assertFalse(en_proceso_ingenieria(_job("SUELTO", status="pending", history=[])))

    def test_la_ruta_docker_cae_en_la_unidad_x(self) -> None:
        marca = os.path.normcase(r"X:\ARGA METALS CORPORATE SYSTEM")

        def existe(path: str) -> bool:
            return os.path.normcase(path).startswith(marca)

        destino = carpeta_autodxf(_job("VANTRAN PRUEBA 1")["local_path"], existe=existe)
        self.assertTrue(destino.startswith(r"X:\ARGA METALS CORPORATE SYSTEM"))
        self.assertTrue(destino.endswith(os.path.join("VANTRAN PRUEBA 1", "MODEL CORE FILES", "AutoDXF")))

    def test_sin_unidad_x_usa_el_unc(self) -> None:
        unc = r"\\192.168.2.80\Users\Administrator\Desktop\Grupo Arga Metals\ARGA METALS CORPORATE SYSTEM"

        def existe(path: str) -> bool:
            return str(path).startswith("\\\\192.168.2.80\\")

        destino = carpeta_autodxf(
            _job("VANTRAN PRUEBA 2")["local_path"],
            existe=existe,
            corporate_root=unc,
        )
        self.assertTrue(destino.startswith(unc))
        self.assertTrue(destino.endswith(os.path.join("MODEL CORE FILES", "AutoDXF")))

    def test_una_ruta_fuera_del_share_no_se_ofrece(self) -> None:
        raro = _job("OTRO", local=r"C:\temp\OTRO")
        res = armar_lista([raro, _job("VANTRAN PRUEBA 1")], existe=lambda path: "VANTRAN PRUEBA 1" in path or path.startswith("X:\\"))
        numeros = [item["job_number"] for item in res["jobs"]]
        self.assertEqual(numeros, ["VANTRAN PRUEBA 1"])
        self.assertIn("sin carpeta", res["message"])

    def test_publicar_sube_el_dxf_y_no_toca_processed_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raiz = os.path.join(tmp, "ARGA METALS CORPORATE SYSTEM", "TANKS", "VANTRAN", "JOB", "MODEL CORE FILES", "AutoDXF")
            cal = os.path.join(raiz, "Cal 0.25 A36")
            processed = os.path.join(raiz, "Processed Files")
            os.makedirs(cal)
            os.makedirs(processed)
            abierto = os.path.join(cal, "TAPA, A36, QTY 4, Cal 0.25.dxf")
            viejo = os.path.join(raiz, "TAPA, A36, QTY 4, Cal 0.25.dxf")
            with open(abierto, "w", encoding="utf-8") as f:
                f.write("nuevo")
            with open(viejo, "w", encoding="utf-8") as f:
                f.write("viejo")
            with open(os.path.join(processed, "TAPA, A36, QTY 4, Cal 0.25.dxf"), "w", encoding="utf-8") as f:
                f.write("ans")
            res = publicar_dxf_en_raiz(raiz)
            self.assertTrue(res["ok"])
            self.assertEqual(res["movidos"], 1)
            with open(viejo, encoding="utf-8") as f:
                self.assertEqual(f.read(), "nuevo")
            self.assertFalse(os.path.exists(abierto))
            self.assertFalse(os.path.isdir(cal))
            self.assertTrue(os.path.exists(os.path.join(processed, "TAPA, A36, QTY 4, Cal 0.25.dxf")))

    def test_asegurar_no_crea_fuera_del_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job = os.path.join(tmp, "ARGA METALS CORPORATE SYSTEM", "TANKS", "VANTRAN", "JOB")
            os.makedirs(job)
            destino = os.path.join(job, "MODEL CORE FILES", "AutoDXF")
            res = asegurar_autodxf(destino)
            self.assertTrue(res["ok"])
            self.assertTrue(os.path.isdir(destino))
            fuera = asegurar_autodxf(os.path.join(tmp, "otro", "AutoDXF"))
            self.assertFalse(fuera["ok"])


if __name__ == "__main__":
    unittest.main()
