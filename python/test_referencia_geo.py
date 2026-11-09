"""Motor de geometría de COTAS_POR_REFERENCIA con datos sintéticos (sin Inventor)."""

from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

import referencia_geo as rg

IDENT = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]]


def _caja(x0, y0, z0, x1, y1, z1, planos=False, compartidos=False):
    v = [
        (x, y, z)
        for z in (z0, z1)
        for y in (y0, y1)
        for x in (x0, x1)
    ]
    aristas = [(0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (1, 3), (4, 6), (5, 7), (0, 4), (1, 5), (2, 6), (3, 7)]
    sv, si = [], []
    if compartidos:
        for p in v:
            sv.extend(p)
        for a, b in aristas:
            si.extend([a + 1, b + 1])
    else:
        for a, b in aristas:
            base = len(sv) // 3
            sv.extend(v[a] + v[b])
            si.extend([base + 1, base + 2])
    caras = [(0, 1, 3, 2), (4, 5, 7, 6), (0, 1, 5, 4), (2, 3, 7, 6), (0, 2, 6, 4), (1, 3, 7, 5)]
    fv = [c for p in v for c in p]
    fi = []
    for a, b, c, d in caras:
        fi.extend([a + 1, b + 1, c + 1, a + 1, c + 1, d + 1])
    raw = {"sv": sv, "si": si, "fv": fv, "fi": fi}
    if planos:
        area = (x1 - x0) * (y1 - y0)
        raw["planos"] = [
            {"n": [0, 0, 1], "p": [x0, y0, z1], "area": area},
            {"n": [0, 0, -1], "p": [x0, y0, z0], "area": area},
        ]
    return raw


def _arco(cx, cy, z, r, a0, a1, n=24):
    return [(cx + r * math.cos(a), cy + r * math.sin(a), z) for a in np.linspace(a0, a1, n)]


def _boquilla(cx, cy, r, z0, z1):
    sv, si = [], []

    def poner(pts):
        base = len(sv) // 3
        for p in pts:
            sv.extend(p)
        for i in range(len(pts) - 1):
            si.extend([base + i + 1, base + i + 2])

    for z in (z0, z1):
        poner(_arco(cx, cy, z, r, 0.0, math.pi))
        poner(_arco(cx, cy, z, r, math.pi, 2 * math.pi))
    fv, fi = [], []
    ang = np.linspace(0, 2 * math.pi, 33)[:-1]
    for z in (z0, z1):
        for a in ang:
            fv.extend((cx + r * math.cos(a), cy + r * math.sin(a), z))
    k = len(ang)
    for i in range(1, k - 1):
        fi.extend([k + 1, k + i + 1, k + i + 2])
    return {"sv": sv, "si": si, "fv": fv, "fi": fi}


def _snap():
    return {
        "centro_tanque": [50, 40, -50],
        "anclas": {"SEGM1": "placa"},
        "defs": {
            "placa.ipt": _caja(0, 0, -0.5, 100, 80, 0, planos=True),
            "boq.ipt": _boquilla(30, 20, 5, 0, 10),
            "caja.ipt": _caja(60, 50, 0, 70, 55, 3),
            "atras.ipt": _caja(10, 10, -10, 20, 20, -5),
        },
        "occs": [
            {"key": "placa", "def": "placa.ipt", "m": IDENT, "cara": "SEGM1", "placa": True, "name": "placa:1"},
            {"key": "boq", "def": "boq.ipt", "m": IDENT, "cara": "SEGM1", "name": "boq:1", "tipo": "BOQ"},
            {"key": "caja", "def": "caja.ipt", "m": IDENT, "cara": "SEGM1", "name": "caja:1", "tipo": "CAJA"},
            {"key": "atras", "def": "atras.ipt", "m": IDENT, "cara": "SEGM1", "name": "atras:1", "tipo": "ATRAS"},
            {"key": "otro", "def": "atras.ipt", "m": IDENT, "cara": "SEGM2", "name": "otro:1", "tipo": "OTRO"},
        ],
    }


class CadenasTest(unittest.TestCase):
    def test_vertices_compartidos_dan_una_arista_por_tramo(self):
        raw = _caja(0, 0, 0, 1, 2, 3, compartidos=True)
        self.assertEqual(len(rg.cadenas(raw["sv"], raw["si"])), 12)

    def test_vertices_duplicados_dan_una_arista_por_tramo(self):
        raw = _caja(0, 0, 0, 1, 2, 3)
        self.assertEqual(len(rg.cadenas(raw["sv"], raw["si"])), 12)

    def test_circulo_cerrado_es_una_cadena(self):
        pts = _arco(0, 0, 0, 2, 0, 2 * math.pi, 40)
        pts[-1] = pts[0]
        sv = [c for p in pts[:-1] for c in p]
        n = len(pts) - 1
        si = []
        for i in range(n):
            si.extend([i + 1, (i + 1) % n + 1])
        cads = rg.cadenas(sv, si)
        self.assertEqual(len(cads), 1)
        c = rg.ajustar_circulo(cads[0])
        self.assertAlmostEqual(c["r"], 2.0, places=9)
        self.assertAlmostEqual(c["barrido"], 2 * math.pi, places=6)


class CirculoTest(unittest.TestCase):
    def test_arco_exacto(self):
        c = rg.ajustar_circulo(_arco(3, -4, 7, 1.27, 0.2, 2.0, 9))
        self.assertAlmostEqual(c["r"], 1.27, places=9)
        np.testing.assert_allclose(c["c"], [3, -4, 7], atol=1e-9)
        self.assertAlmostEqual(abs(c["n"][2]), 1.0, places=9)

    def test_recta_no_es_circulo(self):
        self.assertIsNone(rg.ajustar_circulo([(0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0)]))

    def test_polilinea_quebrada_no_es_circulo(self):
        self.assertIsNone(rg.ajustar_circulo([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]))


class MarcoYRasgosTest(unittest.TestCase):
    def setUp(self):
        self.snap = _snap()
        self.defs, self.occs = rg.preparar(self.snap)
        self.marcos = rg.marcos_de(self.snap, self.defs, self.occs)

    def test_marco_normal_afuera_y_arriba_mundo(self):
        mc = self.marcos["SEGM1"]
        np.testing.assert_allclose(mc["n"], [0, 0, 1], atol=1e-9)
        np.testing.assert_allclose(mc["v"], [0, 1, 0], atol=1e-9)
        np.testing.assert_allclose(mc["u"], [1, 0, 0], atol=1e-9)
        self.assertAlmostEqual(mc["exterior"], 0.0)
        self.assertAlmostEqual(mc["span_u"], 100.0)
        self.assertAlmostEqual(mc["span_v"], 80.0)

    def test_marco_tanque_del_otro_lado_invierte_normal(self):
        self.snap["centro_tanque"] = [50, 40, 50]
        mc = rg.marcos_de(self.snap, self.defs, self.occs)["SEGM1"]
        np.testing.assert_allclose(mc["n"], [0, 0, -1], atol=1e-9)
        self.assertAlmostEqual(mc["exterior"], 0.5)

    def test_cotas_exactas_mm(self):
        filas = {p["key"]: p for p in rg.piezas_cara("SEGM1", self.snap, self.defs, self.occs, self.marcos, "mm")}
        self.assertEqual(set(filas), {"boq", "caja"})
        boq = filas["boq"]
        self.assertTrue(boq["circ"])
        self.assertAlmostEqual(boq["x"], 300.0, places=6)
        self.assertAlmostEqual(boq["y"], 200.0, places=6)
        self.assertAlmostEqual(boq["r"], 50.0, places=6)
        caja = filas["caja"]
        self.assertFalse(caja["circ"])
        self.assertAlmostEqual(caja["x"], 600.0, places=9)
        self.assertAlmostEqual(caja["y"], 500.0, places=9)

    def test_matriz_de_instancia_se_aplica(self):
        self.occs["caja"]["m"] = [[1, 0, 0, 5.08], [0, 1, 0, -2.54], [0, 0, 1, 0]]
        filas = {p["key"]: p for p in rg.piezas_cara("SEGM1", self.snap, self.defs, self.occs, self.marcos, "in")}
        self.assertAlmostEqual(filas["caja"]["x"], 65.08 / 2.54, places=9)
        self.assertAlmostEqual(filas["caja"]["y"], 47.46 / 2.54, places=9)

    def test_caja_cuadrada_con_agujero_chico_no_es_circular(self):
        raw = _caja(40, 40, 0, 50, 50, 1)
        hueco = _boquilla(45, 45, 1, 0, 1)
        base = len(raw["sv"]) // 3
        raw["sv"] += hueco["sv"]
        raw["si"] += [i + base for i in hueco["si"]]
        defn = rg.preparar_def(raw)
        r = rg.rasgo(defn, IDENT, self.marcos["SEGM1"])
        self.assertFalse(r["circ"])
        self.assertAlmostEqual(r["x"], 40.0)


class AnclaYAutoTest(unittest.TestCase):
    def test_muro_sin_placa_confirmada_usa_lamina_mayor(self):
        snap = _snap()
        snap["anclas"] = {}
        for o in snap["occs"]:
            if o["key"] == "placa":
                o["placa"] = False
        defs, occs = rg.preparar(snap)
        mc = rg.marcos_de(snap, defs, occs)["SEGM1"]
        self.assertEqual(mc["ancla"], "placa")
        self.assertAlmostEqual(mc["span_u"], 100.0)

    def test_planos_de_facetas(self):
        defn = rg.preparar_def({k: v for k, v in _caja(0, 0, 0, 10, 4, 1).items()})
        mayor = defn["planos"][0]
        self.assertAlmostEqual(mayor["area"], 40.0)
        self.assertAlmostEqual(abs(mayor["n"][2]), 1.0)

    def test_sin_bolsa_entra_solo_si_toca_la_placa(self):
        snap = _snap()
        snap["occs"] = [o for o in snap["occs"] if o["key"] in ("placa", "atras")]
        snap["defs"]["pegada.ipt"] = _caja(5, 5, 0, 8, 8, 2)
        snap["defs"]["flotante.ipt"] = _caja(20, 5, 1, 23, 8, 2)
        snap["occs"] += [
            {"key": "pegada", "def": "pegada.ipt", "m": IDENT, "cara": "", "name": "p:1", "tipo": "P"},
            {"key": "flotante", "def": "flotante.ipt", "m": IDENT, "cara": "", "name": "f:1", "tipo": "F"},
        ]
        snap["occs"][1]["cara"] = ""
        defs, occs = rg.preparar(snap)
        marcos = rg.marcos_de(snap, defs, occs)
        filas = {p["key"] for p in rg.piezas_cara("SEGM1", snap, defs, occs, marcos, "in")}
        self.assertEqual(filas, {"pegada"})

    def test_bolsa_parcial_conserva_lo_anclado_a_la_piel(self):
        snap = _snap()
        snap["defs"]["pegada.ipt"] = _caja(5, 5, 0, 8, 8, 2)
        snap["defs"]["cruza.ipt"] = _caja(12, 5, -0.8, 16, 9, 0.5)
        snap["defs"]["flotante.ipt"] = _caja(20, 5, 1.0, 23, 8, 2)
        snap["defs"]["ajena.ipt"] = _caja(30, 5, 0, 34, 9, 2)
        snap["occs"] += [
            {"key": "pegada", "def": "pegada.ipt", "m": IDENT, "cara": "", "name": "p:1", "tipo": "P"},
            {"key": "cruza", "def": "cruza.ipt", "m": IDENT, "cara": "", "name": "c:1", "tipo": "C"},
            {"key": "flotante", "def": "flotante.ipt", "m": IDENT, "cara": "", "name": "f:1", "tipo": "F"},
            {"key": "ajena", "def": "ajena.ipt", "m": IDENT, "cara": "SEGM2", "name": "a:1", "tipo": "A"},
        ]
        defs, occs = rg.preparar(snap)
        marcos = rg.marcos_de(snap, defs, occs)
        filas = {p["key"] for p in rg.piezas_cara("SEGM1", snap, defs, occs, marcos, "in")}
        self.assertIn("boq", filas)
        self.assertIn("pegada", filas)
        self.assertIn("cruza", filas)
        self.assertNotIn("flotante", filas)
        self.assertNotIn("ajena", filas)


class ExportarTest(unittest.TestCase):
    def test_jpgs_y_vista(self):
        with tempfile.TemporaryDirectory() as tmp:
            files, errors = [], []
            res = rg.exportar(_snap(), tmp, "JOB1", "mm", files, errors)
            self.assertEqual(res, {"SEGM1": 2}, errors)
            nombres = sorted(Path(f).relative_to(tmp).as_posix() for f in files)
            self.assertIn("SEGM1/VISTA_ALAMBRICA.jpg", nombres)
            self.assertIn("SEGM1/BOQ/JOB1__BOQ__XCENTRO_300.jpg", nombres)
            self.assertIn("SEGM1/BOQ/JOB1__BOQ__YCENTRO_200.jpg", nombres)
            self.assertIn("SEGM1/CAJA/JOB1__CAJA__XMIN_600.jpg", nombres)
            self.assertIn("SEGM1/CAJA/JOB1__CAJA__YMIN_500.jpg", nombres)


if __name__ == "__main__":
    unittest.main()
