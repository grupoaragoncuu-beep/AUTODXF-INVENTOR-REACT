"""El espesor se mide entre las dos caras del alma, no desde la punta del pie."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from drawing_focus import _par_espesor, save_thk_drawing


def _ele(t: float = 0.31):
    """Pie hacia la izquierda, alma vertical a la derecha."""
    return [
        (0.0, 0.0),
        (10.0 + t, 0.0),
        (10.0 + t, 8.0),
        (10.0, 8.0),
        (10.0, t),
        (0.0, t),
    ]


class EspesorTest(unittest.TestCase):
    def test_el_par_es_el_alma_no_la_punta(self) -> None:
        t = 0.31
        horizontal, a, b, y = _par_espesor(_ele(t), t)
        self.assertTrue(horizontal)
        self.assertAlmostEqual(a, 10.0, delta=0.05)
        self.assertAlmostEqual(b, 10.0 + t, delta=0.05)
        self.assertGreater(y, 1.0)
        self.assertLess(y, 7.0)

    def test_el_jpg_muestra_las_dos_caras(self) -> None:
        t = 0.31
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "thk.jpg"
            save_thk_drawing(dest, _ele(t), title="t", unit="in", thk=t)
            grupos = _columnas_oscuras(dest, margen=40)
        self.assertGreaterEqual(len(grupos), 2)
        self.assertGreater(grupos[-1][0] - grupos[0][-1], 8)


def _columnas_oscuras(path: Path, margen: int) -> list[list[int]]:
    imagen = Image.open(path).convert("RGB")
    px = imagen.load()
    y = max(0, imagen.height // 2 - margen)
    oscuros = []
    for x in range(imagen.width):
        r, g, b = px[x, y]
        if r + g + b < 250:
            oscuros.append(x)
    grupos: list[list[int]] = []
    for x in oscuros:
        if grupos and x - grupos[-1][-1] <= 3:
            grupos[-1].append(x)
        else:
            grupos.append([x])
    return grupos


if __name__ == "__main__":
    unittest.main()
