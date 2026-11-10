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
        padres = []
        previos = []
        resalte = None
        try:
            resalte = _apagar_resalte(self.inv)
            _soltar_seleccion(self.assembly)
            for occ in keep:
                for hoja in _hojas_de(occ):
                    _ver(hoja, shown, padres)
            if not shown:
                return None
            previos = _material(shown, self.inv, self.assembly)
            if self.cordon is not None:
                try:
                    self.cordon.mostrar(str(junta.get("id") or ""))
                except Exception:
                    pass
            _pintar(shown, self.inv, self.assembly)
            _soltar_seleccion(self.assembly)
            self.view.Update()
            marco = _frente(junta, self.centro)
            frente = self._foto(marco)
            detalle = self._foto(_iso(junta, self.centro, cerrado=True))
            iso = self._foto(_iso(junta, self.centro, cerrado=False))
            return frente, detalle, iso, marco.get("ventana")
        finally:
            _restaurar_material(previos)
            _restaurar_resalte(self.inv, resalte)
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
            for occ in padres:
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
        ancho, alto, escala_u, escala_v = _ajustar_aspecto(
            float(encuadre["w"]),
            float(encuadre["h"]),
            self._aspecto_vista(),
        )
        encuadre["ventana"] = _ventana_uv(
            encuadre.get("uv"),
            escala_u,
            escala_v,
            invertir_u=bool(encuadre.get("u_a_la_izquierda")),
        )
        cam.SetExtents(ancho, alto)
        cam.ApplyWithoutTransition()
        self.view.Update()
        # Apply iguala el aspecto de la ventana. El alto de la placa se conserva
        # porque el ancho ya creció hasta ese aspecto.
        cam = self.view.Camera
        cam.UpVector = arriba
        cam.SetExtents(ancho, alto)
        _soltar_seleccion(self.assembly)
        blanco = self.inv.TransientObjects.CreateColor(255, 255, 255)
        px_w = max(640, int(encuadre["px_w"]) * 2)
        px_h = max(480, int(round(px_w * alto / max(ancho, 0.1))))
        tmp = Path(tempfile.gettempdir()) / "autodxf_weld_vista.bmp"
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        cam.SaveAsBitmap(str(tmp), px_w, px_h, blanco, blanco)
        imagen = Image.open(tmp).convert("RGB")
        imagen.load()
        try:
            tmp.unlink()
        except OSError:
            pass
        return imagen

    def _aspecto_vista(self) -> float:
        try:
            ancho = float(self.view.Width)
            alto = float(self.view.Height)
        except Exception:
            return 0.0
        if ancho < 1 or alto < 1:
            return 0.0
        return ancho / alto


def _frente(junta: dict, centro_tanque) -> dict:
    """La foto usa el mismo marco que el círculo: +u a la derecha, +v hacia arriba."""
    frame = junta["frame"]
    normal = _mira(junta, centro_tanque)
    u = _unit(frame.get("u") or (1.0, 0.0, 0.0)) or (1.0, 0.0, 0.0)
    v = _unit(frame.get("v") or (0.0, 1.0, 0.0)) or (0.0, 1.0, 0.0)
    vista = (-normal[0], -normal[1], -normal[2])
    v = _unit(_resta(v, _escala(vista, _dot(v, vista)))) or v
    u = _unit(_resta(u, _escala(vista, _dot(u, vista)))) or u
    derecha = _cross(vista, v)
    xs, ys = _uv_placa(junta, frame)
    ancho = max(max(xs) - min(xs), 10.0) / 10.0
    alto = max(max(ys) - min(ys), 10.0) / 10.0
    centro_u = (min(xs) + max(xs)) / 2
    centro_v = (min(ys) + max(ys)) / 2
    destino = _mundo(frame, centro_u, centro_v)
    from weld_jpg import MARGEN_FOTO

    encuadre = _encuadre(destino, normal, v, ancho * MARGEN_FOTO, alto * MARGEN_FOTO, 980)
    # No se espeja la foto: queda como la vista frontal de Inventor.
    # Si +u cae a la izquierda, la cota se dibuja de ese lado.
    encuadre["flip_x"] = False
    encuadre["u_a_la_izquierda"] = _dot(derecha, u) < 0
    encuadre["uv"] = (centro_u, centro_v, (max(xs) - min(xs)) * MARGEN_FOTO, (max(ys) - min(ys)) * MARGEN_FOTO)
    return encuadre


def _iso(junta: dict, centro_tanque, *, cerrado: bool) -> dict:
    frame = junta["frame"]
    normal = _mira(junta, centro_tanque)
    u = frame["u"]
    v = frame["v"]
    pieza = _primer_filete(junta)
    cordon = _centro_de(pieza)
    esquina = _esquina_vertical(junta)
    if junta.get("kind") == "hermetico":
        huella = (junta.get("weld") or {}).get("footprint") or (0, 0, 0, 0)
        destino = cordon or _mundo(frame, (huella[0] + huella[2]) / 2, (huella[1] + huella[3]) / 2)
        lado = (42.0 if cerrado else 78.0) if esquina else (14.0 if cerrado else 58.0)
    else:
        destino = cordon or junta.get("centro") or _mundo(frame, 0, 0)
        lado = 14.0 if cerrado else _lado_pieza(junta.get("caja"), False)
    # La cara azul mira a un solo lado del canto. Seguir el centro de la huella
    # deja el ojo en el lado contrario y la placa tapa el filete.
    canto = _hacia_la_cara_azul(normal, pieza) if esquina else None
    if canto is None and esquina:
        canto = _hacia_el_borde(junta, frame, normal)
    if canto is None and esquina:
        canto = _canto_en_la_cara(normal, pieza)
    if canto is not None:
        mira = _suma(normal, canto, _escala(v, 0.45))
    elif cerrado:
        mira = _suma(normal, _escala(u, 0.95), _escala(v, 0.35))
    else:
        mira = _suma(normal, _escala(u, 0.55), _escala(v, 0.85))
    encuadre = _encuadre(destino, mira, v, lado, lado, 720)
    encuadre["flip_x"] = False
    encuadre["u_a_la_izquierda"] = _voltear(encuadre, frame)
    return encuadre


def _voltear(encuadre: dict, frame: dict) -> bool:
    """True si hay que espejar para que la derecha de la foto sea +u de la placa."""
    u = _unit(frame.get("u") or (1.0, 0.0, 0.0))
    if u is None:
        return False
    look = encuadre["look"]
    vista = (-look[0], -look[1], -look[2])
    u = _unit(_resta(u, _escala(vista, _dot(u, vista)))) or u
    derecha = _cross(vista, encuadre["up"])
    return _dot(derecha, u) < 0


def _arriba_de_frente(frame, normal):
    """En pantalla: Y del mundo hacia arriba, el canto de la placa a plomo o a nivel."""
    mundo = (0.0, 1.0, 0.0)
    if abs(_dot(mundo, normal)) > 0.85:
        mundo = frame.get("u") or (1.0, 0.0, 0.0)
    proyectado = _unit(_resta(mundo, _escala(normal, _dot(mundo, normal))))
    return proyectado or frame.get("v") or mundo


def _hojas_de(occ) -> list:
    """Un ensamble se muestra con sus piezas. La foto no se queda en el padre vacío."""
    hojas = []

    def walk(actual) -> None:
        try:
            if bool(actual.Suppressed):
                return
        except Exception:
            return
        try:
            ensamble = int(actual.DefinitionDocumentType) == 12291
        except Exception:
            ensamble = False
        if not ensamble:
            hojas.append(actual)
            return
        try:
            hijos = actual.SubOccurrences
            total = int(hijos.Count)
        except Exception:
            hojas.append(actual)
            return
        if total <= 0:
            hojas.append(actual)
            return
        for indice in range(1, total + 1):
            try:
                walk(hijos.Item(indice))
            except Exception:
                continue

    walk(occ)
    return hojas or [occ]


def _soltar_seleccion(assembly) -> None:
    """El verde de la foto es la pieza seleccionada. La cota no la lleva marcada."""
    for documento in (assembly,):
        try:
            documento.SelectSet.Clear()
        except Exception:
            pass
        try:
            conjuntos = documento.HighlightSets
            for indice in range(int(conjuntos.Count), 0, -1):
                conjuntos.Item(indice).Clear()
        except Exception:
            pass


def _apagar_resalte(inv):
    """Mientras se toma la foto, el color de selección es el mismo gris del tanque."""
    try:
        inv.CommandManager.StopActiveCommand()
    except Exception:
        pass
    try:
        inv.ActiveDocument.SelectSet.Clear()
    except Exception:
        pass
    guardado = []
    try:
        esquema = inv.ActiveColorScheme
        gris = inv.TransientObjects.CreateColor(188, 188, 188)
    except Exception:
        return guardado
    for nombre in ("PrimarySelectColor", "SecondarySelectColor", "HighlightColor"):
        try:
            color = getattr(esquema, nombre)
            guardado.append((nombre, (int(color.Red), int(color.Green), int(color.Blue))))
            setattr(esquema, nombre, gris)
        except Exception:
            continue
    return guardado


def _restaurar_resalte(inv, guardado) -> None:
    if not guardado:
        return
    try:
        esquema = inv.ActiveColorScheme
    except Exception:
        return
    for nombre, rgb in guardado:
        try:
            setattr(esquema, nombre, inv.TransientObjects.CreateColor(*rgb))
        except Exception:
            continue


def _pintar(occs, inv=None, assembly=None) -> None:
    from inventor_session import _clear_appearance, _set_appearance

    pintura = None
    if inv is not None and assembly is not None:
        try:
            from weld_solido import _apariencia

            pintura = _apariencia(inv, assembly, "TanqueNeutro", (188, 188, 188))
        except Exception:
            pintura = None
    for occ in occs:
        if pintura is not None:
            _set_appearance(occ, pintura)
        else:
            _clear_appearance(occ)


def _material(occs, inv=None, assembly=None) -> list:
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
    _pintar(occs, inv, assembly)
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


def _primer_filete(junta: dict):
    from weld_juntas import cordones

    piezas = cordones(junta)
    return piezas[0] if piezas else None


def _centro_cordon(junta: dict):
    return _centro_de(_primer_filete(junta))


def _centro_de(pieza):
    if not pieza:
        return None
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


def _ver(occ, shown: list, padres: list) -> None:
    """Muestra la pieza y los ensambles que la contienen. Si el padre está apagado, la hoja no sale."""
    cadena = []
    actual = occ
    while actual is not None and len(cadena) < 8:
        cadena.append(actual)
        try:
            actual = actual.ParentOccurrence
        except Exception:
            break
    for indice, nodo in enumerate(cadena):
        try:
            estaba = bool(nodo.Visible)
        except Exception:
            estaba = True
        try:
            nodo.Visible = True
        except Exception:
            continue
        if indice == 0:
            if nodo not in shown:
                shown.append(nodo)
        elif not estaba and nodo not in padres:
            padres.append(nodo)


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


def _ajustar_aspecto(ancho: float, alto: float, aspecto: float) -> tuple[float, float, float, float]:
    """Crece el lado corto hasta el aspecto de la ventana. El otro lado no se recorta."""
    if aspecto <= 0 or alto <= 0 or ancho <= 0:
        return ancho, alto, 1.0, 1.0
    actual = ancho / alto
    if actual < aspecto - 1e-6:
        return alto * aspecto, alto, aspecto / actual, 1.0
    if actual > aspecto + 1e-6:
        return ancho, ancho / aspecto, 1.0, actual / aspecto
    return ancho, alto, 1.0, 1.0


def _ventana_uv(uv, escala_u: float, escala_v: float, invertir_u: bool = False):
    if not uv:
        return None
    centro_u, centro_v, span_u, span_v = uv
    medio_u = float(span_u) * escala_u / 2.0
    medio_v = float(span_v) * escala_v / 2.0
    izquierda = float(centro_u) + medio_u if invertir_u else float(centro_u) - medio_u
    derecha = float(centro_u) - medio_u if invertir_u else float(centro_u) + medio_u
    return (
        izquierda,
        float(centro_v) - medio_v,
        derecha,
        float(centro_v) + medio_v,
    )


def _uv_placa(junta: dict, frame: dict) -> tuple[list[float], list[float]]:
    outline = junta.get("outline") or []
    xs = [float(p[0]) for p in outline]
    ys = [float(p[1]) for p in outline]
    for punto in _uv_caja(junta.get("host"), frame):
        xs.append(punto[0])
        ys.append(punto[1])
    otro = junta.get("otro")
    host = junta.get("host")
    for occ in junta.get("visibles") or []:
        if occ is None or occ is otro or occ is host:
            continue
        for punto in _uv_caja(occ, frame):
            xs.append(punto[0])
            ys.append(punto[1])
    if not xs or not ys:
        return [0.0, 10.0], [0.0, 10.0]
    return xs, ys


def _uv_caja(occ, frame: dict) -> list[tuple[float, float]]:
    if occ is None:
        return []
    try:
        caja = occ.RangeBox
        esquinas = (
            (float(caja.MinPoint.X), float(caja.MinPoint.Y), float(caja.MinPoint.Z)),
            (float(caja.MaxPoint.X), float(caja.MaxPoint.Y), float(caja.MaxPoint.Z)),
        )
    except Exception:
        return []
    origen = frame.get("origen")
    u = frame.get("u")
    v = frame.get("v")
    if not origen or not u or not v:
        return []
    puntos = []
    for x in (esquinas[0][0], esquinas[1][0]):
        for y in (esquinas[0][1], esquinas[1][1]):
            for z in (esquinas[0][2], esquinas[1][2]):
                delta = _resta((x * 10.0, y * 10.0, z * 10.0), origen)
                puntos.append((_dot(delta, u), _dot(delta, v)))
    return puntos


def _mira(junta: dict, centro_tanque):
    """El ojo queda en la cara que se acota, por fuera del tanque.

    Una pata del filete sale por la otra placa. Si la cámara la sigue,
    la foto deja de ser el segmento y el cordón azul queda detrás del canto.
    """
    frame = junta.get("frame") or {}
    if junta.get("kind") == "accesorio":
        lado = _hacia_pieza(frame, junta.get("centro"))
        if lado is not None:
            return lado
    return _afuera(frame, centro_tanque)


def _hacia_la_cara_azul(afuera, pieza):
    """Sobre la placa, hacia el cuadrante que mira la hipotenusa del filete."""
    if not pieza:
        return None
    a = _eje(pieza.get("normal"))
    b = _eje(pieza.get("lado"))
    if a is None or b is None:
        return None
    return _unit(_resta(_suma(a, b), _escala(afuera, _dot(_suma(a, b), afuera))))


def _hacia_el_borde(junta: dict, frame: dict, afuera):
    """Desde el centro de la placa hacia el canto del cordón, sobre esa cara."""
    outline = junta.get("outline") or []
    huella = (junta.get("weld") or {}).get("footprint")
    u = _unit(frame.get("u") or ())
    v = _unit(frame.get("v") or ())
    if u is None or v is None or len(outline) < 2 or not isinstance(huella, (list, tuple)) or len(huella) < 4:
        return None
    xs = [float(punto[0]) for punto in outline]
    ys = [float(punto[1]) for punto in outline]
    centro_u = (min(xs) + max(xs)) / 2.0
    centro_v = (min(ys) + max(ys)) / 2.0
    cu = (float(huella[0]) + float(huella[2])) / 2.0
    cv = (float(huella[1]) + float(huella[3])) / 2.0
    du = cu - centro_u
    dv = cv - centro_v
    span_u = max(max(xs) - min(xs), 1.0)
    span_v = max(max(ys) - min(ys), 1.0)
    if abs(du) < span_u * 0.08 and abs(dv) < span_v * 0.08:
        return None
    if abs(du) >= abs(dv):
        tangente = _escala(u, 1.0 if du > 0.0 else -1.0)
    else:
        tangente = _escala(v, 1.0 if dv > 0.0 else -1.0)
    return _unit(_resta(tangente, _escala(afuera, _dot(tangente, afuera))))


def _canto_en_la_cara(afuera, pieza):
    """La pata que corre sobre esta cara, hacia el canto. La otra pata es la placa de al lado."""
    if not pieza:
        return None
    mejor = None
    for clave in ("normal", "lado"):
        pata = _eje(pieza.get(clave))
        if pata is None:
            continue
        alineada = abs(_dot(pata, afuera))
        en_plano = _unit(_resta(pata, _escala(afuera, _dot(pata, afuera))))
        if en_plano is None:
            continue
        if mejor is None or alineada < mejor[0]:
            mejor = (alineada, en_plano)
    return None if mejor is None else mejor[1]


def _esquina_vertical(junta: dict) -> bool:
    if junta.get("kind") != "hermetico":
        return False
    ident = str(junta.get("id") or "").upper()
    cara = str(junta.get("cara") or "").upper()
    return cara.startswith("SEGM") and "BASE" not in ident and "TOP" not in ident


def _hacia_pieza(frame: dict, centro):
    normal = _unit(frame.get("normal") or (0.0, 0.0, 1.0))
    origen = frame.get("origen")
    if normal is None or not origen or not centro:
        return None
    if _dot(_resta(centro, origen), normal) >= 0:
        return normal
    return (-normal[0], -normal[1], -normal[2])


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


def _eje(valor):
    if not isinstance(valor, (list, tuple)) or len(valor) < 3:
        return None
    return _unit(valor)


def _unit(vector):
    norma = math.sqrt(_dot(vector, vector))
    if norma < 1e-9:
        return None
    return (vector[0] / norma, vector[1] / norma, vector[2] / norma)
