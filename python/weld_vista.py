"""Tres vistas sombreadas del ensamble: cara, detalle e isométrica.

No abre un plano. Oculta el resto de las piezas, apunta la cámara del
ensamble y la devuelve a su sitio al cerrar.
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

from PIL import Image

from vista_hlr import _apagar_sombras, _estado_vista, _restaurar_vista

_SOMBREADO = 8709


class VistaSoldadura:
    def __init__(self, inv, assembly, centro_tanque=None, cordon=None):
        self.inv = inv
        self.assembly = assembly
        self.centro = centro_tanque
        self.cordon = cordon
        self.saved: list[tuple] = []
        self._lista = False
        try:
            assembly.Activate()
        except Exception:
            pass
        self.view = inv.ActiveView
        self.display = inv.DisplayOptions
        self.state = _estado_vista(self.view, self.view.Camera, self.display)
        try:
            self.display.Show3DIndicator = False
        except Exception:
            pass
        _apagar_sombras(self.view)
        try:
            self.view.AreTexturesOn = True
        except Exception:
            pass
        try:
            # 8710 sombreado con aristas: el 8709 solo sale lavado en el JPG.
            self.view.DisplayMode = 8710
        except Exception:
            self.view.DisplayMode = _SOMBREADO
        self._fondo = _fondo_blanco(inv)
        self._ocultar_todo()

    def cerrar(self) -> None:
        for occ, vis in reversed(self.saved):
            try:
                if bool(occ.Visible) != vis:
                    occ.Visible = vis
            except Exception:
                continue
        if self.cordon is not None:
            try:
                self.cordon.mostrar_todos()
            except Exception:
                pass
        _restaurar_fondo(self.inv, getattr(self, "_fondo", None))
        try:
            _restaurar_vista(self.inv, self.inv.ActiveView, self.inv.TransientGeometry, self.display, self.state)
        except Exception:
            try:
                self.inv.ActiveView.Update()
            except Exception:
                pass

    def tomar(self, junta: dict) -> tuple[Image.Image, Image.Image, Image.Image] | None:
        keep = list(junta.get("visibles") or [])
        for occ in (junta.get("host"), junta.get("pieza"), junta.get("otro")):
            if occ is not None and occ not in keep:
                keep.append(occ)
        keep = [occ for occ in keep if occ is not None]
        if not keep or not junta.get("frame"):
            return None
        shown = []
        previos = []
        try:
            for occ in keep:
                try:
                    occ.Visible = True
                    shown.append(occ)
                except Exception:
                    continue
            if not shown:
                return None
            previos = _material(shown)
            if self.cordon is not None:
                try:
                    self.cordon.mostrar(str(junta.get("id") or ""))
                except Exception:
                    pass
            self.view.Update()
            frente = self._foto(_frente(junta, self.centro))
            detalle = self._foto(_iso(junta, self.centro, cerrado=True))
            iso = self._foto(_iso(junta, self.centro, cerrado=False))
            return frente, detalle, iso
        finally:
            _restaurar_material(previos)
            if self.cordon is not None:
                for grupo in getattr(self.cordon, "_grupos", []) or []:
                    occ = grupo.get("occ") if isinstance(grupo, dict) else None
                    if occ is None:
                        continue
                    try:
                        occ.Visible = False
                    except Exception:
                        continue
            for occ in shown:
                try:
                    occ.Visible = False
                except Exception:
                    continue

    def _ocultar_todo(self) -> None:
        leaves = self.assembly.ComponentDefinition.Occurrences.AllLeafOccurrences
        total = int(leaves.Count)
        for index in range(1, total + 1):
            try:
                occ = leaves.Item(index)
                if bool(occ.Suppressed):
                    continue
                vis = bool(occ.Visible)
            except Exception:
                continue
            self.saved.append((occ, vis))
            if vis:
                try:
                    occ.Visible = False
                except Exception:
                    continue
        self._lista = True
        try:
            self.view.Update()
        except Exception:
            pass

    def _foto(self, encuadre: dict) -> Image.Image:
        tg = self.inv.TransientGeometry
        cam = self.view.Camera
        cam.Perspective = False
        origen = encuadre["origin"]
        mira = encuadre["look"]
        distancia = max(float(encuadre["w"]), float(encuadre["h"]), 10.0) * 2.5
        cam.Target = tg.CreatePoint(float(origen[0]), float(origen[1]), float(origen[2]))
        cam.Eye = tg.CreatePoint(
            float(origen[0] + mira[0] * distancia),
            float(origen[1] + mira[1] * distancia),
            float(origen[2] + mira[2] * distancia),
        )
        arriba = tg.CreateUnitVector(float(encuadre["up"][0]), float(encuadre["up"][1]), float(encuadre["up"][2]))
        cam.UpVector = arriba
        cam.ApplyWithoutTransition()
        cam = self.view.Camera
        cam.UpVector = arriba
        cam.SetExtents(float(encuadre["w"]), float(encuadre["h"]))
        cam.UpVector = arriba
        cam.ApplyWithoutTransition()
        self.view.Update()
        blanco = self.inv.TransientObjects.CreateColor(255, 255, 255)
        px_w = max(640, int(encuadre["px_w"]) * 2)
        px_h = max(480, int(encuadre["px_h"]) * 2)
        tmp = Path(tempfile.gettempdir()) / "autodxf_weld_vista.bmp"
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        try:
            self.view.SaveAsBitmap(str(tmp), px_w, px_h)
        except Exception:
            self.view.Camera.SaveAsBitmap(str(tmp), px_w, px_h, blanco, blanco)
        imagen = Image.open(tmp).convert("RGB")
        imagen.load()
        try:
            tmp.unlink()
        except OSError:
            pass
        if encuadre.get("flip_x"):
            imagen = imagen.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        return imagen


def _frente(junta: dict, centro_tanque) -> dict:
    """La foto usa el mismo marco que el círculo: +u a la derecha, +v hacia arriba."""
    frame = junta["frame"]
    normal = _afuera(frame, centro_tanque)
    u = _unit(frame.get("u") or (1.0, 0.0, 0.0)) or (1.0, 0.0, 0.0)
    v = _unit(frame.get("v") or (0.0, 1.0, 0.0)) or (0.0, 1.0, 0.0)
    vista = (-normal[0], -normal[1], -normal[2])
    v = _unit(_resta(v, _escala(vista, _dot(v, vista)))) or v
    u = _unit(_resta(u, _escala(vista, _dot(u, vista)))) or u
    derecha = _cross(vista, v)
    outline = junta.get("outline") or []
    xs = [float(p[0]) for p in outline]
    ys = [float(p[1]) for p in outline]
    ancho = max(max(xs) - min(xs), 10.0) / 10.0
    alto = max(max(ys) - min(ys), 10.0) / 10.0
    destino = _mundo(frame, (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
    from weld_jpg import MARGEN_FOTO

    encuadre = _encuadre(destino, normal, v, ancho * MARGEN_FOTO, alto * MARGEN_FOTO, 980)
    encuadre["flip_x"] = _dot(derecha, u) < 0
    return encuadre


def _iso(junta: dict, centro_tanque, *, cerrado: bool) -> dict:
    frame = junta["frame"]
    normal = _afuera(frame, centro_tanque)
    u = frame["u"]
    v = frame["v"]
    cordon = _centro_cordon(junta)
    if junta.get("kind") == "hermetico":
        huella = (junta.get("weld") or {}).get("footprint") or (0, 0, 0, 0)
        destino = cordon or _mundo(frame, (huella[0] + huella[2]) / 2, (huella[1] + huella[3]) / 2)
        lado = 14.0 if cerrado else 58.0
    else:
        destino = cordon or junta.get("centro") or _mundo(frame, 0, 0)
        lado = 14.0 if cerrado else _lado_pieza(junta.get("caja"), False)
    if cerrado:
        mira = _suma(normal, _escala(u, 0.95), _escala(v, 0.35))
    else:
        mira = _suma(normal, _escala(u, 0.55), _escala(v, 0.85))
    return _encuadre(destino, mira, v, lado, lado, 720)


def _arriba_de_frente(frame, normal):
    """En pantalla: Y del mundo hacia arriba, el canto de la placa a plomo o a nivel."""
    mundo = (0.0, 1.0, 0.0)
    if abs(_dot(mundo, normal)) > 0.85:
        mundo = frame.get("u") or (1.0, 0.0, 0.0)
    proyectado = _unit(_resta(mundo, _escala(normal, _dot(mundo, normal))))
    return proyectado or frame.get("v") or mundo


def _material(occs) -> list:
    from inventor_session import _clear_appearance

    previos = []
    for occ in occs:
        try:
            fuente = int(occ.AppearanceSourceType)
        except Exception:
            fuente = None
        try:
            aspecto = occ.Appearance
        except Exception:
            aspecto = None
        previos.append((occ, fuente, aspecto))
        _clear_appearance(occ)
    return previos


def _restaurar_material(previos) -> None:
    for occ, fuente, aspecto in previos or []:
        try:
            if fuente == 100609 and aspecto is not None:
                occ.AppearanceSourceType = 100609
                occ.Appearance = aspecto
            else:
                occ.AppearanceSourceType = 100612
        except Exception:
            continue


def _fondo_blanco(inv):
    try:
        esquema = inv.ActiveColorScheme
        tipo = int(inv.ColorSchemes.BackgroundType)
        arriba = (int(esquema.TopColor.Red), int(esquema.TopColor.Green), int(esquema.TopColor.Blue))
        abajo = (int(esquema.BottomColor.Red), int(esquema.BottomColor.Green), int(esquema.BottomColor.Blue))
        blanco = inv.TransientObjects.CreateColor(255, 255, 255)
        inv.ColorSchemes.BackgroundType = 26371
        esquema.TopColor = blanco
        esquema.BottomColor = blanco
        return {"tipo": tipo, "arriba": arriba, "abajo": abajo}
    except Exception:
        return None


def _restaurar_fondo(inv, fondo) -> None:
    if not fondo:
        return
    try:
        esquema = inv.ActiveColorScheme
        inv.ColorSchemes.BackgroundType = int(fondo["tipo"])
        esquema.TopColor = inv.TransientObjects.CreateColor(*fondo["arriba"])
        esquema.BottomColor = inv.TransientObjects.CreateColor(*fondo["abajo"])
    except Exception:
        pass


def _centro_cordon(junta: dict):
    from weld_juntas import cordones

    piezas = cordones(junta)
    if not piezas:
        return None
    pieza = piezas[0]
    if pieza.get("forma") == "anillo":
        return pieza.get("centro")
    direccion = pieza.get("direccion")
    esquina = pieza.get("esquina")
    if direccion is None or esquina is None:
        return pieza.get("centro")
    mitad = float(pieza.get("largo") or 0) / 2.0
    return (
        esquina[0] + direccion[0] * mitad,
        esquina[1] + direccion[1] * mitad,
        esquina[2] + direccion[2] * mitad,
    )


def _lado_pieza(caja, cerrado: bool) -> float:
    if not caja:
        return 22.0 if cerrado else 48.0
    tramos = [abs(float(caja[1][eje]) - float(caja[0][eje])) / 10.0 for eje in range(3)]
    largo = max(tramos) if tramos else 20.0
    if cerrado:
        return min(max(largo * 0.42, 14.0), 36.0)
    return min(max(largo * 1.25, 18.0), 90.0)


def _encuadre(destino_mm, mira, arriba, ancho_cm, alto_cm, px_w: int) -> dict:
    look = _unit(mira) or (0.0, 0.0, 1.0)
    up = _unit(arriba) or (0.0, 1.0, 0.0)
    lateral = _dot(up, look)
    up = _unit(_resta(up, (look[0] * lateral, look[1] * lateral, look[2] * lateral))) or up
    ancho = max(float(ancho_cm), 4.0)
    alto = max(float(alto_cm), 4.0)
    return {
        "origin": (float(destino_mm[0]) / 10.0, float(destino_mm[1]) / 10.0, float(destino_mm[2]) / 10.0),
        "look": look,
        "up": up,
        "w": ancho,
        "h": alto,
        "px_w": px_w,
        "px_h": max(280, int(round(px_w * alto / ancho))),
    }


def _afuera(frame: dict, centro_tanque):
    normal = frame["normal"]
    if not centro_tanque or not frame.get("origen"):
        return normal
    delta = _resta(frame["origen"], centro_tanque)
    if _dot(normal, delta) < 0:
        return (-normal[0], -normal[1], -normal[2])
    return normal


def _mundo(frame: dict, u: float, v: float):
    origen = frame["origen"]
    uu = frame["u"]
    vv = frame["v"]
    return (
        origen[0] + uu[0] * u + vv[0] * v,
        origen[1] + uu[1] * u + vv[1] * v,
        origen[2] + uu[2] * u + vv[2] * v,
    )


def _suma(*vectores):
    return tuple(sum(vector[eje] for vector in vectores) for eje in range(3))


def _escala(vector, factor: float):
    return (vector[0] * factor, vector[1] * factor, vector[2] * factor)


def _resta(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _unit(vector):
    norma = math.sqrt(_dot(vector, vector))
    if norma < 1e-9:
        return None
    return (vector[0] / norma, vector[1] / norma, vector[2] / norma)
