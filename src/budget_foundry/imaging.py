"""Stage 2, import: source photo -> corrected image, flat-fielded sheet, ink mask, components.

Sheets without markers (all of v0) skip perspective correction: the corrected image
is the photo itself, upright.
"""
from __future__ import annotations

import json

import cv2
import numpy as np
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener
from skimage.morphology import skeletonize

from .project import Project, fingerprint, sha256_file

register_heif_opener()

DEFAULTS = dict(background_kernel=81, background_blur=25, ink_below=140, paper_above=120,
                min_component_area=150, max_component_width=0.3, max_component_height=0.2)


def settings(p: Project) -> dict:
    return {**DEFAULTS, **p.config.get('import', {})}


def stage_fp(p: Project, key: str) -> str:
    return fingerprint('import', sha256_file(p.source_path(key)), settings(p))


def load_upright(path) -> Image.Image:
    return ImageOps.exif_transpose(Image.open(path)).convert('RGB')


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
    load_upright(p.source_path(key)).save(out / 'image.png')
    gray = cv2.imread(str(out / 'image.png'), cv2.IMREAD_GRAYSCALE)
    norm, ink = flatten(gray, s)
    cv2.imwrite(str(out / 'norm.png'), norm)
    cv2.imwrite(str(out / 'ink.png'), ink)
    comps, lab = components(ink, s)
    np.savez_compressed(out / 'labels.npz', lab=lab)
    (out / 'comps.json').write_text(json.dumps(comps))
    sws = np.array([c['sw'] for c in comps])
    H, W = gray.shape
    report = dict(width=W, height=H, components=len(comps),
                  stroke_px=float(np.median(sws)) if sws.size else 0.0)
    p.mark_stage(out, stage_fp(p, key), source_sha256=sha256_file(p.source_path(key)), **report)
    log(f'  sheet {key}: {W}×{H}px, {len(comps)} components, median stroke {report["stroke_px"]:.1f}px')


def load(p: Project, key: str) -> dict:
    d = p.sheet_dir(key)
    return dict(comps=json.loads((d / 'comps.json').read_text()),
                ink_path=d / 'ink.png', record=p.stage_record(d))


def load_labels(p: Project, key: str) -> np.ndarray:
    return np.load(p.sheet_dir(key) / 'labels.npz')['lab']
