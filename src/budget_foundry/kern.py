"""Stage 8, kern: profile-based, one class per character, averaged across its variants.

Each glyph is rasterised and blurred vertically into left/right profiles. A pair's
gap is compared with its reference pair (H H, n n, H n, or the punctuation itself):
tighter-than-reference pairs open by 30% of the difference, looser ones close by
60%, never closer than a minimum ink gap. Overrides in decisions.json pin a pair's
value or exclude it, and survive rebuilds.
"""
from __future__ import annotations

import cv2
import numpy as np
from fontTools.pens.basePen import BasePen
from PIL import Image, ImageChops, ImageDraw

DEFAULTS = dict(tighten=0.6, loosen=0.3, min_gap=0.22, max_loosen=0.3, threshold=30, step=5,
                blur=0.3, scale=0.25, top=1100, bottom=-400, skip=' ·•')


class Poly(BasePen):
    def __init__(s, g): super().__init__(g); s.polys = []; s.cur = []
    def _moveTo(s, p): s.cur = [p]
    def _lineTo(s, p): s.cur.append(p)
    def _curveToOne(s, a, b, c):
        p0 = s.cur[-1]
        for t in np.linspace(0.1, 1, 10):
            mt = 1 - t
            s.cur.append((mt ** 3 * p0[0] + 3 * mt * mt * t * a[0] + 3 * mt * t * t * b[0] + t ** 3 * c[0],
                          mt ** 3 * p0[1] + 3 * mt * mt * t * a[1] + 3 * mt * t * t * b[1] + t ** 3 * c[1]))
    def _closePath(s): s.polys.append(s.cur); s.cur = []


def kind(c): return 'U' if (c.isupper() or c.isdigit()) else ('L' if c.islower() else 'P')


class Profiles:
    def __init__(self, font, U, cfg):
        self.U, self.c = U, cfg
        self.gs = font.getGlyphSet(); self.hm = font['hmtx'].metrics
        self.chars = {}
        for n in font.getGlyphOrder():
            if n.startswith('uni'): self.chars.setdefault(chr(int(n[3:7], 16)), []).append(n)
        self.P = {n: self.profile(n) for c in self.chars for n in self.chars[c]}

    def profile(self, name):
        SC, Y0, Y1 = self.c['scale'], self.c['bottom'], self.c['top']; H = int((Y1 - Y0) * SC)
        VB = int(self.c['blur'] * self.U * SC)
        p = Poly(self.gs); self.gs[name].draw(p); W = int((self.hm[name][0] + 800) * SC)
        m = Image.new('1', (W, H), 0)
        for poly in p.polys:
            t = Image.new('1', (W, H), 0); ImageDraw.Draw(t).polygon([((x + 400) * SC, (Y1 - y) * SC) for x, y in poly], fill=1)
            m = ImageChops.logical_xor(m, t)
        a = cv2.dilate(np.array(m).astype(np.uint8), np.ones((2 * VB + 1, 1), np.uint8))
        L = np.full(H, np.nan); R = np.full(H, np.nan)
        for y in range(H):
            xs = np.nonzero(a[y])[0]
            if xs.size: L[y] = xs[0] / SC - 400; R[y] = xs[-1] / SC - 400
        return L, R, self.hm[name][0]

    def metric(self, a, b):
        """(mean gap capped at 4 strokes, minimum gap) over every variant pairing."""
        vals, mins = [], []
        for na in self.chars[a]:
            _, Ra, adv = self.P[na]
            for nb in self.chars[b]:
                Lb, _, _ = self.P[nb]; g = adv - Ra + Lb; ok = ~np.isnan(g)
                if ok.sum() < 4: return None, None
                vals.append(np.mean(np.minimum(g[ok], 4 * self.U))); mins.append(np.min(g[ok]))
        return float(np.mean(vals)), float(np.min(mins))


def compute(font, U, cfg=None):
    c = {**DEFAULTS, **(cfg or {})}
    pr = Profiles(font, U, c)
    rep = lambda ch: {'U': 'H', 'L': 'n'}.get(kind(ch), ch)
    REF = {}
    def ref(a, b):
        k = (rep(a), rep(b))
        if k not in REF: REF[k] = pr.metric(*k)[0]
        return REF[k]
    KC = [ch for ch in pr.chars if ch not in c['skip']]
    pairs = {}
    for a in KC:
        for b in KC:
            if kind(a) == 'P' and kind(b) == 'P': continue
            act, mn = pr.metric(a, b)
            if act is None: continue
            r = ref(a, b)
            if r is None: continue
            k = -c['tighten'] * (act - r) if act > r else -c['loosen'] * (act - r)
            k = max(k, c['min_gap'] * U - mn)          # never let ink collide
            k = min(k, c['max_loosen'] * U)
            k = int(round(k / c['step']) * c['step'])
            if abs(k) >= c['threshold']: pairs[(a, b)] = k
    return pairs, pr, KC


def generate(font, U, cfg, overrides) -> tuple[str, dict]:
    pairs, pr, KC = compute(font, U, cfg)
    for key in overrides.get('kern_exclude', []):
        pairs.pop((key[0], key[1]), None)
    for key, v in overrides.get('kern', {}).items():
        if key[0] in pr.chars and key[1] in pr.chars: pairs[(key[0], key[1])] = int(v)
    cls = {ch: '@k_' + '%04X' % ord(ch) for ch in pr.chars}
    used = set(x for p in pairs for x in p)
    lines = [f"{cls[ch]} = [{' '.join(pr.chars[ch])}];" for ch in KC if ch in used]
    lines += [f"{cls[ch]} = [{' '.join(pr.chars[ch])}];" for ch in pr.chars if ch in used and ch not in KC]
    lines.append("feature kern {\n  lookup kernpairs {")
    for (a, b), k in sorted(pairs.items(), key=lambda x: x[1]):
        lines.append(f"    pos {cls[a]} {cls[b]} {k};")
    lines.append("  } kernpairs;\n} kern;")
    return "\n".join(lines), dict(pairs=len(pairs))


def collisions(font, U, cfg=None) -> list[tuple[str, int, float]]:
    """Kerned pairs whose ink overlaps in some variant pairing: (pair, kern, min gap)."""
    c = {**DEFAULTS, **(cfg or {})}
    pr = Profiles(font, U, c)
    gpos_pairs = read_kern_pairs(font, pr)
    out = []
    for (a, b), k in gpos_pairs.items():
        _, mn = pr.metric(a, b)
        if mn is not None and mn + k < 0: out.append((a + b, k, round(mn + k, 1)))
    return out


def read_kern_pairs(font, pr) -> dict:
    """Class kern pairs back out of GPOS, as {(left char, right char): value}."""
    name2ch = {n: ch for ch, ns in pr.chars.items() for n in ns}
    out = {}
    if 'GPOS' not in font: return out
    for lk in font['GPOS'].table.LookupList.Lookup:
        for st in lk.SubTable:
            if getattr(st, 'Format', None) != 2 or lk.LookupType != 2: continue
            c1 = {}
            for g in st.Coverage.glyphs: c1.setdefault(st.ClassDef1.classDefs.get(g, 0), []).append(g)
            c2 = {}
            for g, v in st.ClassDef2.classDefs.items(): c2.setdefault(v, []).append(g)
            for i1, rec in enumerate(st.Class1Record):
                for i2, r2 in enumerate(rec.Class2Record):
                    v = getattr(r2.Value1, 'XAdvance', 0) if r2.Value1 else 0
                    if not v or i1 not in c1 or i2 not in c2: continue
                    a = name2ch.get(c1[i1][0]); b = name2ch.get(c2[i2][0])
                    if a and b: out[(a, b)] = v
    return out
