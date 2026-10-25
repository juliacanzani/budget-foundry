"""Stage 1, template: a printable PDF from the charset, and the layout import reads back.

Everything is laid out once in millimetres (origin top left, y down, as in images).
The PDF is drawn from that layout and the layout is saved as templates/<rev>.json in
the project, so an old printout still imports after the charset changes.

Each sheet carries four corner ArUco markers (ids 4n..4n+3 for sheet n: top left,
top right, bottom right, bottom left) and one revision marker (id 800 + rev mod 200).
Guides print pale cyan or light grey; import removes them by position and lightness,
so a mono printer works as well as a colour one.

The PDF opens with a guide page: instructions only, outside the layout. It carries the
revision marker and no corner markers, which is how import knows to skip it.
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
GUIDE = 'guide'                                        # find_sheet's sheet index for the guide page
GUIDE_PAGES = 1                                        # PDF pages before sheet 0
GUIDE_COLOUR = {'colour': (0.55, 0.85, 0.93), 'mono': (0.72, 0.72, 0.72)}   # pale cyan, light grey
GUIDE_MM = 0.3
# Printed under the character in the margin, where its shape alone could be any of several:
# a name, and where length or height is the question, the character in a word
NAMES = {
    'I': ('capital i', None), 'l': ('small L', None), 'O': ('capital o', None), '0': ('zero', None), '1': ('one', None),
    '.': ('full stop', None), ',': ('comma', None), ':': ('colon', None), ';': ('semicolon', None),
    '…': ('ellipsis', 'so…'), '!': ('exclamation', None), '?': ('question', None),
    "'": ('straight quote', "it's"), '"': ('straight double', '"hi"'),
    '“': ('open double', '“hi”'), '”': ('close double', '“hi”'),
    '‘': ('open single', '‘hi’'), '’': ('apostrophe', 'it’s'),
    '-': ('hyphen', 'well-made'), '–': ('en dash', '9–5'), '—': ('em dash', 'wait—no'), '_': ('underscore', 'utm_source'),
    '(': ('open paren', None), ')': ('close paren', None), '[': ('open bracket', None), ']': ('close bracket', None),
    '{': ('open brace', None), '}': ('close brace', None), '<': ('less than', None), '>': ('greater than', None),
    '«': ('open guillemet', '«oui»'), '»': ('close guillemet', '«oui»'), '/': ('slash', 'and/or'),
    '\\': ('backslash', None), '|': ('vertical bar', None), '+': ('plus', None), '=': ('equals', None),
    '×': ('times', '3×4'), '÷': ('divide', '8÷2'), '%': ('percent', '50%'), '*': ('asterisk', None),
    '#': ('hash', None), '@': ('at', None), '&': ('ampersand', None), '~': ('tilde', '~5'),
}
WORDS = ['nanbncndnenfngnhninjnknlnmnonpnqnrnsntnunvnwnxnynzn', 'Hamburgevons', 'HAMBURGEFONSTIV',
         'little better coffee the other', 'The quick brown fox jumps over the lazy dog.']


def wrap(text: str, n: int) -> list[str]:
    """Greedy lines of at most n characters, breaking at spaces; a longer word is cut into
    even lengths, so an "nanbn" run keeps each letter beside an n."""
    n -= n % 2
    lines, line = [], ''
    for w in text.split():
        while len(w) > n: lines += [line] if line else []; line = ''; lines.append(w[:n]); w = w[n:]
        if line and len(line) + 1 + len(w) > n: lines.append(line); line = w
        else: line = f'{line} {w}'.strip()
    return lines + ([line] if line else [])


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
                 desc=base + cap * s['descender'], top=y_top, bottom=y_top + pitch, x0=x0 if text is None else m, x1=x1,
                 label_x=(m + x0) / 2)
        if char is not None: r['char'] = char
        if text is not None: r['text'] = text
        return r

    sheets = []
    for i in range(0, len(chars), per_sheet):
        rows = [row(top + j * pitch, c, char=c) for j, c in enumerate(chars[i:i + per_sheet])]
        sheets.append(dict(kind='chars', rows=rows))
    # Words rows run the full width, with their prompt above; a long one goes over several rows,
    # at about 0.6 cap per handwritten character
    per_row = int((x1 - m) / (cap * 0.6))
    words = [line for w in p.config.get('template', {}).get('words', WORDS) for line in wrap(w, per_row)]
    sheets.append(dict(kind='words', rows=[row(top + j * pitch, w, text=w) for j, w in enumerate(words[:per_sheet])]))
    for n, sh in enumerate(sheets): sh['index'] = n
    body = dict(paper=s['paper'], size=[W, H], marker_mm=mk, margin_mm=m, cap_mm=cap, label_mm=s['label_mm'], sheets=sheets)
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

    rx, ry = rev_marker_origin(lay); marker(lay['rev_marker'], rx, ry, lay['marker_mm'])
    guide_page(c, p, lay, guide, Y, mono)
    c.showPage()

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
                name, example = NAMES.get(r['label'], (None, None))
                for line, dy in ((name, 2), (example, 4.6)):
                    if not line: continue
                    size = min(6.5, 6.5 * (lay['label_mm'] - 2) * mm / c.stringWidth(line, font, 6.5))
                    c.setFont(font, size); c.drawCentredString(r['label_x'] * mm, Y(r['desc'] + dy), line)
            else:                                          # above the row, clear of tall letters
                c.setFont(font, 8)
                c.drawString(r['x0'] * mm, Y(r['cap'] - 1.2), r['label'])
        c.showPage()
    c.save()
    return out, lay


def guide_page(c, p: Project, lay: dict, guide, Y, mono: bool) -> None:
    """How to fill in the template, on its own first page."""
    import os
    from reportlab.lib.units import mm
    from reportlab.lib.utils import simpleSplit
    W, H = lay['size']; m = lay['margin_mm']
    x0, width = m + 6, W - 2 * (m + 6)
    y = m + lay['marker_mm'] + 12
    n = len(lay['sheets'])
    try: folder = os.path.relpath(p.root)
    except ValueError: folder = str(p.root)
    if folder.startswith('..'): folder = str(p.root)

    def text(s, size=9.5, font='Helvetica', gap=1.6, indent=0.0, colour=(0, 0, 0)):
        nonlocal y
        c.setFont(font, size); c.setFillColorRGB(*colour)
        lead = size * 0.3528 * 1.35                        # line height in mm
        for line in simpleSplit(s, font, size, (width - indent) * mm):
            y += lead; c.drawString((x0 + indent) * mm, Y(y), line)
        y += gap

    def heading(s):
        nonlocal y
        y += 3; text(s, 11.5, 'Helvetica-Bold', gap=0.8)

    def bullets(items):
        for s in items:
            c.setFont('Helvetica', 9.5); c.setFillColorRGB(0, 0, 0)
            c.drawString(x0 * mm, Y(y + 9.5 * 0.3528 * 1.35), '•')
            text(s, indent=4)

    text('How to fill in this template', 20, 'Helvetica-Bold', gap=1)
    text(f"{p.config['name']} · {n} writing sheets after this one · rev {lay['rev']}. This page isn't read "
         "back, so print from page 2 if you don't need it.", 9.5, colour=(0.3, 0.3, 0.3), gap=2)

    heading('1  Print, or write on screen')
    bullets(['Any printer works, colour or black and white. '
             + ('This copy has grey guide lines for black-and-white printers; template.pdf has pale blue ones.' if mono
                else 'If the pale blue guide lines disappear on yours, print template-mono.pdf instead.'),
             'Any scale is fine, but keep the whole page: all four black corner squares must print.',
             'No printer? Write on this PDF with a stylus and export it.'])

    heading('2  Write')
    bullets(['Use the pen you want the font to look like. A black or dark felt tip reads best; '
             'pencil and pale colours may not be picked up.',
             'Each row is for the grey character at its left; symbols are named under it, with an example '
             'where size or length matters (a hyphen is short, an em dash long). Write it 5 to 8 times along '
             'the row. Every copy '
             'is a candidate: you keep up to four later, and the font cycles through them so repeated '
             'letters vary.',
             'Leave a clear gap between copies: ink that touches becomes one shape. The dots on i and j are fine.',
             'Write naturally rather than precisely. Size and baseline are evened out, so the lines are a '
             'guide, not a rule.',
             'Made a mistake? Leave it and write another copy. You can reject any copy later.',
             'Keep clear of the black squares and the small print at the foot of each sheet.',
             'The last sheet has words: write each line under its prompt, as you normally would; a long one '
             'carries on to the next row. It is kept '
             'for spacing and, later, ligatures, so it is optional for now.'])

    # the four lines, as they print on the sheets, drawn twice the size to fit their labels
    y += 2
    cap = 2 * lay['cap_mm']; xh, de = DEFAULTS['xheight'], DEFAULTS['descender']
    sx0, sx1 = x0 + 4, x0 + 70
    base = y + cap * 1.05
    lines = [('cap', base - cap, (0.6, 2), 'Capitals and tall letters (b, d, h) reach the top line'),
             ('x', base - cap * xh, (2, 2), 'a, n and x reach the dashed line'),
             ('base', base, None, 'Everything sits on the solid baseline'),
             ('desc', base + cap * de, (0.6, 2), 'g, p and y drop to the bottom line')]
    for _, ly, dash, label in lines:
        c.setStrokeColorRGB(*guide); c.setLineWidth(GUIDE_MM * mm)
        if dash: c.setDash(*[v * mm for v in dash])
        else: c.setDash()
        c.line(sx0 * mm, Y(ly), sx1 * mm, Y(ly))
        c.setDash(); c.setFont('Helvetica', 8.5); c.setFillColorRGB(0.25, 0.25, 0.25)
        c.drawString((sx1 + 3) * mm, Y(ly + 1), label)
    y = base + cap * de + 4

    heading('3  Photograph')
    bullets(['One sheet per photo, lying flat, in even light with no shadows across it.',
             'Get the whole page in, with all four corner squares. An angle is fine: the squares correct it.',
             'Fill the frame. You get a warning if a capital comes out under 120 pixels tall.',
             'Wrote on the PDF? Use the exported PDF as it is; there is nothing to photograph.'])

    heading('4  Bring it in')
    for cmd, what in ((f'budget-foundry add {folder} <photos or PDF>', 'copies them into the project'),
                      (f'budget-foundry segment {folder}', 'reads each sheet and finds every copy'),
                      (f'budget-foundry serve {folder}', 'opens the app: choose keepers, then build the font')):
        c.setFont('Courier', 9); c.setFillColorRGB(0, 0, 0)
        y += 9 * 0.3528 * 1.35; c.drawString(x0 * mm, Y(y), cmd)
        text(what, 8.5, colour=(0.3, 0.3, 0.3), indent=4, gap=1.2)


# ---- geometry for import

def find_sheet(p: Project, gray: np.ndarray):
    """Detect markers; return (layout, sheet index, homography image→mm, report) or None.
    The guide page returns (layout, GUIDE, None, {})."""
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
    if not by_sheet:
        # The revision marker alone is the guide page: instructions, nothing to read
        return (lay, GUIDE, None, {}) if lay['rev_marker'] in found else None
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
