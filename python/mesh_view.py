"""Malla Inventor: silueta de canto e ISO Phong (sonda y Módulo de Ingeniería)."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw


def tessellate_document(doc, chord: float = 0.003) -> dict | None:
    try:
        if int(doc.DocumentType) == 12291:
            return tessellate_assembly(doc, chord)
    except Exception:
        pass
    return tessellate_part(doc, chord)


def tessellate_assembly(assembly, chord: float = 0.008) -> dict | None:
    try:
        leaves = assembly.ComponentDefinition.Occurrences.AllLeafOccurrences
        total = int(leaves.Count)
    except Exception:
        return None
    occs = []
    for index in range(1, total + 1):
        try:
            occ = leaves.Item(index)
            if bool(occ.Suppressed):
                continue
            occs.append(occ)
        except Exception:
            continue
    return tessellate_occurrences(occs, chord)


def tessellate_occurrences(occs, chord: float = 0.008) -> dict | None:
    """Solo estas ocurrencias (un segmento + accesorios), no el tanque entero."""
    verts: list[tuple[float, float, float]] = []
    nrm: list[tuple[float, float, float]] = []
    tris: list[tuple[int, int, int]] = []
    for occ in occs or []:
        try:
            if bool(occ.Suppressed):
                continue
            part = occ.Definition.Document
            mesh = tessellate_part(part, chord)
            matrix = occ.Transformation
        except Exception:
            continue
        if not mesh:
            continue
        base = len(verts)
        for p, n in zip(mesh["verts"], mesh["norms"]):
            verts.append(_mx_point(matrix, p))
            nrm.append(_norm(_mx_dir(matrix, n)))
        for a, b, c in mesh["tris"]:
            tris.append((a + base, b + base, c + base))
    if len(verts) < 3 or len(tris) < 1:
        return None
    return {"verts": verts, "norms": nrm, "tris": tris, "nv": len(verts), "nf": len(tris)}


def _mx_point(matrix, p: tuple[float, float, float]) -> tuple[float, float, float]:
    x, y, z = p
    return (
        float(matrix.Cell(1, 1)) * x + float(matrix.Cell(1, 2)) * y + float(matrix.Cell(1, 3)) * z + float(matrix.Cell(1, 4)),
        float(matrix.Cell(2, 1)) * x + float(matrix.Cell(2, 2)) * y + float(matrix.Cell(2, 3)) * z + float(matrix.Cell(2, 4)),
        float(matrix.Cell(3, 1)) * x + float(matrix.Cell(3, 2)) * y + float(matrix.Cell(3, 3)) * z + float(matrix.Cell(3, 4)),
    )


def _mx_dir(matrix, n: tuple[float, float, float]) -> tuple[float, float, float]:
    x, y, z = n
    return (
        float(matrix.Cell(1, 1)) * x + float(matrix.Cell(1, 2)) * y + float(matrix.Cell(1, 3)) * z,
        float(matrix.Cell(2, 1)) * x + float(matrix.Cell(2, 2)) * y + float(matrix.Cell(2, 3)) * z,
        float(matrix.Cell(3, 1)) * x + float(matrix.Cell(3, 2)) * y + float(matrix.Cell(3, 3)) * z,
    )


def tessellate_part(part, chord: float = 0.003) -> dict | None:
    try:
        bodies = part.ComponentDefinition.SurfaceBodies
        nbody = int(bodies.Count)
    except Exception:
        return None
    verts = []
    nrm = []
    tris = []
    for bi in range(1, nbody + 1):
        try:
            faces = bodies.Item(bi).Faces
            nfaces = int(faces.Count)
        except Exception:
            continue
        for fi in range(1, nfaces + 1):
            try:
                nv, nf, coords, norms, idx = faces.Item(fi).CalculateFacets(float(chord))
            except Exception:
                continue
            if int(nv) < 3 or int(nf) < 1:
                continue
            base = len(verts)
            raw = list(coords)
            for i in range(0, len(raw) - 2, 3):
                verts.append((float(raw[i]), float(raw[i + 1]), float(raw[i + 2])))
            nraw = list(norms)
            for i in range(0, len(nraw) - 2, 3):
                nrm.append(_norm((float(nraw[i]), float(nraw[i + 1]), float(nraw[i + 2]))))
            while len(nrm) < len(verts):
                nrm.append((0.0, 0.0, 1.0))
            ids = list(idx)
            for i in range(0, len(ids) - 2, 3):
                a, b, c = int(ids[i]) - 1 + base, int(ids[i + 1]) - 1 + base, int(ids[i + 2]) - 1 + base
                if min(a, b, c) < base or max(a, b, c) >= len(verts):
                    continue
                n = _norm(_cross(_sub(verts[b], verts[a]), _sub(verts[c], verts[a])))
                avg = _norm(
                    (
                        nrm[a][0] + nrm[b][0] + nrm[c][0],
                        nrm[a][1] + nrm[b][1] + nrm[c][1],
                        nrm[a][2] + nrm[b][2] + nrm[c][2],
                    )
                )
                if _dot(n, avg) < 0.0:
                    a, b, c = a, c, b
                tris.append((a, b, c))
    if len(verts) < 3 or len(tris) < 1:
        return None
    return {"verts": verts, "norms": nrm, "tris": tris, "nv": len(verts), "nf": len(tris)}


def _camara_canto(part, ancho_mm: float):
    from acotacion_run import _to_unit

    uom = part.UnitsOfMeasure
    try:
        box = part.ComponentDefinition.SurfaceBodies.Item(1).RangeBox
    except Exception:
        box = part.ComponentDefinition.RangeBox
    mn, mx = box.MinPoint, box.MaxPoint
    axes = [
        ((1.0, 0.0, 0.0), abs(_to_unit(abs(float(mx.X) - float(mn.X)), uom, "mm"))),
        ((0.0, 1.0, 0.0), abs(_to_unit(abs(float(mx.Y) - float(mn.Y)), uom, "mm"))),
        ((0.0, 0.0, 1.0), abs(_to_unit(abs(float(mx.Z) - float(mn.Z)), uom, "mm"))),
    ]
    box_mm = [a[1] for a in axes]
    if ancho_mm > 0.5:
        ranked = sorted(axes, key=lambda item: abs(item[1] - ancho_mm))
    else:
        ranked = sorted(axes, key=lambda item: item[1])
        ranked = [ranked[1]] + [ranked[0], ranked[2]]
    look = ranked[0][0]
    resto = [item for item in axes if item[0] != look]
    resto.sort(key=lambda item: -item[1])
    u_axis = resto[0][0]
    v_axis = _norm(_cross(look, u_axis))
    u_axis = _norm(_cross(v_axis, look))
    origin = (
        (float(mn.X) + float(mx.X)) / 2,
        (float(mn.Y) + float(mx.Y)) / 2,
        (float(mn.Z) + float(mx.Z)) / 2,
    )
    return look, origin, u_axis, v_axis, box_mm


def _silueta(
    mesh, origin, u_axis, v_axis, look, size: int = 720, unit_scale: float = 10.0, min_px: int = 0
) -> tuple[list[tuple[float, float]], object]:
    tris = []
    for a, b, c in mesh["tris"]:
        pa, pb, pc = mesh["verts"][a], mesh["verts"][b], mesh["verts"][c]
        tris.append(
            (
                _proy(pa, origin, u_axis, v_axis, look, unit_scale),
                _proy(pb, origin, u_axis, v_axis, look, unit_scale),
                _proy(pc, origin, u_axis, v_axis, look, unit_scale),
            )
        )
    xs = [p[0] for t in tris for p in t]
    ys = [p[1] for t in tris for p in t]
    if not xs:
        return [], None
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    span = max(maxx - minx, maxy - miny, 1.0)
    pad = 10
    scale = (size - 2 * pad) / span
    corto = min(maxx - minx, maxy - miny)
    if min_px and corto > 1e-6:
        scale = max(scale, float(min_px) / corto)
    if (maxx - minx) * scale * (maxy - miny) * scale > 9_000_000:
        scale = math.sqrt(9_000_000 / max((maxx - minx) * (maxy - miny), 1e-6))
    w = int((maxx - minx) * scale) + 2 * pad + 2
    h = int((maxy - miny) * scale) + 2 * pad + 2
    occ = bytearray(w * h)
    for ta, tb, tc in tris:
        _fill_tri(
            occ,
            w,
            h,
            _pix(ta, minx, maxy, scale, pad),
            _pix(tb, minx, maxy, scale, pad),
            _pix(tc, minx, maxy, scale, pad),
        )
    contour_px = _contorno(occ, w, h, max(800, size))
    outline = []
    for x, y in contour_px:
        outline.append(((x - pad) / scale + minx, maxy - (y - pad) / scale))
    if outline and math.hypot(outline[0][0] - outline[-1][0], outline[0][1] - outline[-1][1]) > 0.2:
        outline.append(outline[0])
    return outline, (occ, w, h)


def _jpg_silueta(dest: Path, outline: list[tuple[float, float]], title: str) -> str:
    if len(outline) < 3:
        img = Image.new("RGB", (400, 200), "#FFFFFF")
        ImageDraw.Draw(img).text((16, 16), title + " (vacio)", fill="#1B2631")
        img.save(dest, "JPEG", quality=92)
        return str(dest)
    xs, ys = [p[0] for p in outline], [p[1] for p in outline]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    span = max(maxx - minx, maxy - miny, 1.0)
    pad = 48
    scale = 560 / span
    w = int((maxx - minx) * scale) + pad * 2
    h = int((maxy - miny) * scale) + pad * 2 + 28
    img = Image.new("RGB", (max(w, 320), max(h, 240)), "#FFFFFF")
    draw = ImageDraw.Draw(img)

    def px(p):
        return (pad + (p[0] - minx) * scale, pad + 24 + (maxy - p[1]) * scale)

    pts = [px(p) for p in outline]
    draw.polygon(pts, fill="#F0F2F4", outline="#1C2833")
    draw.line(pts + [pts[0]], fill="#1C2833", width=2)
    draw.text((pad, 8), title, fill="#1B2631")
    img.save(dest, "JPEG", quality=92)
    return str(dest)


def render_ortho_mesh(
    mesh: dict,
    *,
    origin,
    u_axis,
    v_axis,
    look,
    unit_scale: float,
    crop: tuple[float, float, float, float],
    size: int = 980,
    modo: str = "alambrico",
) -> tuple[Image.Image, object]:
    """Vista ortográfica FRONT. modo=alambrico: líneas 2D (HLR); phong: sólido gris."""
    view = _norm(look)
    light = _norm((view[0] + 0.25, view[1] + 0.55, view[2] + 0.35))
    verts = mesh["verts"]
    vnorm = mesh.get("norms") or [(0.0, 0.0, 1.0)] * len(verts)
    crop_u0, crop_v0, crop_u1, crop_v1 = crop
    projected = []
    for p in verts:
        u, v, d = _proy(p, origin, u_axis, v_axis, view, unit_scale)
        projected.append((u - crop_u0, v - crop_v0, d))
    span_u = max(crop_u1 - crop_u0, 1.0)
    span_v = max(crop_v1 - crop_v0, 1.0)
    aa = 2
    izq = 160
    der, abajo = 72, 140
    escala = size / max(span_u, span_v)
    w = int(izq + span_u * escala + der)
    h = int(izq + span_v * escala + abajo)
    img_aa = Image.new("RGB", (w * aa, h * aa), (255, 255, 255))
    pix = img_aa.load()
    depth = [-1e9] * (w * aa * h * aa)
    wa, ha = w * aa, h * aa
    pad = izq * aa
    sc = escala * aa
    minx, maxy = 0.0, span_v
    face_n = []
    front = []
    alambrico = str(modo or "alambrico").strip().lower() != "phong"
    for a, b, c in mesh["tris"]:
        n = _norm(_cross(_sub(verts[b], verts[a]), _sub(verts[c], verts[a])))
        face_n.append(n)
        front.append(_dot(n, view) > 0.0)
    for ti, (a, b, c) in enumerate(mesh["tris"]):
        if not front[ti]:
            continue
        pa, pb, pc = projected[a], projected[b], projected[c]
        if (
            (pa[0] < -1 and pb[0] < -1 and pc[0] < -1)
            or (pa[1] < -1 and pb[1] < -1 and pc[1] < -1)
            or (pa[0] > span_u + 1 and pb[0] > span_u + 1 and pc[0] > span_u + 1)
            or (pa[1] > span_v + 1 and pb[1] > span_v + 1 and pc[1] > span_v + 1)
        ):
            continue
        n = face_n[ti]
        if alambrico:
            _fill_tri_depth(
                depth,
                wa,
                ha,
                _pixf(pa, minx, maxy, sc, pad),
                _pixf(pb, minx, maxy, sc, pad),
                _pixf(pc, minx, maxy, sc, pad),
                pa[2],
                pb[2],
                pc[2],
            )
            continue
        _fill_tri_phong(
            pix,
            depth,
            wa,
            ha,
            _pixf(pa, minx, maxy, sc, pad),
            _pixf(pb, minx, maxy, sc, pad),
            _pixf(pc, minx, maxy, sc, pad),
            pa[2],
            pb[2],
            pc[2],
            _alinea_n(vnorm[a], n),
            _alinea_n(vnorm[b], n),
            _alinea_n(vnorm[c], n),
            n,
            light,
            view,
        )
    draw_aa = ImageDraw.Draw(img_aa)
    ink = (28, 36, 44)
    width = max(2, aa)
    for p0, p1 in _aristas_solidas(
        mesh, projected, front, face_n, depth, wa, ha, minx, maxy, sc, pad, alambrico=alambrico
    ):
        q0, q1 = _inset_cap(p0, p1, width * 0.48)
        if math.hypot(q1[0] - q0[0], q1[1] - q0[1]) < width:
            continue
        draw_aa.line((q0, q1), fill=ink, width=width)
    img = img_aa.resize((w, h), Image.Resampling.LANCZOS)

    def px(x: float, y: float) -> tuple[float, float]:
        return (izq + float(x) * escala, izq + (span_v - float(y)) * escala)

    return img, px


def _jpg_iso(dest: Path, mesh: dict, title: str, subtitle: str = "") -> str:
    """Sólido opaco con Phong + antialias. Sin aristas de tesela."""
    view = _norm((1.0, 1.0, 1.0))
    light = _norm((0.35, 0.65, 1.0))
    up = (0.0, 0.0, 1.0)
    u_axis = _norm(_cross(up, view))
    v_axis = _norm(_cross(view, u_axis))
    verts = mesh["verts"]
    vnorm = mesh.get("norms") or [(0.0, 0.0, 1.0)] * len(verts)
    origin = (
        sum(p[0] for p in verts) / len(verts),
        sum(p[1] for p in verts) / len(verts),
        sum(p[2] for p in verts) / len(verts),
    )
    projected = [_proy(p, origin, u_axis, v_axis, view) for p in verts]
    xs = [p[0] for p in projected]
    ys = [p[1] for p in projected]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    span = max(maxx - minx, maxy - miny, 1.0)
    aa = 3
    pad = 56 * aa
    scale = (720.0 * aa) / span
    w = max(int((maxx - minx) * scale) + pad * 2, 400 * aa)
    h = max(int((maxy - miny) * scale) + pad * 2 + 28 * aa, 300 * aa)
    img = Image.new("RGB", (w, h), (255, 255, 255))
    pix = img.load()
    depth = [-1e9] * (w * h)
    face_n = []
    front = []
    for a, b, c in mesh["tris"]:
        n = _norm(_cross(_sub(verts[b], verts[a]), _sub(verts[c], verts[a])))
        face_n.append(n)
        front.append(_dot(n, view) > 0.0)
    for ti, (a, b, c) in enumerate(mesh["tris"]):
        if not front[ti]:
            continue
        n = face_n[ti]
        _fill_tri_phong(
            pix,
            depth,
            w,
            h,
            _pixf(projected[a], minx, maxy, scale, pad),
            _pixf(projected[b], minx, maxy, scale, pad),
            _pixf(projected[c], minx, maxy, scale, pad),
            projected[a][2],
            projected[b][2],
            projected[c][2],
            _alinea_n(vnorm[a], n),
            _alinea_n(vnorm[b], n),
            _alinea_n(vnorm[c], n),
            n,
            light,
            view,
        )

    draw = ImageDraw.Draw(img)
    ink = (28, 36, 44)
    width = max(2, aa)
    for p0, p1 in _aristas_solidas(mesh, projected, front, face_n, depth, w, h, minx, maxy, scale, pad):
        q0, q1 = _inset_cap(p0, p1, width * 0.48)
        if math.hypot(q1[0] - q0[0], q1[1] - q0[1]) < width:
            continue
        draw.line((q0, q1), fill=ink, width=width)
    out_w, out_h = max(w // aa, 1), max(h // aa, 1)
    img = img.resize((out_w, out_h), Image.Resampling.LANCZOS)
    ImageDraw.Draw(img).text((26, 8), title, fill=(27, 38, 49))
    if subtitle:
        ImageDraw.Draw(img).text((26, 28), subtitle, fill=(90, 102, 114))
    img.save(dest, "JPEG", quality=98)
    return str(dest)


def save_iso_mesh(dest: str | Path, mesh: dict, *, title: str, subtitle: str = "") -> str:
    return _jpg_iso(Path(dest), mesh, title, subtitle)


def silhouette(mesh, origin, u_axis, v_axis, look, unit_scale: float = 10.0, size: int = 720, min_px: int = 0):
    return _silueta(mesh, origin, u_axis, v_axis, look, size=size, unit_scale=unit_scale, min_px=min_px)


def _fill_tri_depth(depth, w, h, a, b, c, za, zb, zc) -> None:
    ax, ay = a
    bx, by = b
    cx, cy = c
    minx = max(0, int(math.floor(min(ax, bx, cx))))
    maxx = min(w - 1, int(math.ceil(max(ax, bx, cx))))
    miny = max(0, int(math.floor(min(ay, by, cy))))
    maxy = min(h - 1, int(math.ceil(max(ay, by, cy))))
    area = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
    if abs(area) < 1e-6:
        return
    inv = 1.0 / float(area)
    for y in range(miny, maxy + 1):
        py = y + 0.5
        row = y * w
        for x in range(minx, maxx + 1):
            px = x + 0.5
            w0 = ((bx - ax) * (py - ay) - (by - ay) * (px - ax)) * inv
            w1 = ((cx - bx) * (py - by) - (cy - by) * (px - bx)) * inv
            w2 = 1.0 - w0 - w1
            if w0 < 0.0 or w1 < 0.0 or w2 < 0.0:
                continue
            z = zb * w0 + zc * w1 + za * w2
            i = row + x
            if z + 1e-5 >= depth[i]:
                depth[i] = z


def _fill_tri_phong(pix, depth, w, h, a, b, c, za, zb, zc, na, nb, nc, n_face, light, view) -> None:
    ax, ay = a
    bx, by = b
    cx, cy = c
    minx = max(0, int(math.floor(min(ax, bx, cx))))
    maxx = min(w - 1, int(math.ceil(max(ax, bx, cx))))
    miny = max(0, int(math.floor(min(ay, by, cy))))
    maxy = min(h - 1, int(math.ceil(max(ay, by, cy))))
    area = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
    if abs(area) < 1e-6:
        return
    inv = 1.0 / float(area)
    half = _norm((light[0] + view[0], light[1] + view[1], light[2] + view[2]))
    mixed = _dot(na, nb) < 0.72 or _dot(nb, nc) < 0.72 or _dot(nc, na) < 0.72
    for y in range(miny, maxy + 1):
        py = y + 0.5
        row = y * w
        for x in range(minx, maxx + 1):
            px = x + 0.5
            w0 = ((bx - ax) * (py - ay) - (by - ay) * (px - ax)) * inv
            w1 = ((cx - bx) * (py - by) - (cy - by) * (px - bx)) * inv
            w2 = 1.0 - w0 - w1
            if w0 < 0.0 or w1 < 0.0 or w2 < 0.0:
                continue
            z = zb * w0 + zc * w1 + za * w2
            i = row + x
            if z + 1e-5 < depth[i]:
                continue
            depth[i] = z
            if mixed:
                n = n_face
            else:
                nx = nb[0] * w0 + nc[0] * w1 + na[0] * w2
                ny = nb[1] * w0 + nc[1] * w1 + na[1] * w2
                nz = nb[2] * w0 + nc[2] * w1 + na[2] * w2
                n = _norm((nx, ny, nz))
            if _dot(n, view) < 0:
                n = (-n[0], -n[1], -n[2])
            diff = max(0.0, _dot(n, light))
            rim = 1.0 - abs(_dot(n, view))
            spec = max(0.0, _dot(n, half)) ** 48
            shade = 0.22 + 0.68 * diff + 0.18 * spec + 0.12 * rim * rim
            pix[x, y] = (
                min(255, int(148 * shade + 42)),
                min(255, int(154 * shade + 44)),
                min(255, int(160 * shade + 46)),
            )


def _alinea_n(nv, n_face):
    """Evita que la normal del canto/espesor se filtre a la cara."""
    if _dot(nv, n_face) < 0.80:
        return n_face
    return nv


def _aristas_solidas(mesh, projected, front, normals, depth, w, h, minx, maxy, scale, pad, alambrico: bool = False):
    neighbors: dict[tuple[int, int], list[int]] = {}
    for ti, (a, b, c) in enumerate(mesh["tris"]):
        for i0, i1 in ((a, b), (b, c), (c, a)):
            key = (i0, i1) if i0 < i1 else (i1, i0)
            neighbors.setdefault(key, []).append(ti)
    lines = []
    for (i0, i1), tris in neighbors.items():
        silueta = False
        quiebre = False
        if len(tris) == 1:
            t = tris[0]
            if not front[t]:
                continue
            silueta = True
        elif len(tris) == 2:
            t0, t1 = tris
            if not (front[t0] or front[t1]):
                continue
            silueta = front[t0] != front[t1]
            quiebre = front[t0] and front[t1] and _dot(normals[t0], normals[t1]) < (0.35 if alambrico else 0.08)
            if not silueta and not quiebre:
                continue
        else:
            continue
        p0 = projected[i0]
        p1 = projected[i1]
        if not _arista_visible(p0, p1, depth, w, h, minx, maxy, scale, pad):
            continue
        if (
            not alambrico
            and silueta
            and not quiebre
            and not _es_contorno(p0, p1, depth, w, h, minx, maxy, scale, pad)
        ):
            continue
        lines.append((_pix(p0, minx, maxy, scale, pad), _pix(p1, minx, maxy, scale, pad)))
    return lines


def _es_contorno(p0, p1, depth, w, h, minx, maxy, scale, pad) -> bool:
    a = _pixf(p0, minx, maxy, scale, pad)
    b = _pixf(p1, minx, maxy, scale, pad)
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    if length < 1.0:
        return False
    nx, ny = -dy / length, dx / length
    mx, my = (a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5
    z = (p0[2] + p1[2]) * 0.5
    empty = -1e8
    gap = 1.15
    off = 2.6
    z1 = _z_at(depth, w, h, mx + nx * off, my + ny * off)
    z2 = _z_at(depth, w, h, mx - nx * off, my - ny * off)
    far1 = z1 <= empty or (z - z1) > gap
    far2 = z2 <= empty or (z - z2) > gap
    return far1 or far2


def _z_at(depth, w, h, x, y) -> float:
    ix, iy = int(round(x)), int(round(y))
    if ix < 0 or iy < 0 or ix >= w or iy >= h:
        return -1e9
    return depth[iy * w + ix]


def _inset_cap(p0, p1, pix: float):
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    length = math.hypot(dx, dy)
    if length <= 1.0:
        return p0, p1
    ux, uy = dx / length, dy / length
    return (p0[0] + ux * pix, p0[1] + uy * pix), (p1[0] - ux * pix, p1[1] - uy * pix)


def _arista_visible(p0, p1, depth, w, h, minx, maxy, scale, pad) -> bool:
    hits = 0
    ok = 0
    for t in (0.15, 0.5, 0.85):
        x = p0[0] + (p1[0] - p0[0]) * t
        y = p0[1] + (p1[1] - p0[1]) * t
        z = p0[2] + (p1[2] - p0[2]) * t
        px, py = _pix((x, y, z), minx, maxy, scale, pad)
        if px < 0 or py < 0 or px >= w or py >= h:
            continue
        hits += 1
        if z >= depth[py * w + px] - 0.12:
            ok += 1
    return hits > 0 and ok * 2 >= hits


def _proy(p, origin, u_axis, v_axis, look, unit_scale: float = 10.0):
    rel = (p[0] - origin[0], p[1] - origin[1], p[2] - origin[2])
    return (_dot(rel, u_axis) * unit_scale, _dot(rel, v_axis) * unit_scale, _dot(rel, look) * unit_scale)


def _pix(p, minx, maxy, scale, pad) -> tuple[int, int]:
    fx, fy = _pixf(p, minx, maxy, scale, pad)
    return (int(round(fx)), int(round(fy)))


def _pixf(p, minx, maxy, scale, pad) -> tuple[float, float]:
    return ((p[0] - minx) * scale + pad, (maxy - p[1]) * scale + pad)


def _fill_tri(occ: bytearray, w: int, h: int, a, b, c) -> None:
    minx = max(0, min(a[0], b[0], c[0]))
    maxx = min(w - 1, max(a[0], b[0], c[0]))
    miny = max(0, min(a[1], b[1], c[1]))
    maxy = min(h - 1, max(a[1], b[1], c[1]))
    area = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    if abs(area) < 1:
        _line(occ, w, h, a, b)
        _line(occ, w, h, b, c)
        _line(occ, w, h, c, a)
        return
    for y in range(miny, maxy + 1):
        for x in range(minx, maxx + 1):
            w0 = (b[0] - a[0]) * (y - a[1]) - (b[1] - a[1]) * (x - a[0])
            w1 = (c[0] - b[0]) * (y - b[1]) - (c[1] - b[1]) * (x - b[0])
            w2 = (a[0] - c[0]) * (y - c[1]) - (a[1] - c[1]) * (x - c[0])
            if (w0 >= 0 and w1 >= 0 and w2 >= 0) or (w0 <= 0 and w1 <= 0 and w2 <= 0):
                occ[y * w + x] = 1


def _line(occ, w, h, a, b) -> None:
    x0, y0 = a
    x1, y1 = b
    steps = max(abs(x1 - x0), abs(y1 - y0), 1)
    for i in range(steps + 1):
        x = int(round(x0 + (x1 - x0) * i / steps))
        y = int(round(y0 + (y1 - y0) * i / steps))
        if 0 <= x < w and 0 <= y < h:
            occ[y * w + x] = 1


def _contorno(occ: bytearray, w: int, h: int, max_pts: int = 280) -> list[tuple[int, int]]:
    start = None
    for y in range(h):
        row = y * w
        for x in range(w):
            if occ[row + x]:
                start = (x, y)
                break
        if start:
            break
    if start is None:
        return []
    deltas = ((1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1))
    contour = [start]
    cx, cy = start
    prev = 4
    for _ in range(w * h):
        found = None
        for k in range(8):
            d = (prev + k) % 8
            nx, ny = cx + deltas[d][0], cy + deltas[d][1]
            if 0 <= nx < w and 0 <= ny < h and occ[ny * w + nx]:
                found = (nx, ny, d)
                break
        if found is None:
            break
        nx, ny, d = found
        if (nx, ny) == start and len(contour) > 12:
            break
        contour.append((nx, ny))
        cx, cy = nx, ny
        prev = (d + 5) % 8
        if len(contour) > 12000:
            break
    keep = max(280, int(max_pts or 280))
    step = max(1, len(contour) // keep)
    return contour[::step]


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    length = math.hypot(a[0], math.hypot(a[1], a[2]))
    if length <= 1e-12:
        return (1.0, 0.0, 0.0)
    return (a[0] / length, a[1] / length, a[2] / length)


