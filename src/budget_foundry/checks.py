"""Automated checks. Every build runs them; a failure blocks export, not preview.
Each one exists because of a bug that was only caught by looking at output."""
from __future__ import annotations

import json
import re
from collections import Counter

from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont

from . import kern, segment
from .build import picks_from
from .project import Project
from .shaping import CORPUS, DOUBLES, Shaper

NAME_RE = re.compile(r'^(\.notdef|space(\.alt\d+)?|uni[0-9A-F]{4}(\.alt\d+)?)$')


def charset_chars(p: Project) -> list[str]:
    return list(p.charset.get('drawn', '')) + list(p.charset.get('derived', {}))


def run(p: Project) -> list[dict]:
    otf = p.build_dir / f'{p.ps_name}.otf'; woff2 = p.build_dir / f'{p.ps_name}.woff2'
    tt = TTFont(otf); gs = tt.getGlyphSet(); order = tt.getGlyphOrder(); cmap = tt.getBestCmap()
    cfg = p.config.get('checks', {})
    corpus = cfg.get('corpus', CORPUS)
    res = []
    def add(name, ok, detail, warn=False):
        res.append(dict(check=name, status='pass' if ok else ('warn' if warn else 'fail'), detail=detail))

    # non-empty glyphs (shared row baselines once blanked q, dashes, brackets)
    empty = []
    for n in order:
        if n == '.notdef' or n.startswith('space'): continue
        bp = BoundsPen(gs); gs[n].draw(bp)
        if bp.bounds is None: empty.append(n)
    add('Non-empty glyphs', not empty, f'{len(empty)} empty: {empty[:10]}' if empty else f'{len(order)} glyphs have ink')

    # unclipped tiles (the long-tailed y and two # were cut off in the culling sheet)
    cands, _ = segment.load(p)
    drawn, refs = picks_from(p.load_decisions())
    kept = {i for ids in drawn.values() for i in ids} | {r.split('#')[0] for rs in refs.values() for r in rs}
    clipped = [c['id'] for c in cands.values() if c.get('clipped')]
    add('Unclipped tiles', not clipped, f'{len(clipped)} tiles touch their frame: {clipped[:8]}' if clipped
        else f'{len(cands)} candidate tiles fit their frames')

    # coverage (missing square brackets)
    missing = [c for c in charset_chars(p) if ord(c) not in cmap]
    add('Coverage', not missing, f'missing {"".join(missing)}' if missing else f'{len(charset_chars(p))} charset characters in the cmap')

    # glyph names (an `in '.notdef'` substring test once named glyphs t and .)
    bad = [n for n in order if not NAME_RE.match(n)]
    bad += [f'{n}→U+{cp:04X}' for cp, n in cmap.items() if n.startswith('uni') and int(n[3:7], 16) != cp]
    add('Glyph names', not bad, f'bad: {bad[:10]}' if bad else 'production names, cmap consistent')

    # variant distribution (rand once overrode the cycle: default at 11%)
    sh = Shaper(otf)
    slots, names = sh.slots(corpus)
    nvar = Counter(n.split('.')[0] for n in order if n.startswith('uni'))
    by_n, per_char = {}, {}
    for ch, s, n in zip(corpus, slots, names):
        if ch == ' ' or not n.startswith('uni'): continue
        k = nvar[n.split('.')[0]]
        if k >= 2:
            by_n.setdefault(k, Counter())[s] += 1
            per_char.setdefault(ch, (k, Counter()))[1][s] += 1
    msgs, ok = [], True
    for k, cnt in sorted(by_n.items()):
        tot = sum(cnt.values())
        shares = [cnt[s] / tot for s in range(k)]
        lo, hi = 0.75 / k, 1.2 / k
        ok &= all(lo <= sh_ <= hi for sh_ in shares)
        msgs.append(f'{k} variants: ' + ' / '.join(f'{x:.0%}' for x in shares) + f' (want {lo:.0%}–{hi:.0%})')
    unused = [f'{ch} slot {s}' for ch, (k, cnt) in per_char.items() if sum(cnt.values()) >= 4 * k
              for s in range(k) if not cnt[s]]
    if unused: msgs.append('not shown in the sample corpus: ' + ', '.join(unused))
    add('Variant distribution', ok, '; '.join(msgs) or 'no alternates')

    # doubles: no glyph follows itself
    reps = []
    for word in DOUBLES.split():
        _, nm = sh.slots(word)
        reps += [f'{word}:{a}' for a, b in zip(nm, nm[1:]) if a == b]
    add('Doubles', not reps, f'repeats: {reps[:8]}' if reps else 'no repeated glyph in doubled letters')

    # vertical extremes
    m = json.loads((p.build_dir / 'metrics.json').read_text())
    cap, desc = m['cap'], m['descender']
    tall = [(n, round(b[3])) for n in order if (b := _bounds(gs, n)) and b[3] > 1.3 * cap]
    deep = [(n, round(b[1])) for n in order if (b := _bounds(gs, n)) and b[1] < -1.5 * desc]
    add('Vertical extremes', not tall and not deep,
        f'tallest {m["tallest"][-1][2]} {m["tallest"][-1][0]:.0f}u, deepest {m["deepest"][0][2]} {m["deepest"][0][1]:.0f}u'
        + (f'; beyond limits: {tall + deep}' if tall or deep else ''), warn=True)

    # collisions
    col = kern.collisions(tt, round(m['stroke']), p.config.get('kern', {}))
    add('Collisions', not col, f'{len(col)} kerned pairs overlap: {col[:6]}' if col else f'{m["kern_pairs"]} kerned pairs keep their gap')

    # size
    size = woff2.stat().st_size; limit = cfg.get('woff2_limit_kb', 80)
    add('Size', size < limit * 1000, f'WOFF2 {size / 1000:.1f} KB (limit {limit} KB)', warn=True)

    (p.build_dir / 'checks.json').write_text(json.dumps(res, indent=1, ensure_ascii=False))
    return res


def _bounds(gs, n):
    bp = BoundsPen(gs); gs[n].draw(bp); return bp.bounds
