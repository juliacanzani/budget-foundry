"""Freeform import: any image of one glyph (paint, sauce, a single photographed letter).

Ink is found by colour, not darkness: either a given colour within a tolerance, or the
colour cluster farthest from the paper (the image border's median). Specks within a
set distance of the main shape stay with it (the splatter belongs to the letter);
the rest are dropped. Review flags stand in for the review screen until Milestone 3.
"""
from __future__ import annotations

import re

import cv2
import numpy as np

DEFAULTS = dict(ink='auto', tolerance=28.0, speck_distance=0.15, min_speck=0.0002, rotate=0.0)
NAMES = {'period': '.', 'comma': ',', 'colon': ':', 'semicolon': ';', 'question': '?', 'exclam': '!',
         'slash': '/', 'backslash': '\\', 'quotedbl': '"', 'quotesingle': "'", 'asterisk': '*',
         'ampersand': '&', 'at': '@', 'numbersign': '#', 'percent': '%', 'hyphen': '-', 'underscore': '_',
         'bar': '|', 'plus': '+', 'equal': '=', 'less': '<', 'greater': '>', 'space': ' '}


def char_from_name(stem: str) -> str | None:
    """`A.jpg`, `a_2.png`, `uni0041.png`, `question-1.heic` → the character."""
    head = re.split(r'[_\-\s.]', stem)[0]
    if re.fullmatch(r'uni[0-9A-Fa-f]{4,6}', head): return chr(int(head[3:], 16))
    if head in NAMES: return NAMES[head]
    return head if len(head) == 1 else None


def _lab(rgb):
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32) * [100 / 255, 1, 1] - [0, 128, 128]


def ink_mask(rgb: np.ndarray, s: dict) -> tuple[np.ndarray, list[int]]:
    """Boolean ink mask and the ink colour used (sRGB)."""
    lab = _lab(rgb)
    if s['ink'] == 'auto':
        h, w = lab.shape[:2]
        border = np.concatenate([lab[:h // 40 + 1].reshape(-1, 3), lab[-(h // 40 + 1):].reshape(-1, 3),
                                 lab[:, :w // 40 + 1].reshape(-1, 3), lab[:, -(w // 40 + 1):].reshape(-1, 3)])
        paper = np.median(border, 0)
        sample = lab[::max(1, h // 300), ::max(1, w // 300)].reshape(-1, 3).astype(np.float32)
        crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.5)
        _, lbl, centres = cv2.kmeans(sample, 3, None, crit, 4, cv2.KMEANS_PP_CENTERS)
        centre = max(centres, key=lambda c: np.linalg.norm(c - paper))
    else:
        hx = s['ink'].lstrip('#'); rgb_ink = np.uint8([[[int(hx[i:i + 2], 16) for i in (0, 2, 4)]]])
        centre = _lab(rgb_ink)[0, 0]
    d = np.linalg.norm(lab - centre, axis=2)
    mask = d < s['tolerance']
    c8 = np.uint8([[np.clip((centre + [0, 128, 128]) / [100 / 255, 1, 1], 0, 255)]])
    return mask, [int(v) for v in cv2.cvtColor(c8, cv2.COLOR_LAB2RGB)[0, 0]]


def keep_near(mask: np.ndarray, s: dict) -> np.ndarray:
    """Largest shape plus specks within speck_distance × its size; drop specks below min_speck × its area."""
    m = mask.astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
    if n <= 1: return mask
    main = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    size = max(st[main, cv2.CC_STAT_WIDTH], st[main, cv2.CC_STAT_HEIGHT])
    dist = cv2.distanceTransform((lab != main).astype(np.uint8), cv2.DIST_L2, 5)
    keep = np.zeros(n, bool); keep[main] = True
    for i in range(1, n):
        if i == main or st[i, cv2.CC_STAT_AREA] < s['min_speck'] * st[main, cv2.CC_STAT_AREA]: continue
        if dist[lab == i].min() <= s['speck_distance'] * size: keep[i] = True
    return keep[lab]


def prepare(rgb: np.ndarray, sheet: dict) -> tuple[np.ndarray, np.ndarray, dict]:
    """(cropped image, ink mask as uint8 0/255, report) for one freeform glyph."""
    s = {**DEFAULTS, **{k: v for k, v in sheet.items() if k in DEFAULTS}}
    if s['rotate']:
        h, w = rgb.shape[:2]
        M = cv2.getRotationMatrix2D((w / 2, h / 2), s['rotate'], 1.0)
        rgb = cv2.warpAffine(rgb, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    if 'corners' in sheet:                                  # four points, clockwise from top left
        src = np.float32(sheet['corners']).reshape(4, 2)
        w = int(max(np.linalg.norm(src[1] - src[0]), np.linalg.norm(src[2] - src[3])))
        h = int(max(np.linalg.norm(src[3] - src[0]), np.linalg.norm(src[2] - src[1])))
        M = cv2.getPerspectiveTransform(src, np.float32([(0, 0), (w, 0), (w, h), (0, h)]))
        rgb = cv2.warpPerspective(rgb, M, (w, h), flags=cv2.INTER_CUBIC)
    mask, colour = ink_mask(rgb, s)
    mask = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)).astype(bool)
    mask = keep_near(mask, s)
    ys, xs = np.nonzero(mask)
    if not len(xs): raise ValueError('no ink found: set ink colour or raise the tolerance')
    pad = int(0.15 * max(np.ptp(xs), np.ptp(ys))) + 8
    y0, y1 = max(ys.min() - pad, 0), min(ys.max() + pad + 1, mask.shape[0])
    x0, x1 = max(xs.min() - pad, 0), min(xs.max() + pad + 1, mask.shape[1])
    return rgb[y0:y1, x0:x1], (mask[y0:y1, x0:x1] * 255).astype(np.uint8), dict(ink_rgb=colour, crop=[int(x0), int(y0), int(x1), int(y1)])
