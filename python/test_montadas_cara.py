"""Selección inteligente de muros: solo lo montado en la cara exterior de ESA placa.

Tanque de prueba (cm), centro en el origen: 100 (X) × 80 (Y) × 60 (Z), placas de 1 cm.
SEGM1 = frente +Z, SEGM2 = derecha +X.
"""

from __future__ import annotations

import unittest

from roles_muros import marco_cara, montadas_en_cara

CENTRO = (0.0, 0.0, 0.0)


def caja(x0, y0, z0, x1, y1, z1):
    return ((x0, y0, z0), (x1, y1, z1))


def muro(caja_placa, normal, exterior_pt):
    return marco_cara(normal, [exterior_pt], caja_placa, CENTRO)


FRENTE = caja(-50, -40, 29, 50, 40, 30)
DERECHA = caja(49, -40, -30, 50, 40, 30)
MARCOS = {
    "S1": muro(FRENTE, (0, 0, -1), (0, 0, 30)),
    "S2": muro(DERECHA, (1, 0, 0), (50, 0, 0)),
    "S3": muro(caja(-50, -40, -30, 50, 40, -29), (0, 0, 1), (0, 0, -30)),
    "S4": muro(caja(-50, -40, -30, -49, 40, 30), (-1, 0, 0), (-50, 0, 0)),
}


def nombres(rows):
    return sorted(r["n"] for r in rows)


class MontadasCaraTest(unittest.TestCase):
    def test_normal_apunta_afuera_aunque_la_cara_venga_invertida(self) -> None:
        self.assertEqual(MARCOS["S1"]["n"], (0.0, 0.0, 1.0))
        self.assertAlmostEqual(MARCOS["S1"]["exterior"], 30.0)

    def test_solo_cara_exterior_del_frente(self) -> None:
        piezas = [
            {"n": "brida", "caja": caja(-5, 0, 30, 5, 10, 34)},
            {"n": "niple_pasa", "caja": caja(10, 0, 20, 14, 4, 36)},
            {"n": "placa_dato", "caja": caja(-20, 20, 30, -10, 26, 30.1)},
            {"n": "brace_interior", "caja": caja(-30, -10, 22, 30, -6, 29)},
            {"n": "oreja_de_S2", "caja": caja(50, 10, 20, 56, 16, 28)},
            {"n": "esquina_S2_toca_canto", "caja": caja(50, -30, 26, 55, -20, 30.2)},
            {"n": "lejos", "caja": caja(0, 0, 80, 4, 4, 84)},
        ]
        got = montadas_en_cara("S1", MARCOS["S1"], piezas, MARCOS)
        self.assertEqual(nombres(got), ["brida", "niple_pasa", "placa_dato"])

    def test_tornilleria_sobre_lo_montado_sin_cruzar_muro(self) -> None:
        piezas = [
            {"n": "brida", "caja": caja(-5, 0, 30, 5, 10, 34)},
            {"n": "tornillo", "caja": caja(-4, 1, 34, -3, 2, 37)},
            {"n": "tuerca_en_tornillo", "caja": caja(-4.5, 0.5, 37, -2.5, 2.5, 38)},
            {"n": "flotando", "caja": caja(20, 20, 40, 22, 22, 42)},
        ]
        got = montadas_en_cara("S1", MARCOS["S1"], piezas, MARCOS)
        self.assertEqual(nombres(got), ["brida", "tornillo", "tuerca_en_tornillo"])

    def test_pieza_de_esquina_va_al_muro_donde_sobresale(self) -> None:
        lug = {"n": "lug_S2", "caja": caja(50, 30, 24, 58, 38, 29)}
        self.assertEqual(montadas_en_cara("S1", MARCOS["S1"], [lug], MARCOS), [])
        self.assertEqual(nombres(montadas_en_cara("S2", MARCOS["S2"], [lug], MARCOS)), ["lug_S2"])

    def test_cadena_no_salta_al_muro_vecino(self) -> None:
        piezas = [
            {"n": "angulo_borde", "caja": caja(44, 0, 30, 50, 4, 33)},
            {"n": "tubo_en_S2", "caja": caja(50, 0, 25, 60, 4, 31)},
        ]
        got = montadas_en_cara("S1", MARCOS["S1"], piezas, MARCOS)
        self.assertEqual(nombres(got), ["angulo_borde"])


if __name__ == "__main__":
    unittest.main()
