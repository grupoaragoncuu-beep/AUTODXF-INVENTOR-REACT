"""Nombre de carpeta, recorte y JPG de soldadura, sin Inventor."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

import weld_anotation as weld
import weld_jpg


class WeldAnotationTests(unittest.TestCase):
    def test_token_de_tanque_con_espacios(self):
        self.assertEqual(weld.safe_token("Tank Assembly"), "Tank_Assembly")
        self.assertEqual(weld.safe_token("GIGA TANK PARAMETRIC DESIGN"), "GIGA_TANK_PARAMETRIC_DESIGN")
        self.assertEqual(weld.safe_token("10000-1246-A01"), "10000-1246-A01")

    def test_resuelve_dwg_y_si_falta_el_idw(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AWIS_FACE_DRAWING_Tank_Assembly.dwg").write_bytes(b"dwg")
            found = weld.resolve_drawing_path(root, "Tank Assembly", "face")
            self.assertIsNotNone(found)
            self.assertEqual(found.name, "AWIS_FACE_DRAWING_Tank_Assembly.dwg")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AWIS_FACE_DRAWING_GIGA_TANK_PARAMETRIC_DESIGN.idw").write_bytes(b"idw")
            found = weld.resolve_drawing_path(root, "GIGA TANK PARAMETRIC DESIGN", "face")
            self.assertIsNotNone(found)
            self.assertTrue(found.name.endswith(".idw"))

    def test_plano_de_cotas_y_carpeta_de_salida(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AWIS_WELD_DIMS_Tank_Assembly.dwg").write_bytes(b"dwg")
            payload = {"awisDir": str(root), "assemblyName": "Tank Assembly.iam", "kind": "dims", "job": "5523 Tank"}
            found = weld.find_drawing(payload, "dims")
            self.assertEqual(found.name, "AWIS_WELD_DIMS_Tank_Assembly.dwg")
            dest = weld.output_folder(str(root / "jpg"), "5523 Tank", create=True)
            self.assertEqual(dest.name, "WELD_ANOTATION")
            self.assertEqual(dest.parent.name, "5523_Tank")
            self.assertTrue(dest.is_dir())

    def test_recorte_de_hoja_cuando_la_camara_tiene_margen(self):
        box = weld.sheet_pixel_box(1000, 500, 50, 25, 120, 60, 0, 0, 100, 50)
        self.assertIsNotNone(box)
        x1, y1, x2, y2 = box
        self.assertGreater(x1, 0)
        self.assertGreater(y1, 0)
        self.assertLess(x2, 1000)
        self.assertLess(y2, 500)

    def test_hoja_ya_encuadrada_no_se_recorta(self):
        self.assertIsNone(weld.sheet_pixel_box(1000, 500, 50, 25, 100, 50, 0, 0, 100, 50))

    def test_compose_recorta_y_guarda_el_trazo(self):
        image = Image.new("RGB", (200, 120), (255, 255, 255))
        for x in range(40, 150):
            for y in range(30, 90):
                image.putpixel((x, y), (10, 10, 10))
        framed = weld.compose_sheet_jpg(image, (20, 10, 170, 100))
        self.assertLess(framed.size[0], 200)
        self.assertGreater(framed.size[0], 80)

    def test_la_pauta_vantran_sigue_los_planos(self):
        import weld_juntas as juntas

        juntas_pauta = juntas.aplicar_pauta_vantran(
            [
                {"kind": "hermetico", "id": "SEGM2_SEGM1", "title": "SEGM2 / SEGM1", "weld": {"leg": "6", "other": "8", "pitch": "100-300", "sides": 2}},
                {"kind": "hermetico", "id": "SEGM2_BASE", "title": "SEGM2 / BASE", "weld": {"leg": "6", "other": "8", "pitch": "100-300", "sides": 2}},
                {"kind": "accesorio", "title": "SEGM1 / Pipe Flange .25", "weld": {"leg": "3", "sides": 1}},
                {"kind": "accesorio", "title": "SEGM4 / Pipe Half Nipple", "weld": {"leg": "5", "sides": 1}},
                {"kind": "accesorio", "title": "SEGM2 / D3000 Lifting Lug", "weld": {"leg": "6", "sides": 1}},
                {"kind": "accesorio", "title": "BASE / 261080_Tank-Base", "weld": {"leg": "6", "sides": 1}},
                {"kind": "accesorio", "title": "SEGM1 / Brace-Side", "weld": {"leg": "5", "pitch": "10-60", "sides": 1}},
                {"kind": "accesorio", "title": "SEGM2 / Jacking_pad_41", "weld": {"leg": "5", "sides": 2}},
                {"kind": "accesorio", "title": "SEGM1 / H.V_parking_Std_26", "weld": {"leg": "5", "sides": 2}},
            ]
        )
        pared, base, brida, niple, oreja, marco, brace, jacking, parking = (item["weld"] for item in juntas_pauta)
        self.assertEqual(pared["leg"], "6")
        self.assertEqual(pared["other"], "6")
        self.assertEqual(pared["pitch"], "")
        self.assertEqual(base["leg"], "6")
        self.assertEqual(base["other"], "6")
        self.assertEqual(base["pitch"], "")
        self.assertEqual(brida["leg"], "6")
        self.assertEqual(niple["leg"], "6")
        self.assertEqual(oreja["leg"], "9.525")
        self.assertEqual(marco["leg"], "8")
        self.assertEqual(marco["other"], "8")
        self.assertEqual(marco["pitch"], "")
        self.assertEqual(marco["pitch_other"], "4-20")
        self.assertEqual(marco["sides"], 2)
        self.assertEqual(brace["leg"], "5")
        self.assertEqual(brace["pitch"], "10-60")
        self.assertEqual(jacking["leg"], "6")
        self.assertEqual(parking["leg"], "3")
        import weld_nomenclatura as nom

        hoja = nom.presentar_weld(marco, "in")
        self.assertEqual(hoja["leg"], "5/16")
        self.assertEqual(hoja["pitch_other"], "4-20")
        self.assertEqual(nom.presentar_weld(oreja, "in")["leg"], "3/8")
        self.assertEqual(nom.presentar_weld(pared, "in")["leg"], "1/4")
        self.assertEqual(nom.presentar_weld(pared, "in")["pitch"], "")

    def test_cordon_entre_base_y_segmento(self):
        import weld_juntas as juntas

        segmento = [(0, y, z) for y in (0, 2000) for z in (0, 1600)]
        base = [(x, 0, z) for x in (0, 800) for z in (0, 1600)]
        muros = {
            "SEGM1": juntas.marco_cara((1, 0, 0), segmento),
            "BASE": juntas.marco_cara((0, -1, 0), base),
        }
        halladas = juntas.armar_juntas(muros, [])
        cordon = next(item for item in halladas if item["id"] == "SEGM1_BASE")
        self.assertEqual(cordon["weld"]["length"], "1600 mm")
        self.assertEqual(cordon["weld"]["leg"], "6")
        self.assertEqual(cordon["weld"]["other"], "8")
        self.assertEqual(cordon["weld"]["pitch"], "100-300")
        self.assertEqual(len(set(muros["SEGM1"]["outline"])), 4)
        self.assertIsNotNone(cordon["weld"]["footprint"])
        solidos = juntas.cordones(cordon)
        self.assertEqual(len(solidos), 1)
        self.assertGreater(solidos[0]["largo"], 100)
        self.assertEqual(solidos[0]["color"], "hermetico")
        self.assertLess(solidos[0]["normal"][0], 0)

    def test_la_tapa_suelta_no_se_suelda_y_la_base_solo_en_los_cabezales(self):
        import weld_juntas as juntas

        class Tapa:
            Name = "261080_Tank-LID_11"

        def muro(normal, puntos):
            cara = juntas.marco_cara(normal, puntos)
            cara["puntos"] = puntos
            return cara

        muros = {
            "BASE": muro((0, -1, 0), [(x, 0, z) for x in (0, 2000) for z in (0, 800)]),
            "TOP": muro((0, 1, 0), [(x, 1600, z) for x in (0, 2000) for z in (0, 800)]),
            "SEGM1": muro((0, 0, -1), [(x, y, 0) for x in (0, 2000) for y in (0, 1600)]),
            "SEGM3": muro((0, 0, 1), [(x, y, 800) for x in (0, 2000) for y in (0, 1600)]),
            "SEGM2": muro((1, 0, 0), [(0, y, z) for y in (0, 1600) for z in (0, 800)]),
            "SEGM4": muro((-1, 0, 0), [(2000, y, z) for y in (0, 1600) for z in (0, 800)]),
        }
        muros["TOP"]["occ"] = Tapa()
        ids = {item["id"] for item in juntas.armar_juntas(muros, [])}
        self.assertIn("SEGM1_BASE", ids)
        self.assertIn("SEGM2_BASE", ids)
        self.assertIn("SEGM3_BASE", ids)
        self.assertIn("SEGM4_BASE", ids)
        self.assertFalse(any("TOP" in ident for ident in ids))
        self.assertIn("SEGM2_SEGM1", ids)
        self.assertIn("SEGM2_SEGM3", ids)
        self.assertIn("SEGM4_SEGM3", ids)
        self.assertIn("SEGM4_SEGM1", ids)
        self.assertNotIn("SEGM1_SEGM2", ids)
        self.assertNotIn("SEGM3_SEGM4", ids)
        self.assertNotIn("SEGM1_SEGM4", ids)

    def test_accesorio_usa_la_cara_interior_del_segmento(self):
        import weld_juntas as juntas

        exterior = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), [], [])
        interior = (
            (8.0, 0.0, 0.0),
            (-1.0, 0.0, 0.0),
            [((8.0, 0.0, 0.0), (8.0, 900.0, 0.0))],
            [],
        )
        origen, normal, aristas, _anillos = juntas._mejor_contacto([exterior, interior])
        self.assertAlmostEqual(origen[0], 8.0, delta=0.01)
        self.assertEqual(len(aristas), 1)
        self.assertLess(normal[0], 0)
        misma = [((8.0, 0.0, 0.0), (8.0, 400.0, 0.0))]
        afuera, _normal, _aristas, _anillos = juntas._mejor_contacto(
            [
                ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), misma, []),
                ((8.0, 0.0, 0.0), (1.0, 0.0, 0.0), misma, []),
            ],
            (-30.0, 200.0, 0.0),
        )
        self.assertAlmostEqual(afuera[0], 0.0, delta=0.01)

    def test_el_cancamo_no_suelda_la_ranura_ni_la_horquilla(self):
        import weld_juntas as juntas

        exterior = [
            ((0.0, 0.0, 0.0), (0.0, 180.0, 0.0)),
            ((0.0, 180.0, 0.0), (90.0, 180.0, 0.0)),
            ((90.0, 180.0, 0.0), (90.0, 0.0, 0.0)),
            ((90.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
        ]
        ranura = ((20.0, 150.0, 0.0), (70.0, 150.0, 0.0))
        horquilla = ((25.0, 30.0, 0.0), (65.0, 30.0, 0.0))
        quedaron = juntas._contorno_exterior(exterior + [ranura, horquilla], (0.0, 0.0, 1.0))
        medios = {((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0) for a, b in quedaron}
        self.assertIn((0.0, 90.0), medios)
        self.assertIn((90.0, 90.0), medios)
        self.assertNotIn((45.0, 150.0), medios)
        self.assertNotIn((45.0, 30.0), medios)

    def test_la_solera_interna_del_bastidor_no_la_traga_el_casco(self):
        import weld_juntas as juntas

        marco = [
            ((0.0, 0.0, 0.0), (2000.0, 0.0, 0.0)),
            ((0.0, 900.0, 0.0), (2000.0, 900.0, 0.0)),
            ((0.0, 0.0, 0.0), (0.0, 900.0, 0.0)),
            ((2000.0, 0.0, 0.0), (2000.0, 900.0, 0.0)),
        ]
        barra = [
            ((0.0, 440.0, 0.0), (2000.0, 440.0, 0.0)),
            ((0.0, 456.0, 0.0), (2000.0, 456.0, 0.0)),
        ]
        quedaron = juntas._contorno_exterior(marco + barra, (0.0, 0.0, 1.0))
        centros = [((a[1] + b[1]) / 2.0) for a, b in quedaron]
        self.assertTrue(any(430.0 < valor < 470.0 for valor in centros))

    def test_la_base_no_usa_la_cara_del_piso(self):
        import weld_juntas as juntas

        arriba = (
            (0.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            [((0.0, 0.0, 0.0), (800.0, 0.0, 0.0))],
            [],
        )
        piso = (
            (0.0, -8.0, 0.0),
            (0.0, -1.0, 0.0),
            [((0.0, -8.0, 0.0), (800.0, -8.0, 0.0))],
            [],
        )
        caras = juntas._caras_hacia_el_tanque([arriba, piso], (400.0, 800.0, 0.0))
        self.assertEqual(len(caras), 1)
        self.assertAlmostEqual(caras[0][0][1], 0.0, delta=0.01)

    def test_la_solera_bajo_la_base_se_suelda_en_la_cara_que_toca(self):
        import weld_juntas as juntas

        arriba = (
            (0.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            [((0.0, 0.0, 0.0), (800.0, 0.0, 0.0))],
            [],
        )
        abajo = (
            (0.0, -8.0, 0.0),
            (0.0, -1.0, 0.0),
            [((0.0, -8.0, 0.0), (800.0, -8.0, 0.0))],
            [],
        )
        self.assertTrue(juntas._pieza_del_lado_del_tanque([arriba, abajo], (400.0, 40.0, 0.0), (400.0, 800.0, 0.0)))
        self.assertFalse(juntas._pieza_del_lado_del_tanque([arriba, abajo], (400.0, -30.0, 0.0), (400.0, 800.0, 0.0)))

    def test_la_brida_cuenta_aunque_no_tenga_arista_recta(self):
        import weld_juntas as juntas

        circulo = {"centro": (40.0, 40.0, 0.0), "normal": (0.0, 0.0, 1.0), "radio": 19.0}
        self.assertTrue(juntas._hay_apoyo([], [circulo], [((0.0, 0.0, 0.0), (0.0, 0.0, 1.0))]))
        self.assertFalse(juntas._hay_apoyo([], [circulo], [((0.0, 0.0, 30.0), (0.0, 0.0, 1.0))]))

    def test_el_accesorio_solo_se_suelda_a_su_segmento(self):
        import weld_juntas as juntas

        segm1 = {
            "normal": (0.0, 0.0, 1.0),
            "origen": (0.0, 0.0, 0.0),
            "u": (1.0, 0.0, 0.0),
            "v": (0.0, 1.0, 0.0),
            "outline": [(0.0, 0.0), (400.0, 0.0), (400.0, 400.0), (0.0, 400.0)],
            "occ": None,
        }
        segm2 = {
            "normal": (1.0, 0.0, 0.0),
            "origen": (10.0, 0.0, 0.0),
            "u": (0.0, 1.0, 0.0),
            "v": (0.0, 0.0, 1.0),
            "outline": [(0.0, 0.0), (200.0, 0.0), (200.0, 200.0), (0.0, 200.0)],
            "occ": None,
        }
        pieza = {
            "cara": "SEGM1",
            "occ": None,
            "puntos": [(10.0, 20.0, 0.0), (90.0, 20.0, 0.0), (90.0, 60.0, 40.0), (10.0, 60.0, 40.0)],
        }
        self.assertEqual(juntas._caras_de_apoyo(pieza, {"SEGM1": segm1, "SEGM2": segm2}), ["SEGM1"])
        pieza["cara"] = "BASE"
        base = {
            "normal": (0.0, 1.0, 0.0),
            "origen": (0.0, 400.0, 0.0),
            "u": (1.0, 0.0, 0.0),
            "v": (0.0, 0.0, 1.0),
            "outline": [(0.0, 0.0), (400.0, 0.0), (400.0, 400.0), (0.0, 400.0)],
            "occ": None,
        }
        self.assertEqual(juntas._caras_de_apoyo(pieza, {"BASE": base, "SEGM1": segm1}), [])

    def test_el_ensamble_nuevo_equivale_al_nombre_pintado(self):
        from weld_anotation import _raiz_nombre

        pares = (
            ("261080_Tank-Base_Default<As Machined>_21", "261080_Tank-Base_Default_As_Machined_:1"),
            ("261080_1 Drain Valve Box_49", "261080_1_Drain_Valve_Box:1"),
            ("261080_1 Drain Valve Box_50", "261080_1_Drain_Valve_Box:2"),
            ("Jacking pad_41", "Jacking_pad:1"),
        )
        for pintado, ensamble in pares:
            self.assertEqual(_raiz_nombre(pintado), _raiz_nombre(ensamble))
            self.assertTrue(_raiz_nombre(pintado))

    def test_brida_se_suelda_por_el_circulo_exterior(self):
        import weld_juntas as juntas

        circulos = [
            {"centro": (0.0, 0.0, 0.0), "normal": (0.0, 1.0, 0.0), "radio": 11.9},
            {"centro": (0.0, 0.0, 0.0), "normal": (0.0, 1.0, 0.0), "radio": 19.1},
            {"centro": (0.0, 8.0, 0.0), "normal": (0.0, 1.0, 0.0), "radio": 40.0},
            {"centro": (0.0, 25.4, 0.0), "normal": (0.0, 1.0, 0.0), "radio": 30.0},
        ]
        anillos = juntas._anillos_exteriores(circulos, (0.0, 0.0, 0.0), (0.0, 1.0, 0.0), 12.0)
        self.assertEqual(len(anillos), 1)
        self.assertAlmostEqual(anillos[0]["radio"], 19.1, delta=0.01)

    def test_filete_sale_de_la_pieza_sobre_la_placa(self):
        import weld_juntas as juntas

        inicio = (0.0, 0.0, 0.0)
        fin = (400.0, 0.0, 0.0)
        solidos = juntas._filetes_de_arista("PAD", "accesorio", inicio, fin, (0.0, 1.0, 0.0), (200.0, 12.0, 40.0), 6, False, 6)
        self.assertEqual(len(solidos), 1)
        lado = solidos[0]["lado"]
        self.assertLess(lado[2], -0.9)
        self.assertGreater(solidos[0]["normal"][1], 0.9)
        self.assertAlmostEqual(solidos[0]["largo"], 400.0, delta=0.1)

    def test_el_filete_hermetico_queda_por_fuera(self):
        import weld_juntas as juntas

        interior = ((0.0, 2000.0, 0.0), (0.0, 2000.0, 1600.0))
        exterior = ((-8.0, 2000.0, 0.0), (-8.0, 2000.0, 1600.0))
        centro = (400.0, 1000.0, 800.0)
        afuera = juntas._solo_externos([interior, exterior], centro)
        self.assertEqual(len(afuera), 1)
        self.assertAlmostEqual(afuera[0][0][0], -8.0, delta=0.01)
        solidos = juntas._filete_por_fuera("TAPA", "hermetico", afuera[0][0], afuera[0][1], (1.0, 0.0, 0.0), centro, 6)
        self.assertEqual(len(solidos), 1)
        self.assertLess(solidos[0]["normal"][0], 0)
        self.assertGreater(solidos[0]["lado"][1], 0.9)

    def test_elige_la_piel_externa_del_muro_y_la_cara_que_mira_al_tanque(self):
        import weld_juntas as juntas

        centro = (400.0, 1000.0, 800.0)
        planos_muro = [((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)), ((-8.0, 0.0, 0.0), (1.0, 0.0, 0.0))]
        origen, _normal, al_centro = juntas._elegir_plano_hermetico(planos_muro, (1.0, 0.0, 0.0), centro)
        self.assertAlmostEqual(origen[0], -8.0, delta=0.01)
        self.assertFalse(al_centro)
        planos_base = [((0.0, 0.0, 0.0), (0.0, 1.0, 0.0)), ((0.0, -8.0, 0.0), (0.0, 1.0, 0.0))]
        origen, _normal, al_centro = juntas._elegir_plano_hermetico(planos_base, (0.0, 1.0, 0.0), centro)
        self.assertAlmostEqual(origen[1], 0.0, delta=0.01)
        self.assertTrue(al_centro)

    def test_el_cordon_de_base_queda_en_la_esquina_externa(self):
        import weld_juntas as juntas

        muro = juntas.marco_cara((1, 0, 0), [(0, y, z) for y in (0, 2000) for z in (0, 1600)])
        base = juntas.marco_cara((0, -1, 0), [(x, 0, z) for x in (-40, 800) for z in (0, 1600)])
        cara_muro = ((-8.0, 0.0, 0.0), (-1.0, 0.0, 0.0), False)
        cara_base = ((0.0, 0.0, 0.0), (0.0, 1.0, 0.0), True)
        tramo = juntas._eje_de_planos(juntas._frame(muro), muro["outline"], cara_muro, juntas._frame(base), base["outline"], cara_base)
        self.assertIsNotNone(tramo)
        for punto in tramo:
            self.assertAlmostEqual(punto[0], -8.0, delta=0.1)
            self.assertAlmostEqual(punto[1], 0.0, delta=0.1)
        solidos = juntas._filete_en_aire("BASE", "hermetico", tramo[0], tramo[1], cara_muro, cara_base, (400.0, 1000.0, 800.0), 6)
        self.assertEqual(len(solidos), 1)
        patas = (solidos[0]["lado"], solidos[0]["normal"])
        self.assertTrue(any(pata[0] < -0.9 for pata in patas))
        self.assertTrue(any(pata[1] > 0.9 for pata in patas))

    def test_el_cordon_hermetico_usa_la_arista_mas_afuera(self):
        import weld_juntas as juntas

        inicio = (0.0, 0.0, 0.0)
        fin = (0.0, 2000.0, 0.0)
        centro = (0.0, 1000.0, 0.0)
        interna = ((8.0, 0.0, 0.0), (8.0, 2000.0, 0.0))
        externa = ((-12.0, 0.0, 6.0), (-12.0, 2000.0, 6.0))
        lejana = ((500.0, 0.0, 0.0), (500.0, 2000.0, 0.0))
        corta = ((-20.0, 0.0, 0.0), (-20.0, 30.0, 0.0))
        elegida = juntas._arista_mas_afuera([interna, externa, lejana, corta], inicio, fin, centro)
        self.assertIsNotNone(elegida)
        self.assertAlmostEqual(elegida[0][0], -12.0, delta=0.01)

    def test_el_cordon_va_en_la_raiz_y_no_en_el_canto(self):
        import weld_juntas as juntas

        centro = (-500.0, 1000.0, -500.0)

        def material(punto):
            x, _y, z = punto
            if -8.0 <= x <= 0.0 and -1000.0 <= z <= 6.0:
                return "a"
            if -1000.0 <= x <= -8.0 and -8.0 <= z <= 0.0:
                return "b"
            return None

        aristas = [
            ((0.0, 0.0, 6.0), (0.0, 2000.0, 6.0)),
            ((-8.0, 0.0, 6.0), (-8.0, 2000.0, 6.0)),
            ((-8.0, 0.0, 0.0), (-8.0, 2000.0, 0.0)),
            ((-8.0, 0.0, -8.0), (-8.0, 2000.0, -8.0)),
        ]
        raiz = juntas._raiz_por_cuadrantes(aristas, (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), centro, material)
        self.assertIsNotNone(raiz)
        (inicio, _fin), pata_1, pata_2 = raiz
        self.assertAlmostEqual(inicio[0], -8.0, delta=0.1)
        self.assertAlmostEqual(inicio[2], 0.0, delta=0.1)
        self.assertLess(pata_1[0], -0.9)
        self.assertGreater(pata_2[2], 0.9)

    def test_rincon_interior_no_se_publica(self):
        import weld_juntas as juntas

        def material(punto):
            x, _y, z = punto
            if -8.0 <= x <= 0.0 and -1000.0 <= z <= 6.0:
                return "a"
            if -1000.0 <= x <= -8.0 and -8.0 <= z <= 0.0:
                return "b"
            return None

        aristas = [((-8.0, 0.0, 0.0), (-8.0, 2000.0, 0.0))]
        cerrado = juntas._raiz_por_cuadrantes(aristas, (1, 0, 0), (0, 0, 1), (-500.0, 1000.0, -500.0), material, lambda _p, _r: False)
        self.assertIsNone(cerrado)

    def test_ceja_bajo_la_tapa_llena_la_boca(self):
        import weld_juntas as juntas

        def material(punto):
            x, y, _z = punto
            if -1000.0 <= x <= 2.0 and 0.0 <= y <= 8.0:
                return "b"
            if -8.0 <= x <= 0.0 and y <= -16.0:
                return "a"
            if (x + 16.0) ** 2 + (y + 16.0) ** 2 <= 256.0 and (x + 16.0) ** 2 + (y + 16.0) ** 2 >= 64.0 and x >= -16.0 and y >= -16.0:
                return "a"
            if -60.0 <= x <= -16.0 and -8.0 <= y <= 0.0:
                return "a"
            return None

        aristas = [((2.0, 0.0, 0.0), (2.0, 0.0, 2000.0)), ((2.0, 8.0, 0.0), (2.0, 8.0, 2000.0))]
        boca = juntas._boca_de_ranura(aristas, (1, 0, 0), (0, 1, 0), (-500.0, -800.0, 1000.0), material)
        self.assertIsNotNone(boca)
        (inicio, _fin), pata_1, pata_2 = boca
        self.assertAlmostEqual(inicio[1], 0.0, delta=0.1)
        self.assertLess(pata_1[0], -0.9)
        self.assertLess(pata_2[1], -0.9)

    def test_la_esquina_vertical_abre_las_dos_patas_hacia_afuera(self):
        import weld_juntas as juntas

        cara_a = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), False)
        cara_b = ((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), False)
        solidos = juntas._filete_en_aire("ESQUINA", "hermetico", (0.0, 0.0, 0.0), (0.0, 2000.0, 0.0), cara_a, cara_b, (400.0, 1000.0, 400.0), 6)
        self.assertEqual(len(solidos), 1)
        patas = (solidos[0]["lado"], solidos[0]["normal"])
        self.assertTrue(any(pata[0] < -0.9 for pata in patas))
        self.assertTrue(any(pata[2] < -0.9 for pata in patas))

    def test_la_pata_sigue_la_placa_y_no_el_cordon(self):
        import weld_juntas as juntas

        solidos = juntas._filetes_de_arista("OREJA", "accesorio", (0.0, 0.0, 0.0), (0.0, 400.0, 0.0), (0.0, 0.0, 1.0), (40.0, 20.0, 8.0), 6, False, 6)
        lado = solidos[0]["lado"]
        self.assertAlmostEqual(lado[1], 0.0, delta=0.05)
        self.assertLess(lado[0], -0.9)

    def test_no_rellena_el_hueco_entre_tramos(self):
        import weld_juntas as juntas

        separados = juntas._unir_colineales([((0.0, 0.0, 0.0), (20.0, 0.0, 0.0)), ((60.0, 0.0, 0.0), (80.0, 0.0, 0.0))], (0.0, 1.0, 0.0))
        self.assertEqual(len(separados), 2)
        juntos = juntas._unir_colineales([((0.0, 0.0, 0.0), (20.0, 0.0, 0.0)), ((21.0, 0.0, 0.0), (40.0, 0.0, 0.0))], (0.0, 1.0, 0.0))
        self.assertEqual(len(juntos), 1)
        self.assertAlmostEqual(juntas._largo_vector(juntas._resta(juntos[0][1], juntos[0][0])), 40.0, delta=0.1)

    def test_placa_girada_se_alinea_con_su_canto(self):
        import math

        import weld_juntas as juntas

        angulo = math.radians(18)

        def girar(x, z):
            return (x * math.cos(angulo) - z * math.sin(angulo), 0.0, x * math.sin(angulo) + z * math.cos(angulo))

        puntos = [girar(0, 0), girar(2000, 0), girar(2000, 800), girar(0, 800)]
        marco = juntas.marco_derecho((0, 1, 0), puntos)
        canto = juntas._norm(juntas._resta(puntos[1], puntos[0]))
        self.assertGreater(abs(juntas._dot(marco["u"], canto)), 0.98)

    def test_sesion_si_el_ensamble_esta_en_otra_carpeta(self):
        sesiones = {
            "c:/desktop/modelo vantran 251007.iam": {
                "assembly": "C:/Desktop/MODELO VANTRAN 251007.iam",
                "confirmed": True,
                "bags": {"SEGM1": []},
            }
        }
        hit = weld._sesion_muros(
            r"C:\Downloads\MODELO VANTRAN 251007.iam",
            sesiones,
            lambda ruta: ruta.replace("\\", "/").lower(),
        )
        self.assertIn("SEGM1", hit["bags"])

    def test_muestra_tres_juntas_toma_base_esquina_y_accesorio(self):
        juntas = [
            {"kind": "hermetico", "title": "SEGM1 / TOP"},
            {"kind": "hermetico", "title": "SEGM1 / BASE"},
            {"kind": "accesorio", "title": "SEGM4 / 27"},
            {"kind": "hermetico", "title": "SEGM1 / SEGM2"},
        ]
        muestra = weld._muestra_juntas(juntas, 3)
        self.assertEqual([item["title"] for item in muestra], ["SEGM1 / BASE", "SEGM1 / SEGM2", "SEGM4 / 27"])

    def test_scan_dibuja_en_python(self):
        hit = weld.scan_weld_drawing({"assemblyName": "MODELO VANTRAN 251007.iam", "job": "MODELO VANTRAN 251007"})
        self.assertTrue(hit["ok"])
        self.assertNotIn("dwg", hit["message"].lower())
        self.assertTrue(hit["folder"].endswith("Weld") or "job" in hit["message"].lower())

    def test_jpg_de_weld_entra_a_cotas_dossier(self):
        from cotas_dossier import evidencias_weld

        with tempfile.TemporaryDirectory() as tmp:
            carpeta = Path(tmp) / "TANKS" / "CLI" / "JOB" / "DOSSIER FILES" / "JPGS" / "Weld"
            carpeta.mkdir(parents=True)
            (carpeta / "SEGM1_BASE.jpg").write_bytes(b"x")
            (carpeta / "SEGM4").mkdir()
            (carpeta / "SEGM4" / "SEGM4_CAJA.jpg").write_bytes(b"x")
            (carpeta / "nota.txt").write_text("no", encoding="utf-8")
            filas = evidencias_weld(str(carpeta), job="JOB", cliente="CLI", producto="TANKS")
        self.assertEqual(len(filas), 2)
        fila = filas[0]
        self.assertEqual(fila["clasificacion"], "Weld")
        self.assertEqual(fila["seleccionadas"], "si")
        self.assertEqual(fila["type"], "TYP")
        self.assertEqual(fila["cantidad_spoteos"], 1)
        self.assertEqual(fila["nombre_archivo"], "SEGM1_BASE.jpg")
        self.assertEqual(fila["cliente"], "CLI")
        self.assertEqual(fila["producto"], "TANKS")
        self.assertEqual(fila["job"], "JOB")
        self.assertIn("JPGS\\Weld\\SEGM1_BASE.jpg", fila["ruta"].replace("/", "\\"))
        self.assertIn("JPGS\\Weld\\SEGM4\\SEGM4_CAJA.jpg", filas[1]["ruta"].replace("/", "\\"))

    def test_jpg_van_a_weld_del_dossier(self):
        destino = weld.carpeta_weld_de(
            {"producto": "TANKS", "cliente": "VANTRAN", "job": "06-30-2467TANK261079", "raiz": r"X:\ARGA"},
            "06-30-2467TANK261079",
        )
        self.assertIsNotNone(destino)
        self.assertEqual(destino.parts[-3:], ("DOSSIER FILES", "JPGS", "Weld"))
        self.assertIn("06-30-2467TANK261079", destino.parts)
        self.assertIsNone(weld.carpeta_weld_de({}, ""))

    def test_crea_jpgs_y_weld_si_no_existen(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "TANKS" / "PRUEBAS MODULO" / "TANK WELDS"
            job.mkdir(parents=True)
            eleccion = {
                "producto": "TANKS",
                "cliente": "PRUEBAS MODULO",
                "job": "TANK WELDS",
                "raiz": tmp,
            }
            with patch("dossier_arbol.cargar_eleccion", return_value=eleccion):
                destino = weld.carpeta_weld({"job": "TANK WELDS"}, create=True)
            self.assertTrue(destino.is_dir())
            self.assertEqual(destino.name, "Weld")
            self.assertTrue((job / "DOSSIER FILES" / "JPGS").is_dir())

    def test_la_cara_mira_con_v_hacia_arriba(self):
        import weld_vista

        junta = {
            "frame": {
                "normal": (-1.0, 0.0, 0.0),
                "u": (0.0, 0.0, 1.0),
                "v": (0.0, 1.0, 0.0),
                "origen": (100.0, 0.0, 0.0),
            },
            "outline": [(0.0, 0.0), (200.0, 0.0), (200.0, 400.0), (0.0, 400.0)],
        }
        encuadre = weld_vista._frente(junta, (0.0, 0.0, 0.0))
        self.assertGreater(encuadre["up"][1], 0.9)
        esquina = dict(junta, kind="hermetico", cara="SEGM4", id="SEGM4_SEGM1")
        del_lado = weld_vista._frente(esquina, (0.0, 0.0, 0.0))
        self.assertGreater(del_lado["look"][0], 0.9)
        con_base = dict(junta, kind="hermetico", cara="SEGM4", id="SEGM4_BASE")
        self.assertGreater(weld_vista._frente(con_base, (0.0, 0.0, 0.0))["look"][0], 0.9)
        self.assertFalse(encuadre["flip_x"])
        self.assertTrue(encuadre["u_a_la_izquierda"])
        self.assertAlmostEqual(encuadre["w"], 20.0 * weld_jpg.MARGEN_FOTO, delta=0.01)
        self.assertAlmostEqual(encuadre["h"], 40.0 * weld_jpg.MARGEN_FOTO, delta=0.01)

    def test_la_esquina_vertical_se_mira_por_fuera_del_filete(self):
        import weld_vista

        junta = {
            "kind": "hermetico",
            "cara": "SEGM2",
            "id": "SEGM2_SEGM1",
            "centro_tanque": (0.0, 0.0, 0.0),
            "weld": {"footprint": (0.0, 0.0, 200.0, 400.0), "leg": 6},
            "frame": {
                "normal": (-1.0, 0.0, 0.0),
                "u": (0.0, 0.0, 1.0),
                "v": (0.0, 1.0, 0.0),
                "origen": (100.0, 0.0, 0.0),
            },
            "outline": [(0.0, 0.0), (200.0, 0.0), (200.0, 400.0), (0.0, 400.0)],
            "frame_otro": {
                "normal": (0.0, 0.0, -1.0),
                "u": (1.0, 0.0, 0.0),
                "v": (0.0, 1.0, 0.0),
                "origen": (0.0, 0.0, 100.0),
            },
            "outline_otro": [(0.0, 0.0), (200.0, 0.0), (200.0, 400.0), (0.0, 400.0)],
        }
        detalle = weld_vista._iso(junta, (0.0, 0.0, 0.0), cerrado=True)
        self.assertGreater(detalle["look"][0], 0.55)
        self.assertGreater(detalle["look"][2], 0.55)
        self.assertLess(abs(detalle["look"][0] - detalle["look"][2]), 0.15)
        self.assertGreater(detalle["look"][1], 0.2)
        self.assertAlmostEqual(detalle["w"], 42.0, delta=0.01)
        ancho = weld_vista._iso(junta, (0.0, 0.0, 0.0), cerrado=False)
        self.assertAlmostEqual(ancho["look"][0], detalle["look"][0], delta=0.01)
        self.assertAlmostEqual(ancho["w"], 78.0, delta=0.01)
        frente = weld_vista._frente(junta, (0.0, 0.0, 0.0))
        self.assertGreater(frente["look"][0], 0.9)
        pieza_de_la_otra_placa = {
            "normal": (0.0, 0.0, 1.0),
            "lado": (1.0, 0.0, 0.0),
            "esquina": (100.0, 0.0, 100.0),
            "direccion": (0.0, 1.0, 0.0),
            "largo": 400.0,
        }
        original = weld_vista._primer_filete
        weld_vista._primer_filete = lambda _junta: pieza_de_la_otra_placa
        try:
            de_frente = weld_vista._frente(junta, (0.0, 0.0, 0.0))
            self.assertGreater(de_frente["look"][0], 0.9)
            self.assertLess(abs(de_frente["look"][2]), 0.2)
            detalle_bien = weld_vista._iso(junta, (0.0, 0.0, 0.0), cerrado=True)
        finally:
            weld_vista._primer_filete = original
        self.assertGreater(detalle_bien["look"][0], 0.55)
        self.assertGreater(detalle_bien["look"][2], 0.55)
        self.assertFalse(detalle["flip_x"])
        self.assertFalse(ancho["flip_x"])
        self.assertEqual(detalle["u_a_la_izquierda"], frente["u_a_la_izquierda"])
        self.assertEqual(ancho["u_a_la_izquierda"], frente["u_a_la_izquierda"])
        del_lado_azul = {
            "normal": (1.0, 0.0, 0.0),
            "lado": (0.0, 0.0, 1.0),
            "esquina": (100.0, 0.0, 100.0),
            "direccion": (0.0, 1.0, 0.0),
            "largo": 400.0,
        }
        del_contrario = dict(del_lado_azul, lado=(0.0, 0.0, -1.0))
        weld_vista._primer_filete = lambda _junta: del_lado_azul
        try:
            hacia = weld_vista._iso(junta, (0.0, 0.0, 0.0), cerrado=True)
        finally:
            weld_vista._primer_filete = original
        self.assertGreater(hacia["look"][2], 0.3)
        self.assertGreater(hacia["look"][0], 0.55)
        weld_vista._primer_filete = lambda _junta: del_contrario
        try:
            regreso = weld_vista._iso(junta, (0.0, 0.0, 0.0), cerrado=True)
        finally:
            weld_vista._primer_filete = original
        self.assertLess(regreso["look"][2], -0.3)
        self.assertGreater(regreso["look"][0], 0.55)

    def test_la_foto_del_segmento_lleva_todos_sus_accesorios(self):
        import weld_anotation as weld

        placa, pad, oreja, otro, ajeno = object(), object(), object(), object(), object()
        accesorios = [
            {"cara": "SEGM1", "occ": pad},
            {"cara": "SEGM1", "occ": oreja},
            {"cara": "SEGM2", "occ": ajeno},
        ]
        naranja = weld._visibles_de(
            {"kind": "accesorio", "cara": "SEGM1", "host": placa, "pieza": pad},
            accesorios,
        )
        self.assertEqual(naranja, [placa, pad, oreja])
        azul = weld._visibles_de(
            {"kind": "hermetico", "cara": "SEGM1", "host": placa, "otro": otro, "pieza": None},
            accesorios,
        )
        self.assertEqual(azul, [placa, otro, pad, oreja])

    def test_el_accesorio_interior_se_mira_desde_la_pieza(self):
        import weld_vista

        junta = {
            "kind": "accesorio",
            "centro": (80.0, 200.0, 100.0),
            "frame": {
                "normal": (1.0, 0.0, 0.0),
                "u": (0.0, 0.0, 1.0),
                "v": (0.0, 1.0, 0.0),
                "origen": (100.0, 0.0, 0.0),
            },
            "outline": [(0.0, 0.0), (1600.0, 0.0), (1600.0, 2000.0), (0.0, 2000.0)],
        }
        encuadre = weld_vista._frente(junta, (0.0, 500.0, 800.0))
        self.assertLess(encuadre["look"][0], -0.9)
        self.assertAlmostEqual(encuadre["w"], 160.0 * weld_jpg.MARGEN_FOTO, delta=0.01)
        self.assertAlmostEqual(encuadre["h"], 200.0 * weld_jpg.MARGEN_FOTO, delta=0.01)
        detalle = weld_vista._iso(junta, (0.0, 500.0, 800.0), cerrado=True)
        self.assertLess(detalle["look"][0], 0.0)

    def test_la_ventana_ancha_conserva_el_alto_de_la_placa(self):
        import weld_vista

        ancho, alto, escala_u, escala_v = weld_vista._ajustar_aspecto(100.0, 200.0, 1.8)
        self.assertAlmostEqual(alto, 200.0)
        self.assertGreater(ancho, 100.0)
        self.assertAlmostEqual(escala_v, 1.0)
        self.assertGreater(escala_u, 1.0)
        ventana = weld_vista._ventana_uv((50.0, 100.0, 100.0, 200.0), escala_u, escala_v)
        self.assertAlmostEqual(ventana[3] - ventana[1], 200.0)
        self.assertGreater(ventana[2] - ventana[0], 100.0)

    def test_el_circulo_cae_en_la_placa_y_no_en_el_margen(self):
        outline = [(0.0, 0.0), (200.0, 0.0), (200.0, 400.0), (0.0, 400.0)]
        frente = (0, 0, 216, 432)
        centro = weld_jpg._en_frente((100.0, 200.0), outline, frente)
        canto = weld_jpg._en_frente((100.0, 400.0), outline, frente)
        self.assertAlmostEqual(centro[0], 108.0, delta=0.5)
        self.assertAlmostEqual(centro[1], 216.0, delta=0.5)
        self.assertAlmostEqual(canto[1], 16.0, delta=0.5)
        self.assertGreater(canto[1], 4.0)
        espejo = weld_jpg._en_frente((200.0, 200.0), outline, frente, (216.0, 0.0, 0.0, 432.0))
        self.assertLess(espejo[0], 20.0)

    def test_el_canto_de_la_tapa_queda_arriba_y_el_de_la_base_abajo(self):
        import weld_juntas as juntas

        segmento = [(0, y, z) for y in (0, 2000) for z in (0, 1600)]
        muros = {
            "SEGM1": juntas.marco_cara((1, 0, 0), segmento),
            "BASE": juntas.marco_cara((0, -1, 0), [(x, 0, z) for x in (0, 800) for z in (0, 1600)]),
            "TOP": juntas.marco_cara((0, 1, 0), [(x, 2000, z) for x in (0, 800) for z in (0, 1600)]),
        }
        halladas = {item["id"]: item for item in juntas.armar_juntas(muros, [])}
        ys = [punto[1] for punto in halladas["SEGM1_TOP"]["outline"]]
        tapa = halladas["SEGM1_TOP"]["weld"]["footprint"]
        base = halladas["SEGM1_BASE"]["weld"]["footprint"]
        self.assertGreater((tapa[1] + tapa[3]) / 2.0, (min(ys) + max(ys)) / 2.0)
        self.assertLess((base[1] + base[3]) / 2.0, (min(ys) + max(ys)) / 2.0)

    def test_el_bastidor_se_queda_en_la_base_y_la_oreja_en_su_segmento(self):
        import weld_juntas as juntas

        muros = {
            "SEGM1": juntas.marco_cara((1, 0, 0), [(0, y, z) for y in (0, 2000) for z in (0, 1600)]),
            "BASE": juntas.marco_cara((0, -1, 0), [(x, 0, z) for x in (0, 800) for z in (0, 1600)]),
        }
        bastidor = {
            "cara": "BASE",
            "nombre": "Tank-Base",
            "centro": (20.0, 300.0, 800.0),
            "caja": ((0.0, 0.0, 200.0), (40.0, 700.0, 1400.0)),
            "puntos": juntas._esquinas(((0.0, 0.0, 200.0), (40.0, 700.0, 1400.0))),
        }
        lejos = {
            "cara": "SEGM1",
            "nombre": "Oreja",
            "centro": (20.0, 1500.0, 450.0),
            "caja": ((0.0, 1400.0, 400.0), (40.0, 1600.0, 500.0)),
            "puntos": juntas._esquinas(((0.0, 1400.0, 400.0), (40.0, 1600.0, 500.0))),
        }
        halladas = {item["id"]: item for item in juntas.armar_juntas(muros, [bastidor, lejos])}
        self.assertIn("BASE_Tank-Base", halladas)
        self.assertNotIn("SEGM1_Tank-Base", halladas)
        self.assertIn("SEGM1_Oreja", halladas)
        self.assertNotIn("BASE_Oreja", halladas)

    def test_la_tanda_cercana_entra_y_la_de_atras_no(self):
        import weld_juntas as juntas

        pegada = ((0.0, 0.0, 0.0), (400.0, 0.0, 0.0))
        atras = ((0.0, 0.0, 6.0), (400.0, 0.0, 6.0))
        solo = juntas._banda_de_contacto([pegada, atras], (0.0, 0.0, 0.0), (0.0, 0.0, 1.0))
        self.assertEqual(solo, [pegada])
        separada = ((0.0, 0.0, 7.0), (500.0, 0.0, 7.0))
        self.assertEqual(
            juntas._banda_de_contacto([separada], (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
            [separada],
        )
        self.assertEqual(
            juntas._banda_de_contacto([((0.0, 0.0, 20.0), (100.0, 0.0, 20.0))], (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
            [],
        )

    def test_una_barra_ya_en_el_ensamble_no_se_parte(self):
        import weld_juntas as juntas

        minimo = (0.0, -80.0, -30.0)
        maximo = (205.0, -30.0, 60.0)
        matriz = [
            [1.0, 0.0, 0.0, -65.0],
            [0.0, 1.0, 0.0, -53.0],
            [0.0, 0.0, 1.0, -32.0],
        ]
        cerca = (20.0, -55.0, 15.0)
        lejos = (200.0, -32.0, 55.0)
        self.assertFalse(juntas._conviene_matriz([cerca, lejos], minimo, maximo, matriz))
        inicio = juntas._mm_ensamble(cerca, None, matriz, False)
        fin = juntas._mm_ensamble(lejos, None, matriz, False)
        self.assertAlmostEqual(
            juntas._largo_vector(juntas._resta(fin, inicio)),
            10.0 * juntas._largo_vector(juntas._resta(lejos, cerca)),
            places=3,
        )

    def test_la_matriz_entra_si_la_pieza_no_esta_en_su_caja(self):
        import weld_juntas as juntas

        minimo = (100.0, 100.0, 100.0)
        maximo = (140.0, 110.0, 160.0)
        matriz = [
            [1.0, 0.0, 0.0, 120.0],
            [0.0, 1.0, 0.0, 105.0],
            [0.0, 0.0, 1.0, 130.0],
        ]
        puntos = [(0.0, 0.0, 0.0), (30.0, 5.0, 20.0)]
        self.assertTrue(juntas._conviene_matriz(puntos, minimo, maximo, matriz))

    def test_la_placa_fuera_de_su_caja_pasa_al_ensamble(self):
        import referencia_snapshot
        import weld_anotation

        class Punto:
            def __init__(self, x, y, z):
                self.X, self.Y, self.Z = x, y, z

        class Occ:
            class RangeBox:
                MinPoint = Punto(100.0, 100.0, 100.0)
                MaxPoint = Punto(140.0, 110.0, 160.0)

        matriz = [
            [1.0, 0.0, 0.0, 120.0],
            [0.0, 1.0, 0.0, 105.0],
            [0.0, 0.0, 1.0, 130.0],
        ]
        original = referencia_snapshot._matriz
        referencia_snapshot._matriz = lambda _occ: matriz
        try:
            puntos, normal = weld_anotation._ubicar(Occ(), [(0.0, 0.0, 0.0), (30.0, 5.0, 20.0)], (0.0, 0.0, 1.0))
        finally:
            referencia_snapshot._matriz = original
        self.assertEqual(puntos[0], (120.0, 105.0, 130.0))
        self.assertEqual(normal, (0.0, 0.0, 1.0))

    def test_la_placa_que_ya_esta_en_el_ensamble_no_se_mueve(self):
        import referencia_snapshot
        import weld_anotation

        class Punto:
            def __init__(self, x, y, z):
                self.X, self.Y, self.Z = x, y, z

        class Occ:
            class RangeBox:
                MinPoint = Punto(0.0, -80.0, -30.0)
                MaxPoint = Punto(205.0, -30.0, 60.0)

        matriz = [
            [1.0, 0.0, 0.0, -65.0],
            [0.0, 1.0, 0.0, -53.0],
            [0.0, 0.0, 1.0, -32.0],
        ]
        original = referencia_snapshot._matriz
        referencia_snapshot._matriz = lambda _occ: matriz
        crudos = [(20.0, -55.0, 15.0), (200.0, -32.0, 55.0)]
        try:
            puntos, _normal = weld_anotation._ubicar(Occ(), crudos, (0.0, 1.0, 0.0))
        finally:
            referencia_snapshot._matriz = original
        self.assertEqual(puntos, crudos)

    def test_el_trazo_hermetico_sigue_el_canto_alto(self):
        imagen = Image.new("RGB", (216, 432), (255, 255, 255))
        weld_jpg._cota_en_cara(
            ImageDraw.Draw(imagen),
            [(0.0, 0.0), (200.0, 0.0), (200.0, 400.0), (0.0, 400.0)],
            {"footprint": (0.0, 400.0, 200.0, 400.0), "length": "200 mm", "tone": "hermetico"},
            (0, 0, 216, 432),
        )
        self.assertEqual(imagen.getpixel((40, 16)), weld_jpg._AZUL)
        self.assertEqual(imagen.getpixel((40, 416)), (255, 255, 255))
        medio = weld_jpg._medio_del_canto([(0.0, 0.0), (200.0, 0.0), (200.0, 400.0), (0.0, 400.0)])
        self.assertAlmostEqual(medio[0], 200.0, delta=0.1)
        self.assertAlmostEqual(medio[1], 200.0, delta=0.1)

    def test_el_cielo_azulado_sale_blanco_y_el_naranja_se_queda(self):
        cielo = Image.new("RGB", (8, 8), (214, 224, 236))
        limpio = weld_jpg._limpiar(cielo, suave=True)
        self.assertEqual(limpio.getpixel((1, 1)), (255, 255, 255))
        placa = Image.new("RGB", (8, 8), (188, 188, 188))
        placa.putpixel((3, 3), (230, 110, 15))
        salida = weld_jpg._limpiar(placa, suave=True)
        self.assertEqual(salida.getpixel((0, 0)), (188, 188, 188))
        self.assertEqual(salida.getpixel((3, 3)), (230, 110, 15))
        filete = Image.new("RGB", (8, 8), (15, 75, 190))
        self.assertEqual(weld_jpg._limpiar(filete, suave=True).getpixel((1, 1)), (15, 75, 190))

    def test_placa_inclinada_queda_horizontal(self):
        imagen = Image.new("RGB", (360, 220), (255, 255, 255))
        for x in range(40, 320):
            for y in range(70, 150):
                imagen.putpixel((x, y), (160, 158, 156))
        inclinada = imagen.rotate(-30, expand=True, fillcolor=(255, 255, 255))
        recta = weld_jpg._enderezar(inclinada, True)
        angulo = weld_jpg._eje_placa(recta)
        self.assertIsNotNone(angulo)
        self.assertLess(abs(angulo), 2.0)

    def test_jpg_de_un_cordon(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "BASE_SEGMENT1.jpg"
            weld_jpg.save_weld_jpg(
                dest,
                title="Segment 1 / BASE_SEGMENT1",
                outline=[(0, 0), (1624, 0), (1624, 811), (0, 811)],
                welds=[
                    {
                        "mark": ".A2",
                        "length": "1612 mm",
                        "leg": "6",
                        "pitch": "100-300",
                        "typ": True,
                        "sides": 2,
                        "anchor": (0.5, 0.02),
                    }
                ],
            )
            self.assertTrue(dest.is_file())
            self.assertGreater(dest.stat().st_size, 8000)
            with Image.open(dest) as image:
                self.assertEqual(image.size, (1760, 980))
                esquina = image.getpixel((1, 1))
                self.assertGreater(min(esquina), 248)

    def test_awis_real_tank_assembly(self):
        root = Path.home() / "Documents" / "AWIS"
        if not (root / "AWIS_FACE_DRAWING_Tank_Assembly.dwg").is_file():
            self.skipTest("sin plano AWIS local")
        found = weld.resolve_drawing_path(root, "Tank Assembly", "face")
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "AWIS_FACE_DRAWING_Tank_Assembly.dwg")
        dims = weld.resolve_drawing_path(root, "Tank Assembly", "dims")
        self.assertIsNotNone(dims)
        self.assertEqual(dims.name, "AWIS_WELD_DIMS_Tank_Assembly.dwg")


class _Cuerpo:
    def __init__(self, visible: bool):
        self.Visible = visible


class _Cuerpos:
    def __init__(self, items: list[_Cuerpo]):
        self._items = items
        self.Count = len(items)

    def Item(self, index: int) -> _Cuerpo:
        return self._items[index - 1]


class _Occ:
    def __init__(self, cuerpos: list[_Cuerpo]):
        self.Visible = False
        self.SurfaceBodies = _Cuerpos(cuerpos)


class WeldSolidoTests(unittest.TestCase):
    def test_al_cerrar_la_foto_vuelven_todos_los_filetes(self):
        import weld_solido

        naranja = [_Cuerpo(False), _Cuerpo(True)]
        azul = [_Cuerpo(False)]
        cordon = weld_solido.Cordones.__new__(weld_solido.Cordones)
        cordon._cuerpos = {"a": naranja[0], "b": naranja[1], "c": azul[0]}
        cordon._grupos = [
            {"occ": _Occ(naranja)},
            {"occ": _Occ(azul)},
        ]
        cordon.mostrar_todos()
        self.assertTrue(all(cuerpo.Visible for cuerpo in naranja + azul))
        self.assertTrue(all(grupo["occ"].Visible for grupo in cordon._grupos))

    def test_la_hoja_nueva_enciende_el_filete_con_el_nombre_viejo(self):
        import weld_solido

        class Cuerpo:
            def __init__(self, nombre: str):
                self.Name = nombre
                self.Visible = False

        viejo = Cuerpo("SEGM1_SEGM4")
        vecino = Cuerpo("SEGM2_SEGM3")
        accesorio = Cuerpo("SEGM4_Jacking_pad_24")
        cordon = weld_solido.Cordones.__new__(weld_solido.Cordones)
        cordon._cuerpos = {
            viejo.Name: viejo,
            vecino.Name: vecino,
            accesorio.Name: accesorio,
        }
        cordon.por_junta = {cuerpo.Name: [cuerpo.Name] for cuerpo in (viejo, vecino, accesorio)}
        cordon._grupos = [{"occ": _Occ([viejo, vecino, accesorio])}]
        cordon.mostrar("SEGM4_SEGM1")
        self.assertTrue(viejo.Visible)
        self.assertFalse(vecino.Visible)
        self.assertFalse(accesorio.Visible)
        cordon.mostrar("SEGM4_Jacking_pad_24")
        self.assertTrue(accesorio.Visible)
        self.assertFalse(viejo.Visible)


class WeldNomenclaturaTests(unittest.TestCase):
    def test_el_preset_de_taller_se_lee_igual_que_el_simbolo(self):
        import weld_nomenclatura as nom

        spec = nom.leer_texto("FILLET 6/8 mm 100-300")
        self.assertAlmostEqual(spec["flecha"], 6.0)
        self.assertAlmostEqual(spec["otro"], 8.0)
        self.assertTrue(spec["dos_lados"])
        self.assertEqual(spec["paso"], "100-300")
        self.assertEqual(nom.formato(spec), "FILLET 6/8 mm 100-300")
        self.assertEqual(
            nom.formato(spec, "in"),
            "FILLET 1/4/5/16 in 3.94-11.81",
        )
        hoja_in = nom.presentar_weld({"length": "1753 mm", "leg": "6", "pitch": "", "sides": 1, "typ": True}, "in")
        self.assertEqual(hoja_in["length"], "69.02 in")
        self.assertEqual(hoja_in["leg"], "1/4")
        self.assertEqual(nom.formato(nom.leer_texto("FILLET 3 mm 2SIDES TYP")), "FILLET 3 mm 2SIDES TYP")
        hoja = nom.weld_publicado({"length": "1200 mm", "leg": "6"}, spec)
        self.assertEqual(hoja["leg"], "6")
        self.assertEqual(hoja["other"], "8")
        self.assertEqual(hoja["sides"], 2)
        self.assertEqual(hoja["pitch"], "100-300")

    def test_la_tabla_conserva_lo_editado_y_sigue_el_iam_por_nombre(self):
        import weld_nomenclatura as nom

        with tempfile.TemporaryDirectory() as tmp:
            original = nom.ARCHIVO
            nom.ARCHIVO = Path(tmp) / "weld_nomenclatura.json"
            try:
                juntas = [
                    {"id": "SEGM1_BASE", "title": "SEGM1 / BASE", "kind": "hermetico", "weld": {"leg": "6", "other": "8", "pitch": "100-300", "sides": 2, "typ": True, "length": "2300 mm"}},
                    {"id": "PAD_1", "title": "SEGM1 / PAD", "kind": "accesorio", "weld": {"leg": "6", "sides": 1, "typ": True, "length": "80 mm"}},
                ]
                nom.guardar_manifiesto("C:/jobs/tanque.iam", juntas, {"SEGM1_BASE": ["SEGM1_BASE"], "PAD_1": ["PAD_1"]})
                tabla, cambio = nom.aplicar("C:/otra/tanque.iam", "SEGM1_BASE", "accesorio", {"flecha": 5, "otro": 5, "dos_lados": True, "typ": False, "paso": ""})
                self.assertTrue(tabla["ok"])
                self.assertIsNotNone(cambio)
                self.assertEqual(cambio["clasificacion"], "accesorio")
                self.assertEqual(cambio["texto"], "FILLET 5 mm 2SIDES")
                nom.guardar_manifiesto("C:/otra/tanque.iam", juntas, {"SEGM1_BASE": ["SEGM1_BASE"], "PAD_1": ["PAD_1"]})
                filas = {item["id"]: item for item in nom.listar("C:/jobs/tanque.iam")["cordones"]}
                self.assertTrue(filas["SEGM1_BASE"]["editado"])
                self.assertEqual(filas["SEGM1_BASE"]["clasificacion"], "accesorio")
                self.assertEqual(filas["SEGM1_BASE"]["texto"], "FILLET 3/16 in 2SIDES")
                self.assertEqual(nom.clasificaciones("C:/otra/tanque.iam"), {"SEGM1_BASE": "accesorio"})
            finally:
                nom.ARCHIVO = original

    def test_el_tanque_dentro_de_giga_se_escribe_en_pulgadas(self):
        from acotacion import classify_assembly

        tanque = classify_assembly(
            "261080_TANK.iam",
            r"\\server\TANKS\GIGA\GIGABOARD5\261080_TANK\261080_TANK.iam",
        )
        self.assertEqual(tanque["tipo"], "TANQUE")
        self.assertEqual(tanque["unit"], "in")
        gabinete = classify_assembly("9919 BOARD.iam", r"\\server\ENCLOSURES\9919 BOARD.iam")
        self.assertEqual(gabinete["unit"], "mm")

    def test_el_verde_de_seleccion_no_se_queda_en_la_vineta(self):
        from PIL import Image

        from weld_jpg import _quitar_verde

        imagen = Image.new("RGB", (2, 1))
        imagen.putpixel((0, 0), (120, 190, 110))
        imagen.putpixel((1, 0), (230, 110, 15))
        salida = _quitar_verde(imagen)
        self.assertEqual(salida.getpixel((0, 0)), (140, 140, 140))
        self.assertEqual(salida.getpixel((1, 0)), (230, 110, 15))

    def test_un_cuerpo_elige_su_cordon_y_no_el_grupo_del_mismo_color(self):
        import weld_nomenclatura as nom

        filas = [
            {"id": "SEGM2_TOP", "titulo": "SEGM2 / TOP", "clasificacion": "hermetico", "cuerpos": ["SEGM2_TOP_A"]},
            {"id": "SEGM4_TOP", "titulo": "SEGM4 / TOP", "clasificacion": "hermetico", "cuerpos": ["SEGM4_TOP_A"]},
        ]
        fila = nom._fila_de_cuerpo(filas, "SEGM4_TOP_A")
        self.assertEqual(fila["id"], "SEGM4_TOP")
        self.assertEqual(fila["cuerpos"], ["SEGM4_TOP_A"])
        self.assertEqual(nom.nombres_de_cordon(["SEGM4_TOP"], ["SEGM2_TOP", "SEGM4_TOP", "SEGM4_TOP_B"]), ["SEGM4_TOP", "SEGM4_TOP_B"])

    def test_quitar_un_cordon_no_lo_vuelve_a_proponer(self):
        import weld_nomenclatura as nom

        with tempfile.TemporaryDirectory() as tmp:
            original = nom.ARCHIVO
            aprendizaje = nom.APRENDIZAJE
            nom.ARCHIVO = Path(tmp) / "weld_nomenclatura.json"
            nom.APRENDIZAJE = Path(tmp) / "weld_aprendizaje.json"
            try:
                juntas = [
                    {"id": "SEGM2_TOP", "title": "SEGM2 / TOP", "kind": "hermetico", "weld": {"leg": "6", "sides": 2, "length": "800 mm"}},
                    {"id": "SEGM1_JACKPAD", "title": "SEGM1 / JACK PAD", "kind": "accesorio", "weld": {"leg": "6", "sides": 1, "length": "40 mm"}},
                ]
                nom.guardar_manifiesto("C:/jobs/tanque.iam", juntas, {"SEGM2_TOP": ["SEGM2_TOP"], "SEGM1_JACKPAD": ["SEGM1_JACKPAD"]})
                quitado = nom.excluir("C:/jobs/tanque.iam", "SEGM1_JACKPAD")
                self.assertTrue(quitado["ok"])
                self.assertEqual([item["id"] for item in quitado["cordones"]], ["SEGM2_TOP"])
                otra = {"id": "TOP_JACKPAD", "title": "TOP / JACK PAD:2", "kind": "accesorio"}
                self.assertTrue(nom.junta_vetada(otra))
                self.assertFalse(nom.junta_vetada(juntas[0]))
                nom.guardar_manifiesto("C:/jobs/tanque.iam", juntas, {"SEGM2_TOP": ["SEGM2_TOP"], "SEGM1_JACKPAD": ["SEGM1_JACKPAD"]})
                self.assertEqual([item["id"] for item in nom.listar("C:/jobs/tanque.iam")["cordones"]], ["SEGM2_TOP"])
            finally:
                nom.ARCHIVO = original
                nom.APRENDIZAJE = aprendizaje


if __name__ == "__main__":
    unittest.main()
