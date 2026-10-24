"""Fake phone photos of filled-in templates: the real template PDF, written in with an
existing font, then warped, unevenly lit, blurred, noised and JPEG-compressed."""
from __future__ import annotations

import io

import cv2
import numpy as np
import pypdfium2 as pdfium
from fontTools.ttLib import TTFont
from PIL import Image, ImageChops, ImageDraw

from budget_foundry.shaping import Poly

INK = (28, 32, 62)


def page_image(pdf, index, ppm):
    return pdfium.PdfDocument(str(pdf))[index].render(scale=ppm * 25.4 / 72).to_pil().convert('RGB')


def write_rows(img, sheet, ppm, font_path, repeats=6, seed=0, guide_gamma=1.0):
    """Write each row's character `repeats` times on its baseline, with some wobble."""
    rng = np.random.default_rng(seed)
    if guide_gamma != 1.0:            # darken the printed guides, like a heavy-handed mono printer
        a = np.asarray(img).astype(np.float32) / 255
        img = Image.fromarray((a ** guide_gamma * 255).astype(np.uint8))
    tt = TTFont(str(font_path)); gs = tt.getGlyphSet(); cmap = tt.getBestCmap(); order = set(tt.getGlyphOrder())
    ink = Image.new('1', img.size, 0)
    expected = []
    for r in sheet['rows']:
        cap_px = (r['base'] - r['cap']) * ppm
        x = r['x0'] * ppm + 4 * ppm
        step = (r['x1'] - r['x0'] - 8) * ppm / repeats
        base = cmap[ord(r['char'])]
        names = [base] + [f'{base}.alt{k}' for k in (1, 2, 3) if f'{base}.alt{k}' in order]
        for i in range(repeats):
            sc = cap_px / 700 * rng.uniform(0.94, 1.06)
            ox = x + i * step + rng.normal(0, ppm); oy = r['base'] * ppm + rng.normal(0, 0.35 * ppm)
            pen = Poly(gs); gs[names[i % len(names)]].draw(pen)
            g = Image.new('1', img.size, 0)
            for poly in pen.polys:
                if len(poly) < 3: continue
                t = Image.new('1', img.size, 0)
                ImageDraw.Draw(t).polygon([(ox + px * sc, oy - py * sc) for px, py in poly], fill=1)
                g = ImageChops.logical_xor(g, t)
            ink = ImageChops.logical_or(ink, g)
        expected.append((r['char'], repeats))
    ink = ink.convert('L')
    page = np.asarray(img).astype(np.float32)
    a = np.asarray(ink).astype(np.float32)[..., None] / 255
    page = page * (1 - a) + np.array(INK, np.float32) * a
    return Image.fromarray(page.astype(np.uint8)), expected


def photograph(img, seed=0, tilt=0.06, rotate=4.0):
    """Perspective, rotation, a table around the page, light falloff, blur, noise, JPEG."""
    rng = np.random.default_rng(seed)
    a = np.asarray(img).astype(np.float32)
    h, w = a.shape[:2]
    pad = int(0.08 * max(w, h))
    W, H = w + 2 * pad, h + 2 * pad
    src = np.float32([(0, 0), (w, 0), (w, h), (0, h)])
    jit = rng.uniform(-tilt, tilt, (4, 2)) * [w, h]
    dst = src + pad + jit
    c, s = np.cos(np.radians(rotate)), np.sin(np.radians(rotate))
    centre = np.float32([W / 2, H / 2])
    dst = (dst - centre) @ np.float32([[c, -s], [s, c]]).T + centre
    M = cv2.getPerspectiveTransform(src, dst.astype(np.float32))
    table = np.full((H, W, 3), (120, 96, 70), np.float32)
    warped = cv2.warpPerspective(a, M, (W, H), borderMode=cv2.BORDER_CONSTANT, borderValue=(-1, -1, -1))
    out = np.where(warped < 0, table, warped)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    light = 1.02 - 0.28 * ((xx / W - 0.2) ** 2 + (yy / H - 0.15) ** 2)
    out = out * light[..., None]
    out = cv2.GaussianBlur(out, (0, 0), 1.1)
    out = out + rng.normal(0, 4, out.shape)
    buf = io.BytesIO()
    Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).save(buf, 'JPEG', quality=85)
    return buf.getvalue()


def synthetic_project(tmp, sheets=(0,), font=None, mono_every=2):
    """A new project with a template and photos of `sheets` written in Julia Marker."""
    from pathlib import Path
    from budget_foundry import template
    from budget_foundry.project import Project
    from budget_foundry.workspace import add_sources, new_project
    font = font or Path(__file__).resolve().parents[1] / 'budget-foundry-v0' / 'build' / 'JuliaMarker-Regular.otf'
    p = new_project(tmp / 'hand', 'Test Hand')
    pdfs = {False: template.write_pdf(p, tmp / 'colour.pdf')[0], True: template.write_pdf(p, tmp / 'mono.pdf', mono=True)[0]}
    lay = template.layout(p)
    files = []
    for k, n in enumerate(sheets):
        mono = bool(mono_every) and k % mono_every == 1
        img, _ = write_rows(page_image(pdfs[mono], n, 12), lay['sheets'][n], 12, font, seed=n, guide_gamma=1.5 if mono else 1.0)
        f = tmp / f'sheet{n + 1:02d}.jpg'; f.write_bytes(photograph(img, seed=n, rotate=(-1) ** n * (2 + n % 4))); files.append(f)
    add_sources(p, files, log=lambda *a: None)
    return Project.open(p.root)
