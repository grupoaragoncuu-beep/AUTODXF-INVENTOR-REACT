"""Morfología de maquinado: diámetros, barrenos y escalones, sin origen."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

import referencia_geo as rg
from maquinado_geo import cotas_de, dibujar, morfologia

def _agregar(raw, pts):
    base = len(raw["sv"]) // 3
    for p in pts:
        raw["sv"].extend(float(c) for c in p)
    n = len(pts)
    for i in range(n):
        raw["si"].extend([base + i + 1, base + (i + 1) % n + 1])


def _linea(raw, a, b):
    base = len(raw["sv"]) // 3
    raw["sv"].extend([*a, *b])
    raw["si"].extend([base + 1, base + 2])


def _circulo(z, r, cx=0.0, cy=0.0, n=36):
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return [(cx + r * np.cos(a), cy + r * np.sin(a), z) for a in ang]


def _vacio():
    return {"sv": [], "si": [], "fv": [], "fi": []}


def _tubo():
    raw = _vacio()
    for z in (0.0, 10.0):
        _agregar(raw, _circulo(z, 2.0))
        _agregar(raw, _circulo(z, 1.0))
    return rg.preparar_def(raw)


def _brida():
    raw = _vacio()
    for z in (0.0, 2.0):
        _agregar(raw, _circulo(z, 1.0))
    for z in (2.0, 3.0):
        _agregar(raw, _circulo(z, 3.0))
    for z in (0.0, 3.0):
        _agregar(raw, _circulo(z, 0.4))
    return rg.preparar_def(raw)


def _placa():
    raw = _vacio()
    cara = [(0, 0, 0), (10, 0, 0), (10, 4, 0), (0, 4, 0)]
    techo = [(x, y, 1) for x, y, _z in cara]
    _agregar(raw, cara)
    _agregar(raw, techo)
    for a, b in zip(cara, techo):
        _linea(raw, a, b)
    for z in (0.0, 1.0):
        _agregar(raw, _circulo(z, 0.5, 3, 2))
        _agregar(raw, _circulo(z, 0.5, 7, 2))
    return rg.preparar_def(raw)


class MorfologiaTest(unittest.TestCase):
    def test_tubo_es_diametro_pasado_y_largo(self):
        cotas = {c["name"]: c for c in cotas_de(morfologia(_tubo()), "in")}
        self.assertIn("D_1.575", cotas)
        self.assertIn("D_0.787_PASADO", cotas)
        self.assertIn("L_3.937", cotas)
        self.assertFalse(any(n.startswith("STEP_") or n.startswith("X_") or n.startswith("Y_") for n in cotas))

    def test_brida_separa_escalones_del_barreno(self):
        morf = morfologia(_brida())
        self.assertEqual(morf["kind"], "revolucion")
        nombres = {c["name"] for c in cotas_de(morf, "in")}
        self.assertIn("D_0.315_PASADO", nombres)
        self.assertIn("D_0.787", nombres)
        self.assertIn("D_2.362", nombres)
        self.assertTrue(any(n.startswith("STEP_") and n.endswith("_D0.787") for n in nombres))
        self.assertTrue(any(n.startswith("STEP_") and "D2.362" in n for n in nombres))
        self.assertNotIn("D_2.362_PASADO", nombres)

    def test_placa_mide_tamano_y_distancia_de_barrenos(self):
        morf = morfologia(_placa())
        self.assertEqual(morf["kind"], "placa")
        cotas = {c["name"]: c for c in cotas_de(morf, "in")}
        self.assertAlmostEqual(cotas["W_3.937"]["value"], 10 / 2.54, places=2)
        self.assertAlmostEqual(cotas["H_1.575"]["value"], 4 / 2.54, places=2)
        self.assertIn("THK_0.394", cotas)
        self.assertIn("D_0.394_PASADO_TYP", cotas)
        self.assertIn("CC_1.575", cotas)
        self.assertFalse(any("0.00" == c.get("label", "").split()[1] for c in cotas.values() if c["kind"] != "L"))

    def test_jpg_no_lleva_marca_de_origen(self):
        morf = morfologia(_tubo())
        cota = next(c for c in cotas_de(morf, "in") if c["name"] == "D_0.787_PASADO")
        with tempfile.TemporaryDirectory() as tmp:
            ruta = dibujar(Path(tmp) / "d.jpg", morf, cota, "TUBO  D_0.787_PASADO")
            self.assertGreater(Path(ruta).stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
