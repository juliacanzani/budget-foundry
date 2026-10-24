"""Stage 2, import: source photo -> corrected image, flat-fielded sheet, ink mask, components.

Template sheets are found by their ArUco markers and warped into the template's own
millimetre space (px_per_mm), so every row, guide and label sits where the layout says.
Guides are then dropped by position: inside a guide's footprint ink must be darker
than elsewhere, which removes pale cyan and light grey prints alike. Anything outside
the writing areas (markers, labels, sheet code) is ignored.

Sheets without markers (all of v0) skip correction: the corrected image is the photo
itself, upright, and rows come from a hand-written layout in decisions.json.
"""
from __future__ import annotations

import json
import sys

import cv2
import numpy as np
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener
from skimage.morphology import skeletonize

from . import freeform, template
from .project import Project, code_fp, fingerprint, sha256_file

register_heif_opener()

DEFAULTS = dict(background_kernel=81, background_blur=25, ink_below=140, paper_above=120,
                min_component_area=150, max_component_width=0.3, max_component_height=0.2,
                px_per_mm=16, guide_ink_below=95)


def settings(p: Project) -> dict:
    return {**DEFAULTS, **p.config.get('import', {})}


def stage_fp(p: Project, key: str) -> str:
    return fingerprint('import', code_fp(sys.modules[__name__], template, freeform), sha256_file(p.source_path(key)),
                       p.sheet(key), settings(p), [r['rev'] for r in template.revisions(p)])


def load_upright(path, page: int = 1) -> Image.Image:
    if str(path).lower().endswith('.pdf'):
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(str(path))
        return doc[page - 1].render(scale=400 / 72).to_pil().convert('RGB')
    return ImageOps.exif_transpose(Image.open(path)).convert('RGB')


def has_location(path) -> bool:
    """GPS EXIF in a source photo; worth stripping before a project goes anywhere public."""
    if str(path).lower().endswith('.pdf'): return False
    with Image.open(path) as im:
        return bool(im.getexif().get_ifd(0x8825))


def flatten(gray: np.ndarray, s: dict) -> tuple[np.ndarray, np.ndarray]:
    """Divide out the lighting, then threshold ink against the local background."""
    g = gray.astype(np.float32)
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (s['background_kernel'],) * 2)
    bg = cv2.morphologyEx(g, cv2.MORPH_CLOSE, ker)          # closing removes dark ink
    bg = cv2.GaussianBlur(bg, (0, 0), s['background_blur'])
    norm = np.clip(g / np.maximum(bg, 1) * 255, 0, 255).astype(np.uint8)
    ink = ((norm < s['ink_below']) & (bg > s['paper_above'])).astype(np.uint8) * 255
    ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    return norm, ink


def components(ink: np.ndarray, s: dict) -> tuple[list[dict], np.ndarray]:
    """Connected components with a skeleton-median stroke width each."""
    H, W = ink.shape
    n, lab, st, _ = cv2.connectedComponentsWithStats(ink, 8)
    dist = cv2.distanceTransform(ink, cv2.DIST_L2, 5)
    comps = []
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if a < s['min_component_area']: continue
        if x <= 2 or y <= 2 or x + w >= W - 3 or y + h >= H - 3: continue
        if w > W * s['max_component_width'] or h > H * s['max_component_height']: continue
        m = lab[y:y + h, x:x + w] == i
        d = dist[y:y + h, x:x + w][skeletonize(m)]
        sw = float(np.median(d) * 2) if d.size else 0
        comps.append(dict(id=int(i), x=int(x), y=int(y), w=int(w), h=int(h), a=int(a), sw=round(sw, 1)))
    return comps, lab


def run(p: Project, key: str, log=print) -> None:
    s = settings(p); out = p.sheet_dir(key); out.mkdir(parents=True, exist_ok=True)
    photo = load_upright(p.source_path(key), p.sheet(key).get('page', 1))
    if p.sheet(key).get('kind') == 'freeform':
        return run_freeform(p, key, photo, s, out, log)
    found = template.find_sheet(p, cv2.cvtColor(np.asarray(photo), cv2.COLOR_RGB2GRAY))
    tinfo = None
    if found:
        lay, n, Hm, rep = found; ppm = s['px_per_mm']
        W, H = int(round(lay['size'][0] * ppm)), int(round(lay['size'][1] * ppm))
        warp = cv2.warpPerspective(np.asarray(photo), np.diag([ppm, ppm, 1.0]) @ Hm, (W, H),
                                   flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255))
        Image.fromarray(warp).save(out / 'image.png')
        tinfo = dict(rev=lay['rev'], sheet=n, kind=lay['sheets'][n]['kind'], **rep)
    else:
        photo.save(out / 'image.png')
    gray = cv2.imread(str(out / 'image.png'), cv2.IMREAD_GRAYSCALE)
    norm, ink = flatten(gray, s)
    if found:
        guides = template.guide_mask(lay, n, ppm, ink.shape)
        ink[guides & (norm >= s['guide_ink_below'])] = 0
        ink[~template.writing_mask(lay, n, ppm, ink.shape)] = 0
        ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    cv2.imwrite(str(out / 'norm.png'), norm)
    cv2.imwrite(str(out / 'ink.png'), ink)
    comps, lab = components(ink, s)
    np.savez_compressed(out / 'labels.npz', lab=lab)
    (out / 'comps.json').write_text(json.dumps(comps))
    sws = np.array([c['sw'] for c in comps])
    H, W = gray.shape
    report = dict(width=W, height=H, components=len(comps),
                  stroke_px=float(np.median(sws)) if sws.size else 0.0, location=has_location(p.source_path(key)),
                  template=tinfo)
    p.mark_stage(out, stage_fp(p, key), source_sha256=sha256_file(p.source_path(key)), **report)
    log(f'  sheet {key}: {W}×{H}px, {len(comps)} components, median stroke {report["stroke_px"]:.1f}px'
        + (f", template sheet {tinfo['sheet'] + 1} ({tinfo['kind']}), {tinfo['markers']} markers, fit ±{tinfo['error_mm']}mm, "
           f"cap height {tinfo['cap_px']}px in the photo" if tinfo else ', no markers: manual layout'))
    if tinfo and tinfo['cap_px'] < 120:
        log(f"  ! cap height is only {tinfo['cap_px']}px in the photo (want 120+): shoot closer or one sheet per frame")
    if report['location']:
        log(f'  ! {p.sheet(key)["source"]} has GPS location metadata (strip with: exiftool -gps:all= -xmp:all=)')


def run_freeform(p: Project, key: str, photo, s: dict, out, log=print) -> None:
    sheet = p.sheet(key)
    rgb, ink, rep = freeform.prepare(np.asarray(photo), sheet)
    Image.fromarray(rgb).save(out / 'image.png')
    cv2.imwrite(str(out / 'norm.png'), cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY))
    cv2.imwrite(str(out / 'ink.png'), ink)
    comps, lab = components(ink, {**s, 'max_component_width': 1.0, 'max_component_height': 1.0,
                                  'min_component_area': max(4, int(ink.astype(bool).sum() * 0.0002))})
    np.savez_compressed(out / 'labels.npz', lab=lab)
    (out / 'comps.json').write_text(json.dumps(comps))
    sws = np.array([c['sw'] for c in comps])
    H, W = ink.shape
    p.mark_stage(out, stage_fp(p, key), source_sha256=sha256_file(p.source_path(key)), width=W, height=H,
                 components=len(comps), stroke_px=float(np.median(sws)) if sws.size else 0.0,
                 location=has_location(p.source_path(key)), template=None, freeform=rep)
    log(f"  sheet {key}: freeform {sheet['char']!r}, {len(comps)} components, ink rgb{tuple(rep['ink_rgb'])}")


def load(p: Project, key: str) -> dict:
    d = p.sheet_dir(key)
    return dict(comps=json.loads((d / 'comps.json').read_text()),
                ink_path=d / 'ink.png', record=p.stage_record(d))


def load_labels(p: Project, key: str) -> np.ndarray:
    return np.load(p.sheet_dir(key) / 'labels.npz')['lab']
