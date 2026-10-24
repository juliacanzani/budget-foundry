"""HarfBuzz shaping, so checks see what Chrome and Firefox will do."""
from __future__ import annotations

from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont
from PIL import Image, ImageChops, ImageDraw

# Varied prose that never repeats: a repeated sentence replays the same contexts and
# can hide or invent a starved variant. Projects can set [checks] corpus.
CORPUS = (
    'Some thoughts on making things by hand, and why they are worth it. The quick brown fox jumped over '
    'the lazy dog. Notes from the kitchen: what is on the menu this week, and what to do with the last of '
    'the tomatoes before the frost. A letter is a small house for a thought; you build it once, and then '
    'other people live in it. When the light goes early in October, the garden turns to seed heads and '
    'the robins come back for the rowan berries. Bring a pencil, a ruler and a little patience. Write each '
    'letter eight times, then choose the three that feel most like your hand on a good day. Nobody minds '
    'if the second one wobbles; that wobble is the point. The bookshop on the corner keeps a shelf of old '
    'atlases, their oceans faded to the colour of weak tea. Six jugglers quietly fixed the broken '
    'velvet zip. Pack my box with five dozen liquor jugs. Morning pages, three of them, before anything '
    'else: no editing, no rereading, only the pen moving across the paper until the timer goes. Then '
    'coffee, then the inbox, then the long walk to the river and back again by the mill.'
)
DOUBLES = 'eeee oooo llll tttt ssss bookkeeper Mississippi coffee little better committee balloon'


class Shaper:
    def __init__(self, font_path: str | Path):
        self.path = str(font_path)
        self.font = hb.Font(hb.Face(hb.Blob.from_file_path(self.path)))
        self.tt = TTFont(self.path)
        self.order = self.tt.getGlyphOrder()

    def shape(self, text, features=None):
        buf = hb.Buffer(); buf.add_str(text); buf.guess_segment_properties()
        hb.shape(self.font, buf, features or {})
        return [self.order[g.codepoint] for g in buf.glyph_infos], buf.glyph_positions

    def slots(self, text, features=None):
        names, _ = self.shape(text, features)
        return [int(n.split('.alt')[1]) if '.alt' in n else 0 for n in names], names


class Poly(BasePen):
    def __init__(s, gs): super().__init__(gs); s.polys = []; s.cur = []
    def _moveTo(s, p): s.cur = [p]
    def _lineTo(s, p): s.cur.append(p)
    def _curveToOne(s, a, b, c):
        p0 = s.cur[-1]
        for t in [i / 12 for i in range(1, 13)]:
            mt = 1 - t
            s.cur.append((mt ** 3 * p0[0] + 3 * mt * mt * t * a[0] + 3 * mt * t * t * b[0] + t ** 3 * c[0],
                          mt ** 3 * p0[1] + 3 * mt * mt * t * a[1] + 3 * mt * t * t * b[1] + t ** 3 * c[1]))
    def _closePath(s): s.polys.append(s.cur); s.cur = []


def render_line(sh: Shaper, text, size=90, features=None, guides=None):
    gs = sh.tt.getGlyphSet(); upm = sh.tt['head'].unitsPerEm
    names, pos = sh.shape(text, features)
    sc = size / upm; W = int(sum(p.x_advance for p in pos) * sc) + 40; H = int(size * 1.6); base = int(size * 1.1)
    img = Image.new('L', (W, H), 0); x = 20
    for n, p in zip(names, pos):
        pen = Poly(gs); gs[n].draw(pen)
        m = Image.new('1', (W, H), 0)
        for poly in pen.polys:
            if len(poly) < 3: continue
            t = Image.new('1', (W, H), 0)
            ImageDraw.Draw(t).polygon([(x + px * sc, base - py * sc) for px, py in poly], fill=1)
            m = ImageChops.logical_xor(m, t)
        img = ImageChops.lighter(img, m.convert('L')); x += p.x_advance * sc
    out = Image.new('RGB', (W, H), 'white'); d = ImageDraw.Draw(out)
    for y, c in (guides or []):
        d.line([(0, base - y * sc), (W, base - y * sc)], fill=c)
    out.paste((0, 0, 0), mask=img)
    return out


def render_sheet(font_path, lines, out_path, size=90):
    sh = Shaper(font_path); os2 = sh.tt['OS/2']
    guides = [(0, (120, 160, 220)), (os2.sxHeight, (230, 200, 120)), (os2.sCapHeight, (230, 200, 120))]
    ims = [render_line(sh, t, size, guides=guides) for t in lines]
    W = max(i.width for i in ims); H = sum(i.height for i in ims)
    o = Image.new('RGB', (W, H), 'white'); y = 0
    for i in ims: o.paste(i, (0, y)); y += i.height
    o.thumbnail((1900, 4000)); o.save(out_path)
