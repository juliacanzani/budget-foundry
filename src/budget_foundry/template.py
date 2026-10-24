"""Stage 1, template: a printable PDF from the charset, and the layout import reads back.

Everything is laid out once in millimetres (origin top left, y down, as in images).
The PDF is drawn from that layout and the layout is saved as templates/<rev>.json in
the project, so an old printout still imports after the charset changes.

Each sheet carries four corner ArUco markers (ids 4n..4n+3 for sheet n: top left,
top right, bottom right, bottom left) and one revision marker (id 800 + rev mod 200).
Guides print pale cyan or light grey; import removes them by position and lightness,
so a mono printer works as well as a colour one.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from .project import Project, fingerprint

WRITING_ORDER = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,:;…!?'\"“”‘’-–—_()[]{}<>«»/\\|+=×÷%*#@&~"
PAPER = {'letter': (215.9, 279.4), 'a4': (210.0, 297.0)}
DEFAULTS = dict(paper='letter', cap_mm=10.0, xheight=0.66, descender=0.36, pitch=2.2,
                marker_mm=12.0, margin_mm=8.0, label_mm=20.0)
ARUCO = cv2.aruco.DICT_4X4_1000
REV_BASE, REV_SPAN = 800, 200
GUIDE_COLOUR = {'colour': (0.55, 0.85, 0.93), 'mono': (0.72, 0.72, 0.72)}   # pale cyan, light grey
GUIDE_MM = 0.3
WORDS = ['nanbncndnenfngnhninjnknlnmnonpnqnrnsntnunvnwnxnynzn', 'Hamburgevons', 'HAMBURGEFONSTIV',
         'little better coffee the other', 'The quick brown fox jumps over the lazy dog.']


def settings(p: Project) -> dict:
    return {**DEFAULTS, **p.config.get('template', {})}


def layout(p: Project) -> dict:
    s = settings(p)
    W, H = PAPER[s['paper']]
    m, mk = s['margin_mm'], s['marker_mm']
    top, bottom = m + mk + 6, H - (m + mk + 6)
    x0, x1 = m + s['label_mm'], W - m
    cap = s['cap_mm']
    per_sheet = int((bottom - top) // (cap * s['pitch']))
    pitch = (bottom - top) / per_sheet                     # spread rows to fill the page
    drawn = [c for c in p.charset.get('drawn', '') if not c.isspace()]
    chars = [c for c in WRITING_ORDER if c in drawn] + [c for c in drawn if c not in WRITING_ORDER]

    def row(y_top, label, char=None, text=None):
        base = y_top + cap * 1.15                          # room above the cap line for ascenders
        r = dict(label=label, base=base, cap=base - cap, x=base - cap * s['xheight'],
                 desc=base + cap * s['descender'], top=y_top, bottom=y_top + pitch, x0=x0, x1=x1, label_x=(m + x0) / 2)
        if char is not None: r['char'] = char
        if text is not None: r['text'] = text
        return r

    sheets = []
    for i in range(0, len(chars), per_sheet):
        rows = [row(top + j * pitch, c, char=c) for j, c in enumerate(chars[i:i + per_sheet])]
        sheets.append(dict(kind='chars', rows=rows))
    words = [w for w in p.config.get('template', {}).get('words', WORDS)]
    sheets.append(dict(kind='words', rows=[row(top + j * pitch, w, text=w) for j, w in enumerate(words[:per_sheet])]))
    for n, sh in enumerate(sheets): sh['index'] = n
    body = dict(paper=s['paper'], size=[W, H], marker_mm=mk, margin_mm=m, cap_mm=cap, sheets=sheets)
    rev = fingerprint('template', body)[:6]
    return dict(rev=rev, rev_marker=REV_BASE + int(rev, 16) % REV_SPAN, **body)


def marker_corners_mm(lay: dict) -> dict[int, np.ndarray]:
    """Outer corners (TL, TR, BR, BL) of each corner marker, by corner index 0..3."""
    W, H = lay['size']; m, k = lay['margin_mm'], lay['marker_mm']
    origins = [(m, m), (W - m - k, m), (W - m - k, H - m - k), (m, H - m - k)]
    return {c: np.array([(x, y), (x + k, y), (x + k, y + k), (x, y + k)], np.float32) for c, (x, y) in enumerate(origins)}


def rev_marker_origin(lay: dict) -> tuple[float, float]:
    W, H = lay['size']; m, k = lay['margin_mm'], lay['marker_mm']
    return ((W - k) / 2, m)


def save(p: Project, lay: dict) -> Path:
    d = p.root / 'templates'; d.mkdir(exist_ok=True)
    f = d / f"{lay['rev']}.json"
    f.write_text(json.dumps(lay, ensure_ascii=False, indent=1))
    return f


def revisions(p: Project) -> list[dict]:
    d = p.root / 'templates'
    return [json.loads(f.read_text()) for f in sorted(d.glob('*.json'))] if d.exists() else []


# ---- PDF

def write_pdf(p: Project, out: Path, mono: bool = False) -> tuple[Path, dict]:
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    lay = layout(p); save(p, lay)
    W, H = lay['size']
    c = canvas.Canvas(str(out), pagesize=(W * mm, H * mm))
    c.setTitle(f"{p.config['name']} template {lay['rev']}"); c.setCreator('Budget Foundry')
    Y = lambda y: (H - y) * mm                             # layout y-down -> PDF y-up
    guide = GUIDE_COLOUR['mono' if mono else 'colour']
    d = cv2.aruco.getPredefinedDictionary(ARUCO)
    font = 'Helvetica'
    n = len(lay['sheets'])

    def marker(mid, x, y, k):
        bits = cv2.aruco.generateImageMarker(d, mid, 6, borderBits=1)   # 6×6 cells incl. border
        cell = k / 6
        c.setFillColorRGB(0, 0, 0)
        for r in range(6):
            for q in range(6):
                if bits[r, q] == 0:
                    c.rect((x + q * cell) * mm, Y(y + (r + 1) * cell), cell * mm + 0.02, cell * mm + 0.02, stroke=0, fill=1)

    for sh in lay['sheets']:
        k = lay['marker_mm']
        for corner, pts in marker_corners_mm(lay).items():
            marker(4 * sh['index'] + corner, pts[0][0], pts[0][1], k)
        rx, ry = rev_marker_origin(lay); marker(lay['rev_marker'], rx, ry, k)
        c.setFillColorRGB(*guide); c.setFont(font, 7)
        code = f"Budget Foundry · {p.config['name']} · sheet {sh['index'] + 1} of {n} · rev {lay['rev']}"
        c.drawCentredString(W / 2 * mm, Y(H - lay['margin_mm'] - 3), code)
        for r in sh['rows']:
            c.setStrokeColorRGB(*guide); c.setLineWidth(GUIDE_MM * mm)
            c.setDash()
            c.line(r['x0'] * mm, Y(r['base']), r['x1'] * mm, Y(r['base']))
            for key, dash in (('x', (2, 2)), ('cap', (0.6, 2)), ('desc', (0.6, 2))):
                c.setDash(*[v * mm for v in dash])
                c.line(r['x0'] * mm, Y(r[key]), r['x1'] * mm, Y(r[key]))
            c.setDash()
            c.setFillColorRGB(*guide)
            if sh['kind'] == 'chars':
                c.setFont(font, lay['cap_mm'] * 0.7 / 0.3528)  # points from mm
                c.drawCentredString(r['label_x'] * mm, Y(r['base']), r['label'])
                c.setFont(font, 5.5)
                c.drawCentredString(r['label_x'] * mm, Y(r['desc'] + 1.5), f"U+{ord(r['label']):04X}")
            else:
                c.setFont(font, 7)
                c.drawString(r['x0'] * mm, Y(r['top'] + 2.5), r['label'])
        c.showPage()
    c.save()
    return out, lay


# ---- geometry for import

def find_sheet(p: Project, gray: np.ndarray):
    """Detect markers; return (layout, sheet index, homography image→mm, report) or None."""
    det = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(ARUCO), cv2.aruco.DetectorParameters())
    corners, ids, _ = det.detectMarkers(gray)
    if ids is None: return None
    found = {int(i): c.reshape(4, 2) for i, c in zip(ids.ravel(), corners)}
    revs = {lay['rev_marker']: lay for lay in revisions(p)}
    lays = [revs[i] for i in found if i in revs] or revisions(p)[-1:]
    if not lays: return None
    lay = lays[-1]
    by_sheet = {}
    for i in found:
        if i < REV_BASE: by_sheet.setdefault(i // 4, []).append(i)
    if not by_sheet: return None
    n, ids_ = max(by_sheet.items(), key=lambda kv: len(kv[1]))
    if len(ids_) < 3 or n >= len(lay['sheets']): return None
    mm = marker_corners_mm(lay)
    src = np.concatenate([found[i] for i in ids_]).astype(np.float32)
    dst = np.concatenate([mm[i % 4] for i in ids_]).astype(np.float32)
    if lay['rev_marker'] in found:
        rx, ry = rev_marker_origin(lay); k = lay['marker_mm']
        src = np.concatenate([src, found[lay['rev_marker']]]).astype(np.float32)
        dst = np.concatenate([dst, np.array([(rx, ry), (rx + k, ry), (rx + k, ry + k), (rx, ry + k)], np.float32)])
    Hm, _ = cv2.findHomography(src, dst, 0)
    proj = cv2.perspectiveTransform(src.reshape(-1, 1, 2), Hm).reshape(-1, 2)
    err = float(np.sqrt(((proj - dst) ** 2).sum(1)).max())
    # the photo's own resolution at the page centre, in px per mm
    W, H = lay['size']; inv = np.linalg.inv(Hm)
    pts = cv2.perspectiveTransform(np.float32([[(W / 2, H / 2), (W / 2 + 1, H / 2), (W / 2, H / 2 + 1)]]), inv)[0]
    ppm = float((np.linalg.norm(pts[1] - pts[0]) + np.linalg.norm(pts[2] - pts[0])) / 2)
    return lay, n, Hm, dict(markers=len(ids_), rev_marker=lay['rev_marker'] in found, error_mm=round(err, 3),
                            photo_px_per_mm=round(ppm, 2), cap_px=round(ppm * lay['cap_mm']))


def guide_mask(lay: dict, sheet: int, ppm: float, shape, tol_mm=0.6) -> np.ndarray:
    m = np.zeros(shape, np.uint8)
    for r in lay['sheets'][sheet]['rows']:
        for key in ('base', 'x', 'cap', 'desc'):
            y = r[key] * ppm; h = (GUIDE_MM / 2 + tol_mm) * ppm
            m[int(max(y - h, 0)):int(y + h) + 1, int(r['x0'] * ppm):int(r['x1'] * ppm) + 1] = 1
    return m.astype(bool)


def writing_mask(lay: dict, sheet: int, ppm: float, shape) -> np.ndarray:
    m = np.zeros(shape, bool)
    for r in lay['sheets'][sheet]['rows']:
        m[int(r['top'] * ppm):int(r['bottom'] * ppm), int(r['x0'] * ppm):int(r['x1'] * ppm)] = True
    return m
