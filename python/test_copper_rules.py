"""Cobre solo con morfología de solera y nombre. Un A36 no se fuerza a CU."""

import unittest

from inventor_session import decide_copper


class CopperRules(unittest.TestCase):
    def test_busbar_plano_por_nombre_y_solera(self):
        ok, form, why = decide_copper("GENE-FCU-5-102", "Genérico", 4.0, 20.0, 0)
        self.assertTrue(ok)
        self.assertEqual(form, "F")
        self.assertIn("GENE", why)

    def test_busbar_doblado(self):
        ok, form, _why = decide_copper("ABB-42-BCK-728", "Genérico", 5.0, 12.0, 1)
        self.assertTrue(ok)
        self.assertEqual(form, "B")

    def test_a36_no_es_cobre_aunque_el_nombre_coincida(self):
        ok, form, why = decide_copper("GENE-FCU-5-102", "A 36", 4.0, 20.0, 0)
        self.assertFalse(ok)
        self.assertEqual(form, "")
        self.assertEqual(why, "A 36")

    def test_tanque_a36_ancho_no_es_cobre(self):
        ok, _form, why = decide_copper("FRONT WALL TOP PLATE", "Acero, carbono", 40.0, 80.0, 0)
        self.assertFalse(ok)
        self.assertEqual(why, "A 36")

    def test_tanque_generico_sin_nombre_de_busbar(self):
        ok, _form, why = decide_copper("BASE TOP PLATE", "Genérico", 8.0, 16.0, 0)
        self.assertFalse(ok)
        self.assertEqual(why, "Sin nomenclatura de cobre")

    def test_lamina_ancha_no_es_solera(self):
        ok, _form, why = decide_copper("CU-BUS", "Genérico", 18.0, 40.0, 0)
        self.assertFalse(ok)
        self.assertEqual(why, "No es solera")

    def test_cubierta_no_dispara_cu(self):
        ok, _form, why = decide_copper("CUBIERTA TANQUE", "Genérico", 6.0, 20.0, 0)
        self.assertFalse(ok)
        self.assertEqual(why, "Sin nomenclatura de cobre")

    def test_generico_con_acento_es_generico(self):
        from inventor_session import _is_generic_material

        self.assertTrue(_is_generic_material("Genérico"))
        self.assertTrue(_is_generic_material("Generic"))


if __name__ == "__main__":
    unittest.main()
