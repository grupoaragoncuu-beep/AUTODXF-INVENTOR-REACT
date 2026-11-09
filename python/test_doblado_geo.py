"""La cara de doblado sale de la lámina, no del rectángulo ni de lo ensamblado encima.

La ventana de Sólido4 (≈5.5×2.4 in) no es un parche: el filtro viejo la tiraba
y el JPG quedaba en blanco. La piel alámbrica la conserva. Un parche montado
encima no entra.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from acotacion_run import _filtrar_cortes_ensamblados
from doblado_geo import cara, elegir_lamina, guardar_vista
from drawing_jpg import list_face_cotas
from referencia_geo import preparar_def

CM = 2.54
W, H, THK = 10 * CM, 27.5 * CM, 0.25 * CM
X0, X1, Y0, Y1 = 6.0, 20.0, 50.0, 56.0


def _quad(x0, y0, x1, y1, z) -> list[tuple[float, float, float]]:
    return [
        (x0, y0, z),
        (x1, y0, z),
        (x1, y1, z),
        (x0, y0, z),
        (x1, y1, z),
        (x0, y1, z),
    ]


def _placa(*, parche: bool = False, labio: bool = False) -> dict:
    """Piel exterior con ventana. Aristas compartidas parten en el mismo vértice, como Inventor."""
    z = THK
    verts = []
    for (x0, y0, x1, y1) in (
        (0, 0, X0, Y0),
        (X0, 0, X1, Y0),
        (X1, 0, W, Y0),
        (0, Y0, X0, Y1),
        (X1, Y0, W, Y1),
        (0, Y1, X0, H),
        (X0, Y1, X1, H),
        (X1, Y1, W, H),
    ):
        verts += _quad(x0, y0, x1, y1, z)
    verts += _quad(0, 0, W, H, 0.0)[::-1]
    if parche:
        verts += _quad(10, 4, 14, 8, z)
    if labio:
        verts += [
            (0, H, z),
            (W, H, z),
            (W, H, z + 1.5),
            (0, H, z),
            (W, H, z + 1.5),
            (0, H, z + 1.5),
        ]
    tris = np.asarray(verts, dtype=float).reshape(-1, 3, 3)
    aristas = []
    for tri in tris:
        for i, j in ((0, 1), (1, 2), (2, 0)):
            aristas.append({"pts": np.stack([tri[i], tri[j]]), "circ": None})
    from referencia_geo import planos_de_facetas

    return {"aristas": aristas, "tris": tris, "planos": planos_de_facetas(tris)}


def _raw(tris: np.ndarray) -> dict:
    fv = [round(float(x), 4) for x in tris.reshape(-1)]
    return {"sv": [], "si": [], "fv": fv, "fi": list(range(1, len(fv) // 3 + 1))}


def _basis():
    return ((0.0, 0.0, THK), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))


def _barreno() -> dict:
    """Cuadrado 20 cm con un hueco de 1 in y el círculo del sólido."""
    z = THK
    x0, x1, y0, y1, w, h = 8.0, 8.0 + CM, 8.0, 8.0 + CM, 20.0, 20.0
    verts = []
    for a, b, c, d in (
        (0, 0, x0, y0),
        (x0, 0, x1, y0),
        (x1, 0, w, y0),
        (0, y0, x0, y1),
        (x1, y0, w, y1),
        (0, y1, x0, h),
        (x0, y1, x1, h),
        (x1, y1, w, h),
    ):
        verts += _quad(a, b, c, d, z)
    tris = np.asarray(verts, dtype=float).reshape(-1, 3, 3)
    from referencia_geo import planos_de_facetas

    centro = np.array([(x0 + x1) / 2, (y0 + y1) / 2, z])
    return {
        "aristas": [
            {
                "pts": np.stack([centro, centro]),
                "circ": {"c": centro, "n": np.array([0.0, 0.0, 1.0]), "r": CM / 2, "barrido": 2 * np.pi},
            }
        ],
        "tris": tris,
        "planos": planos_de_facetas(tris),
    }


class DobladoAlambricoTest(unittest.TestCase):
    def test_ventana_no_desaparece(self) -> None:
        geom = cara(_placa(), "in", _basis())
        self.assertIsNotNone(geom)
        self.assertAlmostEqual(geom["measures"]["LENGTH"], 10.0, delta=0.05)
        self.assertAlmostEqual(geom["measures"]["WIDTH"], 27.5, delta=0.05)
        self.assertAlmostEqual(geom["measures"]["THK"], 0.25, delta=0.03)
        self.assertEqual([h["kind"] for h in geom["holes"]], ["cut"])
        corte = geom["holes"][0]
        xs = [p[0] for p in corte["pts"]]
        ys = [p[1] for p in corte["pts"]]
        self.assertAlmostEqual(max(xs) - min(xs), (X1 - X0) / CM, delta=0.05)
        self.assertAlmostEqual(max(ys) - min(ys), (Y1 - Y0) / CM, delta=0.05)
        self.assertEqual(_filtrar_cortes_ensamblados(geom["holes"], "in"), [])
        cotas = list_face_cotas(
            geom["outline"],
            geom["holes"],
            geom["measures"],
            hole_anchor="edge",
            measure_walls=False,
            landscape=False,
        )
        self.assertIn("CUT", [c["kind"] for c in cotas])

    def test_parche_en_la_piel_no_es_corte(self) -> None:
        geom = cara(_placa(parche=True), "in", _basis())
        self.assertEqual(len(geom["holes"]), 1)
        self.assertEqual(geom["holes"][0]["kind"], "cut")

    def test_labio_no_deforma_el_contorno(self) -> None:
        geom = cara(_placa(labio=True), "in", _basis())
        self.assertAlmostEqual(geom["measures"]["WIDTH"], 27.5, delta=0.05)
        self.assertEqual(len(geom["holes"]), 1)

    def test_lamina_gana_al_solido_chico(self) -> None:
        placa = _raw(_placa()["tris"])
        parche = _raw(np.asarray(_quad(0, 0, 4, 4, 0) + _quad(0, 0, 4, 4, 0.3), dtype=float).reshape(-1, 3, 3))
        elegido = elegir_lamina([parche, placa])
        defn = preparar_def(elegido)
        geom = cara(defn, "in", _basis())
        self.assertAlmostEqual(geom["measures"]["WIDTH"], 27.5, delta=0.08)
        self.assertEqual(len(geom["holes"]), 1)

    def test_barreno_es_circulo(self) -> None:
        geom = cara(_barreno(), "in", _basis())
        self.assertEqual([h["kind"] for h in geom["holes"]], ["circle"])
        self.assertAlmostEqual(geom["holes"][0]["dia"], 1.0, delta=0.05)

    def test_vista_alambrica_tiene_tinta(self) -> None:
        defn = _placa()
        geom = cara(defn, "in", _basis())
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "VISTA_ALAMBRICA.jpg"
            guardar_vista(defn, geom["_marco"], dest, "in")
            self.assertGreater(dest.stat().st_size, 1000)
            from PIL import Image

            gris = np.asarray(Image.open(dest).convert("L"))
            self.assertGreater(int((gris < 250).sum()), 50)


if __name__ == "__main__":
    unittest.main()
