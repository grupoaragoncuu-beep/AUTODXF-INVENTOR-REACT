"""Invariante: un lazo interno no se parte en N barrenos si es un recorte 2D.

Cada barreno real llega como su propio lazo (bbox ~Ø). Ventana redondeada
(S2 y cualquier otra placa) es un solo lazo con arcos de esquina.
"""

from __future__ import annotations

import unittest

from acotacion_run import _huecos_de_lazo, _lazo_es_recorte_2d


def _rect(x: float, y: float, w: float, h: float) -> list[tuple[float, float]]:
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]


def _esquinas(x: float, y: float, w: float, h: float, dia: float) -> list[dict]:
    r = dia / 2
    return [
        {"x": x + r, "y": y + r, "dia": dia},
        {"x": x + w - r, "y": y + r, "dia": dia},
        {"x": x + r, "y": y + h - r, "dia": dia},
        {"x": x + w - r, "y": y + h - r, "dia": dia},
    ]


class HuecosLazoTest(unittest.TestCase):
    def test_s2_ventana_no_es_cuatro_barrenos(self) -> None:
        poly = _rect(6.25, 48.688, 27.5, 6.0)
        circles = _esquinas(6.25, 48.688, 27.5, 6.0, 1.0)
        huecos = _huecos_de_lazo(circles, poly)
        self.assertEqual([h["kind"] for h in huecos], ["cut"])
        self.assertFalse(any(h.get("kind") == "circle" for h in huecos))
        self.assertGreaterEqual(len(huecos[0]["pts"]), 4)

    def test_ventana_cuadrada_filetes(self) -> None:
        poly = _rect(2, 2, 8, 8)
        huecos = _huecos_de_lazo(_esquinas(2, 2, 8, 8, 0.5), poly)
        self.assertEqual([h["kind"] for h in huecos], ["cut"])

    def test_dos_arcos_en_ventana_siguen_siendo_cut(self) -> None:
        poly = _rect(6.25, 48.688, 27.5, 6.0)
        circles = _esquinas(6.25, 48.688, 27.5, 6.0, 1.0)[:2]
        huecos = _huecos_de_lazo(circles, poly)
        self.assertEqual([h["kind"] for h in huecos], ["cut"])

    def test_barreno_suelto_es_circulo(self) -> None:
        poly = _rect(10, 20, 1.0, 1.0)
        huecos = _huecos_de_lazo([{"x": 10.5, "y": 20.5, "dia": 1.0}], poly)
        self.assertEqual([h["kind"] for h in huecos], ["circle"])
        self.assertAlmostEqual(huecos[0]["dia"], 1.0)

    def test_cuatro_barrenos_son_cuatro_lazos(self) -> None:
        """2×2 real: cada Ø es un lazo aparte; no se fusionan aquí."""
        kinds = []
        for x, y in ((5.0, 10.0), (32.0, 10.0), (5.0, 16.0), (32.0, 16.0)):
            poly = _rect(x - 0.5, y - 0.5, 1.0, 1.0)
            huecos = _huecos_de_lazo([{"x": x, "y": y, "dia": 1.0}], poly)
            kinds.extend(h["kind"] for h in huecos)
        self.assertEqual(kinds, ["circle", "circle", "circle", "circle"])

    def test_slot_estadio_no_es_cut(self) -> None:
        dia = 1.0
        poly = _rect(4.0, 10.0, 6.0, 1.0)
        circles = [{"x": 4.5, "y": 10.5, "dia": dia}, {"x": 9.5, "y": 10.5, "dia": dia}]
        huecos = _huecos_de_lazo(circles, poly)
        self.assertEqual([h["kind"] for h in huecos], ["slot"])

    def test_cadena_colininea_no_es_ventana(self) -> None:
        poly = _rect(0.0, 0.0, 12.0, 1.0)
        circles = [{"x": 0.5 + i * 3.5, "y": 0.5, "dia": 1.0} for i in range(4)]
        self.assertFalse(_lazo_es_recorte_2d(circles, poly))
        huecos = _huecos_de_lazo(circles, poly)
        self.assertGreaterEqual(sum(1 for h in huecos if h["kind"] == "circle"), 3)
        self.assertFalse(any(h.get("kind") == "cut" and h.get("acota") is not False for h in huecos))

    def test_sin_circulos_no_inventa_cut_aqui(self) -> None:
        self.assertEqual(_huecos_de_lazo([], _rect(0, 0, 10, 4)), [])


if __name__ == "__main__":
    unittest.main()
