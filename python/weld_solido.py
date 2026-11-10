"""Cordones 3D en el ensamble abierto. No se guarda el archivo.

Cada filete es un prisma triangular del cateto: naranja en accesorio y azul
en el hermético. Las cotas van después, cuando estos sólidos ya se ven.
"""

from __future__ import annotations

_NUEVO_CUERPO = 20485
_POSITIVO = 20993
_NEGATIVO = 20994
_APARIENCIA = 2
_NARANJA = (230, 110, 15)
_AZUL = (15, 75, 190)
_MUROS = {"SEGM1", "SEGM2", "SEGM3", "SEGM4", "BASE", "TOP"}


def _nombre_invertido(nombre: str) -> str:
    """El filete de una esquina se creó con el otro muro adelante.

    La hoja ahora se llama SEGM4_SEGM1 y el sólido sigue siendo SEGM1_SEGM4.
    """
    partes = str(nombre or "").split("_")
    if len(partes) != 2:
        return ""
    a, b = partes
    if a in _MUROS and b in _MUROS and a != b:
        return f"{b}_{a}"
    return ""


class Cordones:
    def __init__(self, inv, assembly):
        self.inv = inv
        self.assembly = assembly
        self.part = None
        self.occ = None
        self._grupos: list[dict] = []
        self._sucio = bool(getattr(assembly, "Dirty", False))
        self._cuerpos: dict[str, object] = {}
        self._tono: dict[str, str] = {}
        self._asm_color: dict[str, object] = {}
        self.por_junta: dict[str, list[str]] = {}
        self.error = ""

    def construir(self, juntas: list[dict], colores: dict[str, str] | None = None) -> int:
        """colores: clasificación fijada a mano por junta; manda sobre la automática."""
        from weld_juntas import cordones

        colores = colores or {}
        piezas = []
        for junta in juntas:
            for pieza in cordones(junta):
                pieza["junta"] = str(junta.get("id") or "")
                piezas.append(pieza)
        if not piezas:
            return 0
        _quitar_anteriores(self.assembly)
        tg = self.inv.TransientGeometry
        grupos: dict[str, list] = {"accesorio": [], "hermetico": []}
        for pieza in piezas:
            elegido = colores.get(pieza["junta"]) or pieza.get("color")
            tono = "hermetico" if elegido == "hermetico" else "accesorio"
            self._tono[str(pieza["nombre"])] = tono
            grupos[tono].append(pieza)
        for tono, lista in grupos.items():
            if not lista:
                continue
            self._grupo(tg, tono, lista)
        if not self._cuerpos:
            self.cerrar()
            return 0
        return len(self._cuerpos)

    def _grupo(self, tg, tono: str, piezas: list) -> None:
        docs = self.inv.Documents
        plantilla = ""
        try:
            plantilla = str(self.inv.FileManager.GetTemplateFile(12290) or "")
        except Exception:
            plantilla = ""
        part = docs.Add(12290, plantilla, False)
        definicion = part.ComponentDefinition
        self.part = part
        self._ocultar_auxiliares()
        rgb = _AZUL if tono == "hermetico" else _NARANJA
        nombre = "WeldHermetico" if tono == "hermetico" else "WeldAccesorio"
        pintura = _apariencia(self.inv, part, nombre, rgb)
        self._asm_color[tono] = _apariencia(self.inv, self.assembly, nombre, rgb)
        for pieza in piezas:
            if pieza.get("forma") == "anillo":
                cuerpo, error = _anillo(self.inv, definicion, tg, pieza)
            else:
                cuerpo, error = _prisma(self.inv, definicion, tg, pieza)
            if error and not self.error:
                self.error = error
            if cuerpo is None:
                continue
            self._cuerpos[str(pieza["nombre"])] = cuerpo
            self.por_junta.setdefault(str(pieza.get("junta") or ""), []).append(_limpio(pieza["nombre"]))
            _pintar(cuerpo, pintura)
        try:
            part.Update()
        except Exception:
            pass
        if not any(self._tono.get(nombre_cuerpo) == tono for nombre_cuerpo in self._cuerpos):
            try:
                part.Close(True)
            except Exception:
                pass
            return
        occ = self.assembly.ComponentDefinition.Occurrences.AddByComponentDefinition(definicion, tg.CreateMatrix())
        try:
            occ.Name = "WELD_ANOTATION_AZUL" if tono == "hermetico" else "WELD_ANOTATION_NARANJA"
        except Exception:
            pass
        try:
            occ.Visible = True
        except Exception:
            pass
        self._grupos.append({"tono": tono, "part": part, "occ": occ})
        self.occ = occ

    def encuadrar(self) -> None:
        """Iso del ensamble para ver los filetes junto a las piezas."""
        cajas = []
        for grupo in self._grupos:
            try:
                cajas.append(grupo["occ"].RangeBox)
            except Exception:
                continue
        if not cajas:
            return
        minimo = [min(float(caja.MinPoint.X) for caja in cajas), min(float(caja.MinPoint.Y) for caja in cajas), min(float(caja.MinPoint.Z) for caja in cajas)]
        maximo = [max(float(caja.MaxPoint.X) for caja in cajas), max(float(caja.MaxPoint.Y) for caja in cajas), max(float(caja.MaxPoint.Z) for caja in cajas)]
        centro = tuple((minimo[eje] + maximo[eje]) / 2.0 for eje in range(3))
        tramo = max(maximo[eje] - minimo[eje] for eje in range(3))
        tramo = max(tramo, 20.0)
        vista = self.inv.ActiveView
        tg = self.inv.TransientGeometry
        camara = vista.Camera
        camara.Perspective = False
        camara.Target = tg.CreatePoint(*centro)
        camara.Eye = tg.CreatePoint(centro[0] + tramo, centro[1] + tramo * 0.7, centro[2] + tramo)
        camara.UpVector = tg.CreateUnitVector(0, 1, 0)
        camara.SetExtents(tramo * 1.6, tramo * 1.2)
        camara.ApplyWithoutTransition()
        try:
            vista.Fit()
        except Exception:
            pass
        vista.Update()

    def conteo(self, tono: str) -> int:
        return sum(1 for valor in self._tono.values() if valor == tono)

    def adoptar(self, ruta: str = "") -> int:
        """Usa los filetes que ya están en el ensamble. No los vuelve a construir."""
        try:
            ocurrencias = self.assembly.ComponentDefinition.Occurrences
            total = int(ocurrencias.Count)
        except Exception:
            return 0
        for indice in range(1, total + 1):
            try:
                occ = ocurrencias.Item(indice)
                nombre = str(occ.Name)
            except Exception:
                continue
            if not nombre.startswith("WELD_ANOTATION"):
                continue
            tono = "hermetico" if "AZUL" in nombre.upper() else "accesorio"
            try:
                part = occ.Definition.Document
            except Exception:
                part = None
            self._grupos.append({"tono": tono, "part": part, "occ": occ})
            self.occ = occ
            self.part = part
            try:
                cuerpos = occ.SurfaceBodies
                cantidad = int(cuerpos.Count)
            except Exception:
                continue
            for posicion in range(1, cantidad + 1):
                try:
                    cuerpo = cuerpos.Item(posicion)
                    clave = str(cuerpo.Name)
                except Exception:
                    continue
                self._cuerpos[clave] = cuerpo
                self._tono[clave] = tono
                self.por_junta.setdefault(clave, []).append(clave)
        if ruta:
            try:
                from weld_nomenclatura import listar

                for fila in listar(ruta).get("cordones") or []:
                    ident = str(fila.get("id") or "")
                    nombres = [str(nombre) for nombre in fila.get("cuerpos") or [] if nombre]
                    if ident and nombres:
                        self.por_junta[ident] = nombres
            except Exception:
                pass
        return len(self._cuerpos)

    def mostrar(self, nombre: str) -> None:
        claves = {str(nombre or "")}
        invertido = _nombre_invertido(nombre)
        if invertido:
            claves.add(invertido)
        for ident in (str(nombre or ""), invertido):
            for item in self.por_junta.get(ident) or []:
                claves.add(str(item))
        claves.discard("")

        def es_de(titulo: str) -> bool:
            return any(titulo == clave or titulo.startswith(clave + "_") for clave in claves if clave)

        for titulo, cuerpo in self._cuerpos.items():
            try:
                cuerpo.Visible = es_de(titulo)
            except Exception:
                pass
        for grupo in self._grupos:
            occ = grupo.get("occ")
            if occ is None:
                continue
            try:
                occ.Visible = True
            except Exception:
                pass
            try:
                copias = occ.SurfaceBodies
                for indice in range(1, int(copias.Count) + 1):
                    cuerpo = copias.Item(indice)
                    cuerpo.Visible = es_de(str(cuerpo.Name))
            except Exception:
                continue
            try:
                occ.AppearanceSourceType = 100612
            except Exception:
                pass

    def mostrar_todos(self) -> None:
        """La foto deja un solo cordón encendido. Al cerrar, vuelven todos."""
        for cuerpo in self._cuerpos.values():
            try:
                cuerpo.Visible = True
            except Exception:
                pass
        for grupo in self._grupos:
            occ = grupo.get("occ")
            if occ is None:
                continue
            try:
                occ.Visible = True
            except Exception:
                pass
            try:
                copias = occ.SurfaceBodies
                for indice in range(1, int(copias.Count) + 1):
                    copias.Item(indice).Visible = True
            except Exception:
                continue

    def cerrar(self) -> None:
        for grupo in list(self._grupos):
            try:
                grupo["occ"].Delete()
            except Exception:
                pass
            try:
                grupo["part"].Close(True)
            except Exception:
                pass
        self._grupos.clear()
        self.occ = None
        self.part = None
        if not self._sucio:
            try:
                self.assembly.Dirty = False
            except Exception:
                pass

    def _ocultar_auxiliares(self) -> None:
        for nombre, valor in (
            ("AllWorkFeatures", False),
            ("Sketches", False),
            ("ConstructionSurfaces", False),
            ("UserCoordinateSystems", False),
        ):
            try:
                setattr(self.part.ObjectVisibility, nombre, valor)
            except Exception:
                continue


def descolorear(inv, assembly) -> int:
    """Pinta el tanque de gris. El naranja y el azul del cordón se leen encima."""
    from inventor_session import _clear_appearance, _set_appearance

    pintura = _apariencia(inv, assembly, "TanqueNeutro", (188, 188, 188))
    hechos = 0
    for occ in _recorrer(assembly):
        try:
            if bool(occ.Suppressed):
                continue
            nombre = str(occ.Name)
        except Exception:
            continue
        if nombre.startswith("WELD_ANOTATION"):
            continue
        if pintura is not None and _set_appearance(occ, pintura):
            hechos += 1
            continue
        if _clear_appearance(occ):
            hechos += 1
    try:
        inv.ActiveView.Update()
    except Exception:
        pass
    return hechos


def _recorrer(assembly) -> list:
    salida: list = []

    def bajar(coleccion) -> None:
        try:
            total = int(coleccion.Count)
        except Exception:
            return
        for indice in range(1, total + 1):
            try:
                occ = coleccion.Item(indice)
            except Exception:
                continue
            salida.append(occ)
            try:
                bajar(occ.SubOccurrences)
            except Exception:
                continue

    try:
        bajar(assembly.ComponentDefinition.Occurrences)
    except Exception:
        return salida
    return salida


def _ocurrencias_de_cordon(assembly) -> list:
    """Los dos sólidos de soldadura, naranja y azul, en cualquier nivel del ensamble."""
    hallados = []
    vistos: set[int] = set()

    def tomar(occ) -> None:
        try:
            nombre = str(occ.Name or "")
        except Exception:
            return
        if "WELD_ANOTATION" not in nombre.upper():
            return
        marca = id(occ)
        if marca in vistos:
            return
        vistos.add(marca)
        hallados.append(occ)

    def bajar(ocurrencias) -> None:
        try:
            total = int(ocurrencias.Count)
        except Exception:
            return
        for indice in range(1, total + 1):
            try:
                occ = ocurrencias.Item(indice)
            except Exception:
                continue
            tomar(occ)
            try:
                if int(occ.DefinitionDocumentType) == 12291:
                    bajar(occ.SubOccurrences)
            except Exception:
                continue

    try:
        bajar(assembly.ComponentDefinition.Occurrences)
    except Exception:
        return hallados
    return hallados


def _quitar_anteriores(assembly) -> dict:
    """Saca naranja y azul juntos. No toca las piezas del tanque."""
    from inventor_session import _inventor

    viejos = _ocurrencias_de_cordon(assembly)
    if not viejos:
        return {"borrados": 0, "quedan": 0}
    inv = _inventor()
    pantalla = True
    try:
        pantalla = bool(inv.ScreenUpdating)
        inv.ScreenUpdating = False
    except Exception:
        pantalla = True
    documentos = []
    for occ in viejos:
        try:
            documentos.append(occ.Definition.Document)
        except Exception:
            pass
        try:
            occ.Grounded = False
        except Exception:
            pass
    try:
        coleccion = inv.TransientObjects.CreateObjectCollection()
        for occ in viejos:
            coleccion.Add(occ)
        assembly.ComponentDefinition.DeleteObjects(coleccion, False)
    except Exception:
        for _ in range(len(viejos)):
            pendientes = _ocurrencias_de_cordon(assembly)
            if not pendientes:
                break
            try:
                pendientes[-1].Delete()
            except Exception:
                break
    for documento in documentos:
        try:
            documento.Close(True)
        except Exception:
            pass
    try:
        assembly.Update()
    except Exception:
        pass
    try:
        inv.ScreenUpdating = pantalla
        inv.ActiveView.Update()
    except Exception:
        pass
    quedan = len(_ocurrencias_de_cordon(assembly))
    return {"borrados": max(0, len(viejos) - quedan), "quedan": quedan}


def _anillo(inv, definicion, tg, pieza) -> tuple[object | None, str]:
    """Filete de revolución: la esquina recta recorre el círculo de la brida."""
    centro = _cm(pieza["centro"])
    eje = _unidad(pieza["normal"])
    radio = float(pieza["radio"]) / 10.0
    cateto = max(float(pieza["cateto"]) / 10.0, 0.08)
    if eje is None or radio < 0.3:
        return None, "anillo corto"
    radial = _perpendicular(eje)
    if radial is None:
        return None, "anillo sin radio"
    try:
        origen = _punto(tg, centro)
        eje_x = tg.CreateUnitVector(float(radial[0]), float(radial[1]), float(radial[2]))
        eje_y = tg.CreateUnitVector(float(eje[0]), float(eje[1]), float(eje[2]))
        plano = definicion.WorkPlanes.AddFixed(origen, eje_x, eje_y, False)
        plano.Visible = False
        boceto = definicion.Sketches.Add(plano)
        boceto.Visible = False
        p0 = boceto.SketchPoints.Add(tg.CreatePoint2d(radio, 0.0), False)
        pata = boceto.SketchPoints.Add(tg.CreatePoint2d(radio + cateto, 0.0), False)
        altura = boceto.SketchPoints.Add(tg.CreatePoint2d(radio, cateto), False)
        boceto.SketchLines.AddByTwoPoints(p0, pata)
        boceto.SketchLines.AddByTwoPoints(pata, altura)
        boceto.SketchLines.AddByTwoPoints(altura, p0)
        a0 = boceto.SketchPoints.Add(tg.CreatePoint2d(0.0, -0.2), False)
        a1 = boceto.SketchPoints.Add(tg.CreatePoint2d(0.0, cateto + 0.4), False)
        linea = boceto.SketchLines.AddByTwoPoints(a0, a1)
        linea.Construction = True
        perfil = boceto.Profiles.AddForSolid()
        solido = definicion.Features.RevolveFeatures.AddFull(perfil, linea, _NUEVO_CUERPO)
        cuerpo = solido.SurfaceBodies.Item(1)
        cuerpo.Name = _limpio(pieza["nombre"])
        return cuerpo, ""
    except Exception as ex:
        return None, f"anillo {pieza.get('nombre')}: {type(ex).__name__}: {ex}"


def _perpendicular(eje):
    apoyo = (0.0, 0.0, 1.0) if abs(float(eje[2])) < 0.9 else (1.0, 0.0, 0.0)
    cruz = (
        eje[1] * apoyo[2] - eje[2] * apoyo[1],
        eje[2] * apoyo[0] - eje[0] * apoyo[2],
        eje[0] * apoyo[1] - eje[1] * apoyo[0],
    )
    return _unidad(cruz)


def _prisma(inv, definicion, tg, pieza) -> tuple[object | None, str]:
    """Prisma de sección triangular. La esquina recta va sobre la arista de contacto."""
    esquina = _cm(pieza["esquina"])
    largo = float(pieza["largo"]) / 10.0
    cateto = max(float(pieza["cateto"]) / 10.0, 0.08)
    if largo < 0.4:
        return None, "tramo corto"
    ejes = _base_ortonormal(pieza["lado"], pieza["normal"])
    if ejes is None:
        return None, "ejes degenerados"
    lado, normal = ejes
    direccion = pieza["direccion"]
    try:
        origen = _punto(tg, esquina)
        eje_x = tg.CreateUnitVector(float(lado[0]), float(lado[1]), float(lado[2]))
        eje_y = tg.CreateUnitVector(float(normal[0]), float(normal[1]), float(normal[2]))
        plano = definicion.WorkPlanes.AddFixed(origen, eje_x, eje_y, False)
        plano.Visible = False
        boceto = definicion.Sketches.Add(plano)
        boceto.Visible = False
        p0 = boceto.SketchPoints.Add(tg.CreatePoint2d(0.0, 0.0), False)
        pata = boceto.SketchPoints.Add(tg.CreatePoint2d(cateto, 0.0), False)
        altura = boceto.SketchPoints.Add(tg.CreatePoint2d(0.0, cateto), False)
        boceto.SketchLines.AddByTwoPoints(p0, pata)
        boceto.SketchLines.AddByTwoPoints(pata, altura)
        boceto.SketchLines.AddByTwoPoints(altura, p0)
        perfil = boceto.Profiles.AddForSolid()
        sentido = _POSITIVO if _mismo_sentido(lado, normal, direccion) else _NEGATIVO
        extrude = definicion.Features.ExtrudeFeatures.AddByDistanceExtent(perfil, largo, sentido, _NUEVO_CUERPO)
        cuerpo = extrude.SurfaceBodies.Item(1)
        cuerpo.Name = _limpio(pieza["nombre"])
        return cuerpo, ""
    except Exception as ex:
        return None, f"prisma {pieza.get('nombre')}: {type(ex).__name__}: {ex}"


def _base_ortonormal(lado, normal):
    """X sobre la placa, saliendo de la pieza. Y hacia la pieza, perpendicular a X."""
    eje_x = _unidad(lado)
    eje_n = _unidad(normal)
    if eje_x is None or eje_n is None:
        return None
    proyeccion = eje_x[0] * eje_n[0] + eje_x[1] * eje_n[1] + eje_x[2] * eje_n[2]
    eje_y = (
        eje_n[0] - eje_x[0] * proyeccion,
        eje_n[1] - eje_x[1] * proyeccion,
        eje_n[2] - eje_x[2] * proyeccion,
    )
    eje_y = _unidad(eje_y)
    if eje_y is None:
        return None
    return eje_x, eje_y


def _unidad(vector):
    largo = (float(vector[0]) ** 2 + float(vector[1]) ** 2 + float(vector[2]) ** 2) ** 0.5
    if largo < 1e-9:
        return None
    return (float(vector[0]) / largo, float(vector[1]) / largo, float(vector[2]) / largo)


def _apariencia(inv, part, nombre, rgb):
    """Color opaco. El naranja de biblioteca es pintura translúcida y no se lee como soldadura."""
    try:
        asset = part.Assets.Item(nombre)
    except Exception:
        asset = None
    if asset is None:
        origen = _generico(inv)
        if origen is None:
            return None
        try:
            asset = origen.CopyTo(part, True)
        except Exception:
            return None
        try:
            asset.DisplayName = nombre
        except Exception:
            pass
    color = inv.TransientObjects.CreateColor(int(rgb[0]), int(rgb[1]), int(rgb[2]))
    _valor(asset, "generic_diffuse", color)
    _valor(asset, "generic_transparency", 0.0)
    _valor(asset, "generic_refraction_translucency_weight", 0.0)
    _valor(asset, "generic_cutout_opacity", 1.0)
    _valor(asset, "generic_reflectivity_at_0deg", 0.03)
    _valor(asset, "generic_reflectivity_at_90deg", 0.06)
    return asset


def _generico(inv):
    try:
        biblioteca = inv.AssetLibraries.Item("Autodesk Biblioteca de aspecto").AppearanceAssets
        total = int(biblioteca.Count)
    except Exception:
        return None
    for indice in range(1, total + 1):
        try:
            asset = biblioteca.Item(indice)
        except Exception:
            continue
        if str(getattr(asset, "DisplayName", "") or "") == "Genérico":
            return asset
    return None


def _valor(asset, clave, valor) -> None:
    import win32com.client

    try:
        item = win32com.client.dynamic.Dispatch(asset.Item(clave))
        item.Value = valor
    except Exception:
        pass


def _pintar(cuerpo, asset) -> None:
    if asset is None or cuerpo is None:
        return
    try:
        cuerpo.Appearance = asset
    except Exception:
        pass
    try:
        caras = cuerpo.Faces
        for indice in range(1, int(caras.Count) + 1):
            try:
                caras.Item(indice).Appearance = asset
            except Exception:
                continue
    except Exception:
        pass


def _limpio(nombre: str) -> str:
    texto = "".join(caracter if caracter.isalnum() or caracter in "._-" else "_" for caracter in str(nombre))
    return (texto or "CORDON")[:80]


def _mismo_sentido(lado, normal, direccion) -> bool:
    cruz = (
        lado[1] * normal[2] - lado[2] * normal[1],
        lado[2] * normal[0] - lado[0] * normal[2],
        lado[0] * normal[1] - lado[1] * normal[0],
    )
    return cruz[0] * direccion[0] + cruz[1] * direccion[1] + cruz[2] * direccion[2] >= 0


def _cm(punto):
    return (float(punto[0]) / 10.0, float(punto[1]) / 10.0, float(punto[2]) / 10.0)


def _punto(tg, xyz):
    return tg.CreatePoint(float(xyz[0]), float(xyz[1]), float(xyz[2]))


def _por(vector, factor):
    return (float(vector[0]) * factor, float(vector[1]) * factor, float(vector[2]) * factor)


def _suma(*vectores):
    return tuple(sum(vector[eje] for vector in vectores) for eje in range(3))
