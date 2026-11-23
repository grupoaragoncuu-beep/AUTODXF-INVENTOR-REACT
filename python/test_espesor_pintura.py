"""Mallas de espesor de pintura y la prueba local, sin base de datos."""

import json
import tempfile
import unittest
from pathlib import Path

from espesor_geo import OPUESTO, agrupar_muros, clase_oculta, entra_en_alzado, lado_vista, plan_cara, tamano_bitmap
from espesor_run import generar


class Malla(unittest.TestCase):
    def test_thermox_es_rejilla_de_nueve(self):
        puntos, avisos = plan_cara("thermox", "muro", 100, 90)
        self.assertEqual(len(puntos), 9)
        self.assertEqual(avisos, [])
        self.assertEqual({p["banda"] for p in puntos}, {"superior", "media", "inferior"})
        self.assertEqual({p["columna"] for p in puntos}, {"izquierda", "medio", "derecha"})
        self.assertTrue(all(p["color"] == "rojo" for p in puntos))

    def test_thermox_mira_adentro_y_zinc_mira_afuera(self):
        internos, _ = plan_cara("thermox", "muro", 100, 90)
        externos, _ = plan_cara("zinc_macro", "muro", 100, 90)
        self.assertEqual(OPUESTO["SEGM1"], "SEGM3")
        self.assertEqual(OPUESTO["SEGM3"], "SEGM1")
        self.assertEqual(OPUESTO["TOP"], "BASE")
        self.assertEqual(lado_vista("thermox"), "dentro")
        self.assertEqual(lado_vista("poliuretano"), "fuera")
        poliuretano, _ = plan_cara("poliuretano", "muro", 100, 90)
        self.assertTrue(all(p["grupo"] == "externa" for p in poliuretano if p["color"] == "rojo"))
        self.assertEqual(lado_vista("zinc_macro"), "fuera")
        self.assertTrue(all(p["grupo"] == "interna" for p in internos))
        self.assertTrue(all(p["grupo"] == "externa" for p in externos))
        plano = 100.0
        self.assertTrue(entra_en_alzado(plano - 1.0, plano, plano, "dentro"))
        self.assertFalse(entra_en_alzado(plano, plano + 20.0, plano, "dentro"))
        self.assertTrue(entra_en_alzado(plano, plano + 20.0, plano, "fuera"))
        self.assertFalse(entra_en_alzado(plano + 5.0, plano + 40.0, plano, "dentro"))
        self.assertFalse(entra_en_alzado(plano - 220.0, plano - 180.0, plano, "dentro", hasta=plano - 70.0))
        self.assertTrue(entra_en_alzado(plano - 2.0, plano, plano, "dentro", hasta=plano - 70.0))
        self.assertTrue(entra_en_alzado(plano - 170.0, plano - 150.0, plano, "dentro", hasta=plano - 177.0))

    def test_la_media_seccion_corta_a_la_mitad_y_deja_fuera_lo_de_afuera(self):
        from espesor_geo import claro_de, contenida, interior_de

        def cara(codigo, normal, plano, u, v, u0, ancho, v0, alto):
            return {"codigo": codigo, "normal": normal, "plano": plano, "u": u, "v": v,
                    "u0": u0, "ancho": ancho, "v0": v0, "alto": alto}

        x, y, z = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)
        mx, my, mz = (-1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, -1.0)
        caras = [
            cara("SEGM1", z, 95.0, x, y, -150.0, 300.0, 0.0, 327.0),
            cara("SEGM3", mz, 95.0, mx, y, -150.0, 300.0, 0.0, 327.0),
            cara("SEGM2", mx, 177.0, z, y, -94.0, 188.0, 0.0, 329.0),
            cara("SEGM4", x, 177.0, mz, y, -94.0, 188.0, 0.0, 329.0),
            cara("TOP", y, 329.0, mx, z, -175.0, 350.0, -99.0, 198.0),
            cara("BASE", my, 0.5, mx, mz, -175.0, 350.0, -99.0, 198.0),
        ]
        segm1 = caras[0]
        self.assertAlmostEqual(claro_de(caras[2], caras), 354.0)
        self.assertAlmostEqual(claro_de(segm1, caras), 190.0)
        a, b, c, d = interior_de(segm1, caras)
        self.assertEqual((a, b), (-177.0, 177.0))
        self.assertEqual((c, d), (-0.5, 329.0))
        self.assertTrue(contenida([-170.0, 170.0], [0.0, 328.0], (a, b, c, d)))
        self.assertFalse(contenida([170.0, 230.0], [100.0, 120.0], (a, b, c, d)))
        self.assertFalse(contenida([-10.0, 10.0], [330.0, 360.0], (a, b, c, d)))

    def test_el_extremo_es_la_placa_y_no_la_valvula_de_afuera(self):
        from espesor_run import _zona_extremo

        piezas = [
            {"nombre_ocurrencia": "TAPA_EXTREMO", "caja": ((145.0, 0.0, -94.0), (177.0, 329.0, 94.0))},
            {"nombre_ocurrencia": "MURO_LARGO", "caja": ((-150.0, 0.0, 94.0), (150.0, 327.0, 95.0))},
            {"nombre_ocurrencia": "VALVULA", "caja": ((200.0, 100.0, -10.0), (219.0, 130.0, 10.0))},
            {"nombre_ocurrencia": "OREJA", "caja": ((150.0, 150.0, 95.0), (200.0, 190.0, 113.0))},
        ]
        zona = _zona_extremo(piezas, (1.0, 0.0, 0.0))
        self.assertIsNotNone(zona)
        self.assertAlmostEqual(zona["plano"], 177.0)
        self.assertAlmostEqual(zona["ancho"], 188.0)
        self.assertAlmostEqual(zona["alto"], 329.0)

    def test_desde_dentro_la_izquierda_de_la_foto_es_el_punto_izquierdo(self):
        from PIL import Image

        from espesor_jpg import asentar_puntos
        from espesor_run import _recortar_dentro

        import numpy as np

        imagen = Image.new("RGB", (400, 200), "white")
        solido = np.zeros((200, 400), dtype=bool)
        foto, ventana, recorte = _recortar_dentro(imagen, solido, (0.0, 100.0, 0.0, 100.0), 50.0, 50.0, 200.0, 100.0)
        self.assertEqual(foto.size, (200, 200))
        self.assertEqual(recorte.shape, (200, 200))
        izquierda, abajo, derecha, arriba = ventana
        origen_u = -(0.0 + 100.0)
        x_px = (10.0 + origen_u - izquierda) / (derecha - izquierda) * foto.width
        self.assertAlmostEqual(x_px, 20.0)

        angosto = np.zeros((300, 300), dtype=bool)
        angosto[:, :130] = True
        angosto[:, 170:] = True
        puntos = [{"x": 150.0, "y": 150.0}]
        asentar_puntos(puntos, angosto, (0.0, 0.0, 300.0, 300.0), 0.0, 0.0, cara=(300.0, 300.0))
        self.assertTrue(puntos[0]["x"] < 130.0 or puntos[0]["x"] > 170.0)
        ancho = np.zeros((300, 300), dtype=bool)
        ancho[:, :60] = True
        ancho[:, 240:] = True
        lejos = [{"x": 150.0, "y": 150.0}]
        asentar_puntos(lejos, ancho, (0.0, 0.0, 300.0, 300.0), 0.0, 0.0, cara=(300.0, 300.0))
        self.assertEqual(lejos[0]["x"], 150.0)

    def test_el_relleno_gris_no_tapa_la_arista(self):
        from PIL import Image

        from espesor_jpg import trazo_fino

        imagen = Image.new("RGB", (30, 20), "white")
        pixel = imagen.load()
        for y in range(4, 16):
            for x in range(4, 26):
                pixel[x, y] = (170, 170, 170)
        for x in range(4, 26):
            pixel[x, 10] = (0, 0, 0)
        salida = trazo_fino(imagen)
        self.assertEqual(salida.getpixel((10, 7)), (255, 255, 255))
        self.assertEqual(salida.getpixel((10, 10)), (0, 0, 0))
        self.assertEqual(salida.getpixel((4, 8))[0], 0)
        oscura = Image.new("RGB", (30, 20), "white")
        pixel = oscura.load()
        for y in range(4, 16):
            for x in range(4, 26):
                pixel[x, y] = (30, 30, 30)
        for x in range(4, 26):
            pixel[x, 10] = (0, 0, 0)
        salida = trazo_fino(oscura)
        self.assertEqual(salida.getpixel((10, 7)), (255, 255, 255))
        self.assertEqual(salida.getpixel((10, 10)), (0, 0, 0))
        self.assertEqual(salida.getpixel((4, 8))[0], 0)

    def test_un_punto_en_el_hueco_pasa_a_la_chapa(self):
        from PIL import Image

        from espesor_jpg import asentar_puntos, mascara_chapa

        imagen = Image.new("RGB", (100, 80), "white")
        pixel = imagen.load()
        for y in range(80):
            for x in range(30):
                pixel[x, y] = (70, 70, 70)
        solido = mascara_chapa(imagen)
        self.assertIsNotNone(solido)
        puntos = [{"x": 70.0, "y": 40.0, "numero": 1}]
        asentar_puntos(puntos, solido, (0.0, 0.0, 100.0, 80.0), 0.0, 0.0)
        self.assertLess(puntos[0]["x"], 30.0)

    def test_zinc_solo_orillas_de_superior_y_media(self):
        puntos, _avisos = plan_cara("zinc_macro", "muro", 100, 90)
        self.assertEqual(len(puntos), 4)
        self.assertFalse(any(p["banda"] == "inferior" for p in puntos))
        self.assertFalse(any(p["columna"] == "medio" for p in puntos))
        tapa, _ = plan_cara("zinc_macro", "top", 100, 70)
        base, _ = plan_cara("zinc_macro", "base", 100, 70)
        self.assertEqual(len(tapa), 4)
        self.assertEqual(len(base), 4)

    def test_poliuretano_apoya_el_centro_en_el_brace_y_suma_ocultas(self):
        alto = 90
        partes = [
            {"nombre": "Brace medio", "x0": 8, "x1": 92, "y0": 50, "y1": 56},
            {"nombre": "Brace inferior", "x0": 8, "x1": 92, "y0": 16, "y1": 22},
            {"nombre": "Solera Jacking Pad", "x0": 8, "x1": 20, "y0": 60, "y1": 72},
            {"nombre": "Cartagon esquina", "x0": 40, "x1": 55, "y0": 4, "y1": 12},
            {"nombre": "Valvula alivio", "x0": 70, "x1": 84, "y0": 30, "y1": 40},
        ]
        puntos, avisos = plan_cara("poliuretano", "muro", 100, alto, partes)
        rojos = [p for p in puntos if p["color"] == "rojo"]
        azules = [p for p in puntos if p["color"] == "azul"]
        self.assertEqual(len(rojos), 9)
        self.assertEqual(len(azules), 4)
        self.assertEqual(avisos, [])
        media = next(p for p in rojos if p["banda"] == "media" and p["columna"] == "brace")
        inferior = next(p for p in rojos if p["banda"] == "inferior" and p["columna"] == "brace")
        self.assertEqual(media["y"], 53)
        self.assertEqual(inferior["y"], 19)
        self.assertLess(azules[0]["y"], 60)

    def test_las_ocultas_salen_por_la_forma_aunque_el_nombre_sea_part_number(self):
        from espesor_geo import clasificar_montadas

        ancho, alto = 188.0, 329.0
        partes = [
            {"nombre": "62285-1248-P19_304", "x0": 6, "x1": 182, "y0": 85, "y1": 106, "d0": -6, "d1": 6.7},
            {"nombre": "62285-1248-P19_304", "x0": 6, "x1": 182, "y0": 167, "y1": 187, "d0": -6, "d1": 6.7},
            {"nombre": "62285-1248-P20_305", "x0": 182, "x1": 183, "y0": 167, "y1": 187, "d0": -6, "d1": 6},
            {"nombre": "62285-1248-P18_335", "x0": 184, "x1": 204, "y0": 168, "y1": 170, "d0": -0.5, "d1": 16},
            {"nombre": "62285-1248-P22_300", "x0": 7, "x1": 10, "y0": 50, "y1": 85, "d0": -4, "d1": 13},
            {"nombre": "62285-1248-A10_254", "x0": 5, "x1": 25, "y0": 42, "y1": 85, "d0": -6, "d1": 17.8, "grupo": True},
            {"nombre": "62285-1248-A11_256", "x0": 5, "x1": 25, "y0": 277, "y1": 339, "d0": -6, "d1": 20, "grupo": True},
            {"nombre": "62285-1248-P67_271", "x0": 48, "x1": 76, "y0": 12, "y1": 40, "d0": -6, "d1": -3.5},
            {"nombre": "L845.RADVLV-UNITED BRASS_320", "x0": 120, "x1": 150, "y0": 287, "y1": 310, "d0": 10, "d1": 25},
        ]
        clasificar_montadas(partes, ancho, alto)
        clases = [p.get("clase") for p in partes]
        self.assertEqual(clases[:4], ["brace", "brace", "tapa", "cartabon"])
        self.assertIsNone(clases[4])
        self.assertEqual(clases[5], "jacking")
        puntos, avisos = plan_cara("poliuretano", "muro", ancho, alto, partes)
        azules = {p["columna"]: p for p in puntos if p["color"] == "azul"}
        self.assertEqual(set(azules), {"jacking", "brace", "cartabon", "valvula"})
        self.assertEqual(avisos, [])
        self.assertEqual(azules["cartabon"]["pieza"], "62285-1248-P18_335")
        self.assertLess(azules["jacking"]["y"], 42)

    def test_siempre_cuatro_azules_aunque_falte_una_familia(self):
        ancho, alto = 300.0, 327.0
        partes = [
            {"nombre": "62285-1248-P16_332", "clase": "brace", "x0": 20, "x1": 280, "y0": 210, "y1": 240},
            {"nombre": "62285-1248-P16_333", "clase": "brace", "x0": 20, "x1": 280, "y0": 110, "y1": 140},
            {"nombre": "62285-1248-P17_334", "clase": "cartabon", "x0": 30, "x1": 32, "y0": 120, "y1": 150},
            {"nombre": "L845.RADVLV-UNITED BRASS_321", "x0": 220, "x1": 245, "y0": 100, "y1": 125},
            {"nombre": "L845.RADVLV-UNITED BRASS_322", "x0": 250, "x1": 275, "y0": 270, "y1": 295},
        ]
        puntos, avisos = plan_cara("poliuretano", "muro", ancho, alto, partes)
        azules = [p for p in puntos if p["color"] == "azul"]
        self.assertEqual(len(azules), 4)
        self.assertEqual([p["numero"] for p in azules], [1, 2, 3, 4])
        self.assertEqual(len({p["pieza"] for p in azules}), 4)
        self.assertFalse(any("Jacking" in aviso for aviso in avisos))
        self.assertTrue(all(p["aviso"] == "" for p in azules))

    def test_la_tapa_del_brace_no_se_senala_y_el_cartabon_es_el_triangulo(self):
        ancho, alto = 300.0, 327.0
        partes = [
            {"nombre": "62285-1248-P16_332", "x0": 4, "x1": 297, "y0": 138, "y1": 176, "d0": 0.5, "d1": 18},
            {"nombre": "62285-1248-P16_333", "x0": 4, "x1": 297, "y0": 222, "y1": 260, "d0": 0.5, "d1": 18},
            {"nombre": "62285-1248-P17_334", "x0": 2.5, "x1": 3.8, "y0": 139, "y1": 176, "d0": 0.5, "d1": 17.6},
            {"nombre": "62285-1248-P18_335", "x0": 298, "x1": 318, "y0": 140, "y1": 142, "d0": -0.5, "d1": 16},
            {"nombre": "L845.RADVLV-UNITED BRASS_321", "x0": 220, "x1": 245, "y0": 90, "y1": 115, "d0": 10, "d1": 25},
        ]
        from espesor_geo import clasificar_montadas

        clasificar_montadas(partes, ancho, alto)
        self.assertEqual(partes[2]["clase"], "tapa")
        self.assertEqual(partes[3]["clase"], "cartabon")
        puntos, _avisos = plan_cara("poliuretano", "muro", ancho, alto, partes)
        azules = [p for p in puntos if p["color"] == "azul"]
        piezas = [p["pieza"] for p in azules]
        self.assertEqual(len(azules), 4)
        self.assertNotIn("62285-1248-P17_334", piezas)
        self.assertEqual(piezas.count("62285-1248-P16_332") + piezas.count("62285-1248-P16_333"), 2)
        self.assertIn("62285-1248-P18_335", piezas)

    def test_tapa_de_poliuretano_sigue_el_texto_de_nueve(self):
        puntos, avisos = plan_cara("poliuretano", "top", 100, 70)
        self.assertEqual(len(puntos), 9)
        self.assertEqual(avisos, [])

    def test_el_azul_toca_su_pieza_y_esquiva_lo_que_estorba(self):
        ancho, alto = 300.0, 327.0
        brace = {"nombre": "62285-1248-P16_332", "clase": "brace", "x0": 4, "x1": 297, "y0": 138, "y1": 176}
        refuerzo = {"nombre": "62285-1248-P30_1", "x0": 145, "x1": 155, "y0": 40, "y1": 138}
        partes = [brace, refuerzo]
        puntos, _avisos = plan_cara("poliuretano", "muro", ancho, alto, partes)
        azul = next(p for p in puntos if p["color"] == "azul")
        self.assertLess(138 - azul["y"], 0.03 * alto)
        self.assertGreater(138 - azul["y"], 0)
        self.assertFalse(140 <= azul["x"] <= 160)

    def test_thermox_va_sobre_la_placa_principal_y_no_sobre_piezas(self):
        from espesor_geo import _dentro_de

        ancho, alto = 320.0, 340.0
        placa = {"nombre": "62285-1248-P14_1", "x0": 10, "x1": 310, "y0": 10, "y1": 330}
        estorbos = [
            {"nombre": "refuerzo", "x0": 140, "x1": 180, "y0": 10, "y1": 330},
            {"nombre": "soporte", "x0": 30, "x1": 80, "y0": 270, "y1": 310},
            {"nombre": "brida", "x0": 250, "x1": 300, "y0": 30, "y1": 80},
        ]
        puntos, avisos = plan_cara("thermox", "muro", ancho, alto, [], placa=placa, estorbos=estorbos)
        self.assertEqual(len(puntos), 9)
        self.assertEqual(avisos, [])
        for punto in puntos:
            self.assertTrue(10 < punto["x"] < 310 and 10 < punto["y"] < 330)
            self.assertFalse(any(_dentro_de((punto["x"], punto["y"]), caja, 0) for caja in estorbos), punto)
            self.assertEqual(punto["pieza"], "62285-1248-P14_1")
        izquierda = [p for p in puntos if p["columna"] == "izquierda"]
        derecha = [p for p in puntos if p["columna"] == "derecha"]
        self.assertTrue(all(p["x"] < 140 for p in izquierda))
        self.assertTrue(all(p["x"] > 180 for p in derecha))

    def test_zinc_tambien_se_aparta_de_lo_montado_en_la_placa(self):
        from espesor_geo import _dentro_de

        ancho, alto = 350.0, 198.0
        placa = {"nombre": "62285-1247-P01_362", "x0": 0, "x1": 350, "y0": 0, "y1": 198}
        registro = {"nombre": "manway", "x0": 150, "x1": 210, "y0": 70, "y1": 140}
        puntos, avisos = plan_cara("zinc_macro", "top", ancho, alto, [], placa=placa, estorbos=[registro])
        self.assertEqual(len(puntos), 4)
        self.assertEqual(avisos, [])
        for punto in puntos:
            self.assertFalse(_dentro_de((punto["x"], punto["y"]), registro, 0))
            self.assertEqual(punto["pieza"], "62285-1247-P01_362")

    def test_sin_placa_thermox_sigue_la_rejilla(self):
        puntos, _ = plan_cara("thermox", "muro", 100, 90)
        self.assertAlmostEqual(puntos[0]["x"], 14.0)

    def test_la_hoja_no_lleva_notas_de_prueba(self):
        fuente = Path(__file__).with_name("espesor_jpg.py").read_text(encoding="utf-8")
        self.assertNotIn("Prueba local", fuente)
        self.assertNotIn("Sin escritura en la base", fuente)
        from espesor_jpg import _linea

        linea = _linea({"numero": 2, "grupo": "oculta", "columna": "cartabon", "pieza": "62285-1248-P18_336"})
        self.assertEqual(linea, "2  debajo de cartabón · 62285-1248-P18")

    def test_el_mismo_tanque_repite_las_aleatorias(self):
        a, _ = plan_cara("thermox", "base", 200, 80)
        b, _ = plan_cara("thermox", "base", 200, 80)
        self.assertEqual([(p["x"], p["y"]) for p in a], [(p["x"], p["y"]) for p in b])

    def test_las_chapas_de_una_pared_van_juntas_aunque_la_camara_mire_la_esquina(self):
        placas = [
            {"normal": (0, 0, 1), "centro": (0, 50, 100), "area": 400},
            {"normal": (0, 0, 1), "centro": (80, 50, 100), "area": 200},
            {"normal": (0, 0, -1), "centro": (0, 50, -100), "area": 350},
            {"normal": (1, 0, 0), "centro": (100, 50, 0), "area": 150},
            {"normal": (-1, 0, 0), "centro": (-100, 50, 0), "area": 40},
            {"normal": (0, -1, 0), "centro": (0, 0, 0), "area": 800},
            {"normal": (0, 1, 0), "centro": (0, 120, 0), "area": 100},
        ]
        grupos = agrupar_muros(placas)
        self.assertEqual(set(grupos), {"SEGM1", "SEGM2", "SEGM3", "SEGM4", "TOP", "BASE"})
        self.assertEqual(len(grupos["SEGM1"]), 2)
        self.assertEqual(grupos["BASE"][0]["area"], 800)
        self.assertEqual(grupos["TOP"][0]["area"], 100)

    def test_nombres_de_pieza(self):
        self.assertEqual(clase_oculta("Solera Jacking Pad:1"), "jacking")
        self.assertEqual(clase_oculta("Cartagon"), "cartabon")
        self.assertEqual(clase_oculta("Valve 2"), "valvula")
        self.assertEqual(clase_oculta("Brace horizontal"), "brace")
        self.assertIsNone(clase_oculta("Segmento 1"))

    def test_el_bitmap_interno_no_pasa_de_seis_megapixeles(self):
        px_w, px_h = tamano_bitmap(868.0, 347.0, 321.0)
        self.assertLessEqual(px_w, 3000)
        self.assertLessEqual(px_w * px_h, 6_000_000)
        self.assertAlmostEqual(px_w / px_h, 868.0 / 347.0, places=2)
        px_w, px_h = tamano_bitmap(321.0, 900.0, 321.0)
        self.assertLessEqual(px_h, 3000)
        self.assertEqual(tamano_bitmap(500.0, 250.0), (1400, 700))

    def test_la_foto_interna_pide_una_captura_chica(self):
        px_w, px_h = tamano_bitmap(868.0, 347.0, 321.0, lado_max=1600, area_max=2_000_000)
        self.assertLessEqual(max(px_w, px_h), 1600)
        self.assertLessEqual(px_w * px_h, 2_000_000)
        self.assertAlmostEqual(px_w / px_h, 868.0 / 347.0, places=2)


class PruebaLocal(unittest.TestCase):
    def test_la_muestra_escribe_jpg_y_no_la_base(self):
        fuente = Path(__file__).with_name("espesor_run.py").read_text(encoding="utf-8")
        self.assertNotIn("import cotas_dossier", fuente)
        self.assertNotIn("psycopg", fuente)
        self.assertNotIn("alimentar_bd", fuente)
        with tempfile.TemporaryDirectory() as tmp:
            result = generar({"esquema": "poliuretano", "otc": True, "muestra": True, "solo": True, "carpeta": tmp})
            self.assertTrue(result["ok"], result.get("message"))
            self.assertFalse(result["bd"])
            self.assertEqual(result["count"], 70)
            self.assertEqual(result["fotos"], 10)
            manifiesto = json.loads((Path(tmp) / "manifiesto.json").read_text(encoding="utf-8"))
            self.assertFalse(manifiesto["bd"])
            self.assertTrue(manifiesto["zinc"])
            self.assertTrue((Path(tmp) / "SEGMENT_1.jpg").is_file())
            self.assertTrue((Path(tmp) / "SEGMENT_1_PARTES_OCULTAS.jpg").is_file())
            self.assertTrue((Path(tmp) / "TOP_COVER.jpg").is_file())
            self.assertFalse((Path(tmp) / "TOP_COVER_PARTES_OCULTAS.jpg").exists())

    def test_thermox_y_zinc_siguen_en_seis(self):
        for esquema in ("thermox", "zinc_macro"):
            with tempfile.TemporaryDirectory() as tmp:
                result = generar({"esquema": esquema, "muestra": True, "solo": True, "carpeta": tmp})
                self.assertEqual(result["fotos"], 6, esquema)

    def test_thermox_de_muestra_son_54(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = generar({"esquema": "thermox", "muestra": True, "solo": True, "carpeta": tmp})
            self.assertEqual(result["count"], 54)

    def test_zinc_de_muestra_son_24(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = generar({"esquema": "zinc_macro", "muestra": True, "solo": True, "carpeta": tmp})
            self.assertEqual(result["count"], 24)

    def test_shot_blast_marca_igual_que_poliuretano_y_en_su_carpeta(self):
        alto = 90
        partes = [
            {"nombre": "Brace medio", "x0": 8, "x1": 92, "y0": 50, "y1": 56},
            {"nombre": "Brace inferior", "x0": 8, "x1": 92, "y0": 16, "y1": 22},
            {"nombre": "Solera Jacking Pad", "x0": 8, "x1": 20, "y0": 60, "y1": 72},
            {"nombre": "Cartagon esquina", "x0": 40, "x1": 55, "y0": 4, "y1": 12},
            {"nombre": "Valvula alivio", "x0": 70, "x1": 84, "y0": 30, "y1": 40},
        ]
        poli, _ = plan_cara("poliuretano", "muro", 100, alto, partes)
        blast, _ = plan_cara("shot_blast", "muro", 100, alto, partes)
        firma = lambda puntos: [(p["x"], p["y"], p["color"], p["numero"], p["columna"]) for p in puntos]
        self.assertEqual(firma(poli), firma(blast))
        with tempfile.TemporaryDirectory() as tmp:
            result = generar({"muestra": True, "carpeta": tmp})
            self.assertTrue(result["ok"], result.get("message"))
            self.assertEqual(result["fotos"], 32)
            carpeta = Path(tmp) / "shot blast"
            self.assertTrue((carpeta / "SEGMENT_1.jpg").is_file())
            self.assertTrue((carpeta / "SEGMENT_1_PARTES_OCULTAS.jpg").is_file())
            self.assertFalse((carpeta / "TOP_COVER_PARTES_OCULTAS.jpg").exists())
            manifiesto = json.loads((carpeta / "manifiesto.json").read_text(encoding="utf-8"))
            self.assertEqual(manifiesto["esquema"], "shot_blast")
            self.assertFalse(manifiesto["zinc"])
            self.assertEqual(manifiesto["puntos"], 70)


if __name__ == "__main__":
    unittest.main()
