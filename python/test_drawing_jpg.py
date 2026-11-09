"""Cotas de PIEZAS_ACOTADAS: el rótulo no se recorta, el rectángulo son dos cotas y el nombre no lleva el tamaño."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from drawing_jpg import _bajar_si_empalma, _cajas_chocan, _capa_texto, _font, list_face_cotas, save_part_drawing


def _placa():
    outline = [(0, 0), (40, 0), (40, 20), (0, 20)]
    holes = [
        {"kind": "cut", "pts": [(4, 6), (22.5, 6), (22.5, 12), (4, 12)]},
        {"kind": "circle", "x": 10, "y": 10, "dia": 0.5},
        {
            "kind": "slot",
            "x0": 28,
            "y0": 8,
            "x1": 34,
            "y1": 8,
            "dia": 1.0,
        },
    ]
    measures = {"LENGTH": 40.0, "WIDTH": 20.0, "THK": 0.25}
    return outline, holes, measures


class CotasCaraTest(unittest.TestCase):
    def test_rectangulo_y_slot_son_largo_y_ancho(self) -> None:
        outline, holes, measures = _placa()
        cotas = list_face_cotas(outline, holes, measures, hole_anchor="edge", measure_walls=False)
        nombres = [c["name"] for c in cotas]
        self.assertIn("LENGTH_18.50", nombres)
        self.assertIn("WIDTH_6.00", nombres)
        self.assertIn("LENGTH_7.00", nombres)
        self.assertIn("WIDTH_1.00", nombres)
        self.assertFalse(any("x" in n and n.startswith(("CUT", "SLOT")) for n in nombres))
        self.assertFalse(any("_C" in n or "_D" in n or "_S" in n for n in nombres))
        self.assertIn("X_4.00", nombres)
        self.assertIn("X_9.75", nombres)
        self.assertIn("HOLE_0.50", nombres)
        ejes = [c for c in cotas if c["kind"] in {"CUT", "SLOT"}]
        self.assertTrue(all(c.get("axis") in {"L", "W"} for c in ejes))
        self.assertEqual(sum(1 for c in ejes if c["kind"] == "CUT" and c["axis"] == "L"), 1)
        self.assertEqual(sum(1 for c in ejes if c["kind"] == "CUT" and c["axis"] == "W"), 1)

    def test_la_capa_conserva_el_glifo(self) -> None:
        capa = _capa_texto("LENGTH=42.62 in", _font(40, False))
        tinta = capa.getbbox()
        self.assertIsNotNone(tinta)
        self.assertGreaterEqual(tinta[0], 2)
        self.assertGreaterEqual(tinta[1], 2)
        self.assertLessEqual(tinta[2], capa.width - 2)
        self.assertLessEqual(tinta[3], capa.height - 2)

    def test_barrenos_cercanos_no_comparten_rotulo(self) -> None:
        outline = [(0, 0), (20, 0), (20, 12), (0, 12)]
        holes = [{"kind": "circle", "x": 4 + i * 1.2, "y": 3, "dia": 1.14} for i in range(8)]
        holes.append({"kind": "circle", "x": 16, "y": 8, "dia": 1.19})
        measures = {"LENGTH": 20.0, "WIDTH": 12.0, "THK": 0.25}
        cotas = list_face_cotas(outline, holes, measures, hole_anchor="edge", measure_walls=False)
        self.assertIn("HOLE_1.14", [c["name"] for c in cotas])
        self.assertIn("HOLE_1.19", [c["name"] for c in cotas])
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "h.jpg"
            foco = next(c for c in cotas if c["name"] == "HOLE_1.19")
            save_part_drawing(
                dest,
                outline,
                holes,
                title="t",
                subtitle="",
                unit="in",
                measures=measures,
                hole_anchor="edge",
                measure_walls=False,
                focus=foco,
            )
            azul = _pixeles_resaltados(dest)
            self.assertGreater(azul, 400)
            self.assertLess(azul, 8000)

    def test_el_jpg_no_corta_el_rotulo(self) -> None:
        outline, holes, measures = _placa()
        cotas = list_face_cotas(outline, holes, measures, hole_anchor="edge", measure_walls=False)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for cota in cotas:
                if cota["kind"] not in {"LENGTH", "CUT", "SLOT", "HOLE", "X"}:
                    continue
                dest = root / f"{cota['name']}.jpg"
                save_part_drawing(
                    dest,
                    outline,
                    holes,
                    title="placa",
                    subtitle="",
                    unit="in",
                    measures=measures,
                    hole_anchor="edge",
                    measure_walls=False,
                    focus=cota,
                )
                self.assertFalse(_borde_con_tinta(dest), cota["name"])

    def test_largo_y_ancho_del_corte_quedan_en_el_hueco(self) -> None:
        outline, holes, measures = _placa()
        cotas = list_face_cotas(outline, holes, measures, hole_anchor="edge", measure_walls=False)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for nombre, interior in (("LENGTH_18.50", True), ("WIDTH_6.00", False)):
                foco = next(c for c in cotas if c["name"] == nombre)
                dest = root / f"{nombre}.jpg"
                save_part_drawing(
                    dest,
                    outline,
                    holes,
                    title="placa",
                    subtitle="",
                    unit="in",
                    measures=measures,
                    hole_anchor="edge",
                    measure_walls=False,
                    focus=foco,
                )
                self.assertFalse(_tinta_arriba(dest), nombre)
                if interior:
                    self.assertGreater(_tinta_interior_corte(dest), 40, nombre)
                else:
                    self.assertGreater(_tinta_al_lado_del_corte(dest), 40, nombre)

    def test_la_ordenada_que_choca_baja(self) -> None:
        ocupado = (10.0, 100.0, 180.0, 140.0)
        box = (20.0, 110.0, 160.0, 150.0)
        nuevo, movido = _bajar_si_empalma(box, [ocupado], 500, 500)
        self.assertTrue(movido)
        self.assertGreater(nuevo[1], box[1])
        self.assertLess(nuevo[0], box[0])
        self.assertFalse(_cajas_chocan(nuevo, ocupado, 8))

    def test_ordenada_junto_al_origen_no_se_recorta(self) -> None:
        outline = [(0, 0), (10, 0), (10, 18), (0, 18)]
        holes = [{"kind": "circle", "x": 4, "y": 0.83, "dia": 0.5}]
        measures = {"LENGTH": 10.0, "WIDTH": 18.0, "THK": 0.25}
        cotas = list_face_cotas(
            outline, holes, measures, hole_anchor="edge", measure_walls=False, landscape=False
        )
        foco = next(c for c in cotas if c["kind"] == "Y" and abs(c["value"] - 0.58) < 0.05)
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "y.jpg"
            save_part_drawing(
                dest,
                outline,
                holes,
                title="t",
                subtitle="",
                unit="in",
                measures=measures,
                hole_anchor="edge",
                measure_walls=False,
                focus=foco,
                landscape=False,
            )
            self.assertFalse(_borde_con_tinta(dest))


def _tinta_arriba(path: Path, alto: int = 36) -> bool:
    imagen = Image.open(path).convert("RGB")
    px = imagen.load()
    for y in range(min(alto, imagen.height)):
        for x in range(imagen.width):
            r, g, b = px[x, y]
            if r + g + b < 400:
                return True
    return False


def _caja_azul(path: Path):
    imagen = Image.open(path).convert("RGB")
    px = imagen.load()
    w, h = imagen.size
    xs, ys = [], []
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if abs(r - 214) < 8 and abs(g - 234) < 8 and abs(b - 248) < 8 and b > r + 20:
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def _tinta_interior_corte(path: Path) -> int:
    caja = _caja_azul(path)
    if caja is None:
        return 0
    x0, y0, x1, y1 = caja
    imagen = Image.open(path).convert("RGB")
    px = imagen.load()
    cuenta = 0
    for y in range(y0 + 10, y1 - 10):
        for x in range(x0 + 10, x1 - 10):
            r, g, b = px[x, y]
            if r + g + b < 280:
                cuenta += 1
    return cuenta


def _tinta_al_lado_del_corte(path: Path) -> int:
    caja = _caja_azul(path)
    if caja is None:
        return 0
    x0, y0, x1, y1 = caja
    imagen = Image.open(path).convert("RGB")
    px = imagen.load()
    medio = (y0 + y1) / 2
    cuenta = 0
    for y in range(int(medio - (y1 - y0) * 0.25), int(medio + (y1 - y0) * 0.25)):
        for x in range(max(0, x0 - 180), max(0, x0 - 6)):
            r, g, b = px[x, y]
            if r + g + b < 280:
                cuenta += 1
    return cuenta


def _pixeles_resaltados(path: Path) -> int:
    imagen = Image.open(path).convert("RGB")
    px = imagen.load()
    w, h = imagen.size
    cuenta = 0
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if abs(r - 214) < 18 and abs(g - 234) < 18 and abs(b - 248) < 18:
                cuenta += 1
    return cuenta


def _borde_con_tinta(path: Path, margen: int = 3) -> bool:
    imagen = Image.open(path).convert("RGB")
    px = imagen.load()
    w, h = imagen.size

    def tinta(x: int, y: int) -> bool:
        r, g, b = px[x, y]
        return r + g + b < 720

    for y in list(range(margen)) + list(range(h - margen, h)):
        for x in range(w):
            if tinta(x, y):
                return True
    for x in list(range(margen)) + list(range(w - margen, w)):
        for y in range(h):
            if tinta(x, y):
                return True
    return False


if __name__ == "__main__":
    unittest.main()
