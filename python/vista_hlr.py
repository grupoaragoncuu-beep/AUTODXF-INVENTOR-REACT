"""Vista alambrica desde Inventor (Wireframe sin ocultas), no malla."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps

WIREFRAME_NO_HIDDEN = 8711
WHITE = (255, 255, 255)


def capturar_alambrico(
    *,
    inv,
    active_asm,
    scene_doc,
    cara: str,
    keep_nombres: list,
    keep_rutas: list,
    origin,
    look,
    v_axis,
    width_cm: float,
    height_cm: float,
    dest: Path,
    scale: float = 0.3937,
    tank_c=None,
) -> Image.Image:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tg = inv.TransientGeometry
    display = inv.DisplayOptions
    tank_view = inv.ActiveView
    tank_cam = tank_view.Camera
    tank_state = _estado_vista(tank_view, tank_cam, display)
    saved_vis: list[tuple] = []
    activated = False
    try:
        scene_path = _path(scene_doc)
        active_path = _path(active_asm)
        view_doc = active_asm
        if scene_path and scene_path != active_path:
            scene_doc.Activate()
            activated = True
            view_doc = scene_doc
        saved_vis = _ocultar_otras_caras(view_doc, cara)
        n_iam = len(saved_vis)
        saved_vis.extend(
            _ocultar_lado_opuesto(view_doc, origin, look, scale, cara=cara, tank_c=tank_c)
        )
        print(
            f"{_resumen_aislar(saved_vis)} (iam {n_iam}, plano {len(saved_vis) - n_iam})",
            flush=True,
        )
        view = inv.ActiveView
        cam = view.Camera
        try:
            display.Show3DIndicator = False
        except Exception:
            pass
        _apagar_sombras(view)
        view.DisplayMode = WIREFRAME_NO_HIDDEN
        _apuntar(inv, cam, origin, look, v_axis, width_cm, height_cm)
        cam.ApplyWithoutTransition()
        view.Update()
        return _guardar(inv, cam, dest, width_cm, height_cm)
    finally:
        _restaurar_vis(saved_vis)
        if activated:
            try:
                active_asm.Activate()
            except Exception:
                pass
        try:
            _restaurar_vista(inv, inv.ActiveView, tg, display, tank_state)
        except Exception:
            try:
                inv.ActiveView.Update()
            except Exception:
                pass


def _estado_vista(view, cam, display) -> dict:
    flags = {}
    for name in (
        "ShowAmbientShadows",
        "ShowObjectShadows",
        "ShowGroundShadows",
        "ShowGroundPlane",
        "ShowGroundReflections",
        "AreTexturesOn",
        "RayTracing",
    ):
        try:
            flags[name] = bool(getattr(view, name))
        except Exception:
            pass
    return {
        "mode": int(view.DisplayMode),
        "eye": (float(cam.Eye.X), float(cam.Eye.Y), float(cam.Eye.Z)),
        "tgt": (float(cam.Target.X), float(cam.Target.Y), float(cam.Target.Z)),
        "up": (float(cam.UpVector.X), float(cam.UpVector.Y), float(cam.UpVector.Z)),
        "persp": bool(cam.Perspective),
        "ext": _extents(cam),
        "triad": bool(getattr(display, "Show3DIndicator", True)),
        "flags": flags,
    }


def _apagar_sombras(view) -> None:
    for name, value in (
        ("ShowAmbientShadows", False),
        ("ShowObjectShadows", False),
        ("ShowGroundShadows", False),
        ("ShowGroundPlane", False),
        ("ShowGroundReflections", False),
        ("AreTexturesOn", False),
        ("RayTracing", False),
    ):
        try:
            setattr(view, name, value)
        except Exception:
            pass


def _restaurar_vista(inv, view, tg, display, state: dict) -> None:
    cam = view.Camera
    try:
        display.Show3DIndicator = state["triad"]
    except Exception:
        pass
    view.DisplayMode = state["mode"]
    for name, value in (state.get("flags") or {}).items():
        try:
            setattr(view, name, value)
        except Exception:
            pass
    cam.Perspective = state["persp"]
    cam.Target = tg.CreatePoint(*state["tgt"])
    cam.Eye = tg.CreatePoint(*state["eye"])
    try:
        cam.UpVector = tg.CreateUnitVector(*state["up"])
    except Exception:
        cam.UpVector = tg.CreateVector(*state["up"])
    if state.get("ext") is not None:
        cam.SetExtents(float(state["ext"][0]), float(state["ext"][1]))
    cam.ApplyWithoutTransition()
    view.Update()


def _apuntar(inv, cam, origin, look, v_axis, width_cm, height_cm) -> None:
    tg = inv.TransientGeometry
    dist = max(float(width_cm), float(height_cm), 10.0) * 2.5
    cam.Perspective = False
    cam.Target = tg.CreatePoint(float(origin[0]), float(origin[1]), float(origin[2]))
    cam.Eye = tg.CreatePoint(
        float(origin[0] + look[0] * dist),
        float(origin[1] + look[1] * dist),
        float(origin[2] + look[2] * dist),
    )
    try:
        cam.UpVector = tg.CreateUnitVector(float(v_axis[0]), float(v_axis[1]), float(v_axis[2]))
    except Exception:
        cam.UpVector = tg.CreateVector(float(v_axis[0]), float(v_axis[1]), float(v_axis[2]))
    cam.SetExtents(float(width_cm), float(height_cm))


def _guardar(inv, cam, dest: Path, width_cm: float, height_cm: float) -> Image.Image:
    w_px = 1600
    h_px = max(480, int(round(1600 * float(height_cm) / max(float(width_cm), 0.1))))
    white = inv.TransientObjects.CreateColor(255, 255, 255)
    tmp = dest.with_suffix(".bmp")
    cam.SaveAsBitmap(str(tmp), w_px, h_px, white, white)
    img = Image.open(tmp).convert("RGB")
    try:
        tmp.unlink(missing_ok=True)
    except OSError:
        pass
    return _lineas_negras(img)


_CARAS = {
    "TOP": ("top cover", "tapa superior", "tank lid", "tank-lid", "segm top"),
    "SEGM1": ("segmento 1", "segmento #1", "segm1", "s1"),
    "SEGM2": ("segmento 2", "segmento #2", "segm2", "s2"),
    "SEGM3": ("segmento 3", "segmento #3", "segm3", "s3"),
    "SEGM4": ("segmento 4", "segmento #4", "segm4", "s4"),
    "BASE": ("base de soleras", "cuadro base", "base plate", "tank base", "tank-base"),
}


def _ocultar_lado_opuesto(doc, origin, look, scale: float, cara: str = "", tank_c=None) -> list[tuple]:
    """Oculta hojas detrás de esta placa o cuyo muro más cercano no es esta cara."""
    saved: list[tuple] = []
    if origin is None or look is None:
        return saved
    anclas = _anclas_iam(doc, tank_c)
    cara = str(cara or "").upper()
    lim_in = -12.0
    try:
        occs = doc.ComponentDefinition.Occurrences.AllLeafOccurrences
        total = int(occs.Count)
    except Exception:
        return saved
    ox, oy, oz = float(origin[0]), float(origin[1]), float(origin[2])
    lx, ly, lz = float(look[0]), float(look[1]), float(look[2])
    k = float(scale) if scale else 0.3937
    for index in range(1, total + 1):
        try:
            occ = occs.Item(index)
            if bool(occ.Suppressed):
                continue
            vis = bool(occ.Visible)
            if not vis:
                continue
            rb = occ.RangeBox
            cx = 0.5 * (float(rb.MinPoint.X) + float(rb.MaxPoint.X))
            cy = 0.5 * (float(rb.MinPoint.Y) + float(rb.MaxPoint.Y))
            cz = 0.5 * (float(rb.MinPoint.Z) + float(rb.MaxPoint.Z))
            d_in = ((cx - ox) * lx + (cy - oy) * ly + (cz - oz) * lz) * k
        except Exception:
            continue
        otro_muro = False
        if cara and anclas:
            muro = _muro_de_punto_hlr((cx, cy, cz), anclas)
            otro_muro = bool(muro) and muro != cara
        if d_in >= lim_in and not otro_muro:
            continue
        saved.append((occ, vis))
        try:
            occ.Visible = False
        except Exception:
            pass
    return saved


def _anclas_iam(doc, tank_c) -> dict:
    geo: dict = {}

    def walk(occs) -> None:
        try:
            total = int(occs.Count)
        except Exception:
            return
        for index in range(1, total + 1):
            try:
                occ = occs.Item(index)
                if bool(occ.Suppressed):
                    continue
                otra = _cara_occ(occ)
            except Exception:
                continue
            if otra and otra not in geo:
                try:
                    rb = occ.RangeBox
                    c = (
                        0.5 * (float(rb.MinPoint.X) + float(rb.MaxPoint.X)),
                        0.5 * (float(rb.MinPoint.Y) + float(rb.MaxPoint.Y)),
                        0.5 * (float(rb.MinPoint.Z) + float(rb.MaxPoint.Z)),
                    )
                    corners = [
                        (float(x), float(y), float(z))
                        for x in (rb.MinPoint.X, rb.MaxPoint.X)
                        for y in (rb.MinPoint.Y, rb.MaxPoint.Y)
                        for z in (rb.MinPoint.Z, rb.MaxPoint.Z)
                    ]
                except Exception:
                    continue
                geo[otra] = {"c": c, "corners": corners}
                continue
            try:
                walk(occ.SubOccurrences)
            except Exception:
                pass

    try:
        walk(doc.ComponentDefinition.Occurrences)
    except Exception:
        return {}
    if tank_c is None and geo:
        tank_c = (
            sum(g["c"][0] for g in geo.values()) / len(geo),
            sum(g["c"][1] for g in geo.values()) / len(geo),
            sum(g["c"][2] for g in geo.values()) / len(geo),
        )
    for g in geo.values():
        c = g["c"]
        n = _norm3(
            (
                c[0] - float(tank_c[0]),
                c[1] - float(tank_c[1]),
                c[2] - float(tank_c[2]),
            )
        )
        g["n"] = n
        v = _norm3((0.0 - n[0] * n[1], 1.0 - n[1] * n[1], 0.0 - n[2] * n[1]))
        if v[0] * v[0] + v[1] * v[1] + v[2] * v[2] < 0.25:
            v = _norm3((1.0 - n[0] * n[0], 0.0 - n[1] * n[0], 0.0 - n[2] * n[0]))
        u = _norm3(
            (
                v[1] * n[2] - v[2] * n[1],
                v[2] * n[0] - v[0] * n[2],
                v[0] * n[1] - v[1] * n[0],
            )
        )
        us = [
            (p[0] - c[0]) * u[0] + (p[1] - c[1]) * u[1] + (p[2] - c[2]) * u[2]
            for p in g["corners"]
        ]
        vs = [
            (p[0] - c[0]) * v[0] + (p[1] - c[1]) * v[1] + (p[2] - c[2]) * v[2]
            for p in g["corners"]
        ]
        g["u"] = u
        g["v"] = v
        g["umin"] = min(us)
        g["umax"] = max(us)
        g["vmin"] = min(vs)
        g["vmax"] = max(vs)
    return geo


def _muro_de_punto_hlr(c, anclas: dict) -> str:
    mejor, mejor_s = "", None
    for cara, a in (anclas or {}).items():
        ac = a.get("c")
        n = a.get("n")
        if ac is None or n is None:
            continue
        d = abs(
            (c[0] - ac[0]) * n[0] + (c[1] - ac[1]) * n[1] + (c[2] - ac[2]) * n[2]
        )
        penal = 0.0
        if a.get("u") is not None and "umin" in a:
            uu = (c[0] - ac[0]) * a["u"][0] + (c[1] - ac[1]) * a["u"][1] + (c[2] - ac[2]) * a["u"][2]
            vv = (c[0] - ac[0]) * a["v"][0] + (c[1] - ac[1]) * a["v"][1] + (c[2] - ac[2]) * a["v"][2]
            penal = (
                max(0.0, a["umin"] - uu, uu - a["umax"])
                + max(0.0, a["vmin"] - vv, vv - a["vmax"])
            ) * 3.0
        s = d + penal
        if mejor_s is None or s < mejor_s:
            mejor, mejor_s = str(cara).upper(), s
    return mejor


def _norm3(a):
    mag = (a[0] * a[0] + a[1] * a[1] + a[2] * a[2]) ** 0.5 or 1.0
    return (a[0] / mag, a[1] / mag, a[2] / mag)


def _ocultar_otras_caras(doc, cara: str) -> list[tuple]:
    """Oculta ensambles TOP/SEGM/BASE que no sean esta cara. No toca los hijos de este muro."""
    saved: list[tuple] = []
    cara = str(cara or "").upper()

    def walk(occs) -> None:
        try:
            total = int(occs.Count)
        except Exception:
            return
        for index in range(1, total + 1):
            try:
                occ = occs.Item(index)
                if bool(occ.Suppressed):
                    continue
                vis = bool(occ.Visible)
            except Exception:
                continue
            otra = _cara_occ(occ)
            if otra and otra != cara:
                saved.append((occ, vis))
                if vis:
                    try:
                        occ.Visible = False
                    except Exception:
                        pass
                continue
            try:
                walk(occ.SubOccurrences)
            except Exception:
                pass

    try:
        walk(doc.ComponentDefinition.Occurrences)
    except Exception as ex:
        print(f"aislar fail: {ex}", flush=True)
    return saved


def _cara_occ(occ) -> str:
    try:
        nombre = str(occ.Name)
        archivo = Path(str(occ.Definition.Document.FullFileName or "")).stem
    except Exception:
        return ""
    texto = f"{nombre} {archivo}".replace("_", " ").replace("-", " ").lower()
    mejor, score = "", 0
    for cara, pats in _CARAS.items():
        for pat in pats:
            if pat in texto:
                pts = len(pat)
                if pts > score:
                    mejor, score = cara, pts
    return mejor


def _resumen_aislar(saved: list[tuple]) -> str:
    vis = 0
    for occ, _old in saved:
        try:
            if bool(occ.Visible):
                vis += 1
        except Exception:
            continue
    return f"aislar: {len(saved)} hojas, {vis} visibles, {len(saved) - vis} ocultas"


def _ancestros_top(tops, keep_path: str) -> set:
    found = set()
    for i in range(1, int(tops.Count) + 1):
        try:
            occ = tops.Item(i)
            if bool(occ.Suppressed):
                continue
            path = _path(occ.Definition.Document)
        except Exception:
            continue
        ok = path == keep_path
        if not ok:
            try:
                ok = _contiene(occ.SubOccurrences, keep_path)
            except Exception:
                ok = False
        if ok:
            found.add(occ)
    return found


def _contiene(occs, keep_path: str) -> bool:
    try:
        n = int(occs.Count)
    except Exception:
        return False
    for i in range(1, n + 1):
        try:
            occ = occs.Item(i)
            if bool(occ.Suppressed):
                continue
            path = _path(occ.Definition.Document)
        except Exception:
            continue
        if path == keep_path:
            return True
        try:
            if _contiene(occ.SubOccurrences, keep_path):
                return True
        except Exception:
            continue
    return False


def _clave(occ) -> tuple:
    try:
        name = str(occ.Name)
        rb = occ.RangeBox
        cx = round((float(rb.MinPoint.X) + float(rb.MaxPoint.X)) * 0.5, 2)
        cy = round((float(rb.MinPoint.Y) + float(rb.MaxPoint.Y)) * 0.5, 2)
        cz = round((float(rb.MinPoint.Z) + float(rb.MaxPoint.Z)) * 0.5, 2)
        return (name, cx, cy, cz)
    except Exception:
        return (id(occ), 0.0, 0.0, 0.0)


def _restaurar_vis(saved: list[tuple]) -> None:
    for occ, vis in reversed(saved):
        try:
            if bool(occ.Visible) != vis:
                occ.Visible = vis
        except Exception:
            continue


def _extents(cam):
    try:
        got = cam.GetExtents()
        if isinstance(got, (tuple, list)) and len(got) >= 2:
            return float(got[0]), float(got[1])
    except Exception:
        return None
    return None


def _path(doc) -> str:
    try:
        return str(getattr(doc, "FullFileName", "") or "").replace("\\", "/").lower()
    except Exception:
        return ""


def _lineas_negras(img: Image.Image) -> Image.Image:
    """Solo aristas: el gris de sombra/AO se volvía mancha negra al oscurecer todo v<210."""
    gray = ImageOps.grayscale(img)
    w, h = gray.size
    corners = [
        gray.getpixel((2, 2)),
        gray.getpixel((w - 3, 2)),
        gray.getpixel((2, h - 3)),
        gray.getpixel((w - 3, h - 3)),
    ]
    if sum(corners) / 4 < 90:
        gray = ImageOps.invert(gray)
    pix = gray.load()
    out = Image.new("RGB", (w, h), WHITE)
    destp = out.load()
    oscuro = 200
    for y in range(h):
        ym, yp = max(0, y - 1), min(h - 1, y + 1)
        for x in range(w):
            v = pix[x, y]
            if v >= oscuro:
                continue
            xm, xp = max(0, x - 1), min(w - 1, x + 1)
            vecino = max(
                pix[xm, y],
                pix[xp, y],
                pix[x, ym],
                pix[x, yp],
            )
            if vecino - v < 28:
                continue
            destp[x, y] = (0, 0, 0)
    return out
