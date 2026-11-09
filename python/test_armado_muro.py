"""El Segmento, Top y Base no son un kit. JACKING PADS sí."""

import unittest

from armado_kit import es_muro_nombre


class MuroKit(unittest.TestCase):
    def test_segmento_top_y_base_son_muro(self):
        for nombre in (
            "Assembly Segmento 2",
            "Top Cover",
            "Tank-Lid",
            "Tank Base",
            "Base",
            "Base de soleras",
            "Tapa",
        ):
            self.assertTrue(es_muro_nombre(nombre), nombre)

    def test_jacking_pads_y_flange_no_son_muro(self):
        for nombre in (
            "JACKING PADS ASSEMBLY",
            "PIPE FLANGE 0.250",
            "Solera Jacking Pad",
            "Parking Stand w base",
        ):
            self.assertFalse(es_muro_nombre(nombre), nombre)


if __name__ == "__main__":
    unittest.main()
