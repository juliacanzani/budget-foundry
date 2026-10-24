"""Stage 3, segment and label: components -> labelled candidates with metrics, tiles and scores.

Markerless sheets are labelled from a layout in decisions.json: per region, horizontal
bands (one per written row) and per row a spec of (char, count[, groups_per_glyph]).
`SKIP` drops groups. A row whose group count disagrees with its spec is reported and
skipped, never guessed.
"""
from __future__ import annotations

import base64
import json
import math

import cv2
import numpy as np
from skimage.morphology import skeletonize

from . import imaging, template
import sys

from .project import Project, candidate_id, code_fp, fingerprint

SEG_DEFAULTS = dict(min_stroke=0, min_area=400, stroke_floor=0)
# Glyphs whose bottoms don't sit on the baseline; excluded from the row baseline fit.
DESCENDS = set('gjpqy,;()[]{}_|Q')
XHEIGHT_CHARS = 'acemnorsuvwxz'
XTOP_DESCENDERS = set('gpqy')   # descenders whose top sits on the x-height
TILE = dict(px_per_stroke=13, above=10.5, below=5.0, pad=0.4)
SCORE_DEFAULTS = dict(flag_percentile=90, keep_frequent=4, keep_rare=2, keep=3, frequent='eaonsti',
                      rare='[]{}|_#@×÷…;“”«»%*\\/')
FULL = (0, 99999)


def sheet_settings(p: Project, key: str) -> dict:
    return {**SEG_DEFAULTS, **{k: v for k, v in p.sheet(key).items() if k in SEG_DEFAULTS}}


def score_settings(p: Project) -> dict:
    return {**SCORE_DEFAULTS, **p.config.get('score', {})}


def stage_fp(p: Project) -> str:
    d = p.load_decisions()
    return fingerprint('segment', code_fp(sys.modules[__name__]), [imaging.stage_fp(p, k) for k in p.sheet_keys],
                       {k: sheet_settings(p, k) for k in p.sheet_keys}, p.config.get('segment', {}),
                       score_settings(p), d['layout'], d['labels'])


# ---- grouping

def row_groups(comps, s, bands, xr=FULL):
    """Components in each band, merged into glyph groups by horizontal overlap (i, j, !, ?, ÷)."""
    cs = [dict(c) for c in comps if c['sw'] >= s['min_stroke'] and c['a'] >= s['min_area']
          and xr[0] <= c['x'] + c['w'] / 2 < xr[1]]
    rows = [[] for _ in bands[:-1]]
    for c in cs:
        cy = c['y'] + c['h'] / 2
        for i in range(len(bands) - 1):
            if bands[i] <= cy < bands[i + 1]: rows[i].append(c)
    out = []
    for r in rows:
        r.sort(key=lambda c: c['x'])
        groups = []
        for c in r:
            for g in groups[-3:]:
                x0 = max(g['x'], c['x']); x1 = min(g['x'] + g['w'], c['x'] + c['w'])
                if x1 - x0 > 0.5 * min(g['w'], c['w']):
                    nx = min(g['x'], c['x']); ny = min(g['y'], c['y'])
                    g['w'] = max(g['x'] + g['w'], c['x'] + c['w']) - nx; g['h'] = max(g['y'] + g['h'], c['y'] + c['h']) - ny
                    g['x'], g['y'] = nx, ny; g['ids'].append(c['id'])
                    break
            else:
                groups.append(dict(x=c['x'], y=c['y'], w=c['w'], h=c['h'], ids=[c['id']]))
        groups.sort(key=lambda g: g['x'])
        out.append(groups)
    return out


def label_region(key, comps, s, region, problems):
    bands = region['bands']; xr = tuple(region.get('x') or FULL)
    res = []
    for ri, (r, spec) in enumerate(zip(row_groups(comps, s, bands, xr), region['rows'])):
        spec = [t if len(t) == 3 else (t[0], t[1], 1) for t in spec]
        n = sum(c * m for _, c, m in spec)
        if n != len(r):
            problems.append(f'sheet {key} band {bands[ri]}–{bands[ri + 1]} x{list(xr)}: '
                            f'spec says {n} groups, found {len(r)} at x={[g["x"] for g in r]}')
            continue
        i = 0
        for ch, cnt, m in spec:
            for _ in range(cnt):
                if ch == 'SKIP': i += m; continue
                parts = r[i:i + m]; i += m
                x0 = min(q['x'] for q in parts); y0 = min(q['y'] for q in parts)
                res.append(dict(x=x0, y=y0, w=max(q['x'] + q['w'] for q in parts) - x0,
                                h=max(q['y'] + q['h'] for q in parts) - y0,
                                ids=sum([q['ids'] for q in parts], []), ch=ch, sheet=key,
                                row=f'{key}{xr[0]}-{bands[ri]}'))
    return res


# ---- template sheets

# Characters written as strokes side by side, which overlap-merging can't join.
# (Vertical stacks like i j ! ? : ; = ÷ already merge by overlap.)
MULTIPART = set('"“”„«»…%‰')


def merge_parts(groups, ch):
    """Join the strokes of one written glyph: split the row's gaps into small (inside a
    glyph) and large (between repeats) at the widest jump between sorted gaps, but only
    when they really are two kinds (small under half of large); strokes that already
    touched leave nothing to merge."""
    if ch not in MULTIPART or len(groups) < 2: return groups
    gaps = [b['x'] - (a['x'] + a['w']) for a, b in zip(groups, groups[1:])]
    srt = sorted(gaps)
    jumps = [(srt[i + 1] - srt[i], i) for i in range(len(srt) - 1)]
    if not jumps: return groups
    j, i = max(jumps)
    if srt[i] >= 0.5 * srt[i + 1]: return groups
    cut = (srt[i] + srt[i + 1]) / 2
    out = [dict(groups[0], ids=list(groups[0]['ids']))]
    for g, gap in zip(groups[1:], gaps):
        if gap < cut:
            o = out[-1]; nx, ny = min(o['x'], g['x']), min(o['y'], g['y'])
            o['w'] = max(o['x'] + o['w'], g['x'] + g['w']) - nx; o['h'] = max(o['y'] + o['h'], g['y'] + g['h']) - ny
            o['x'], o['y'] = nx, ny; o['ids'] += g['ids']
        else:
            out.append(dict(g, ids=list(g['ids'])))
    return out


def label_template(key, comps, sheet_sw, lay, n, ppm):
    """Every glyph in a row is a candidate for that row's character; the baseline is the
    printed guide, not a fitted line."""
    sh = lay['sheets'][n]; res = []
    min_area = 0.25 * sheet_sw ** 2                     # a pen dot is ~0.8 sw²; specks are smaller
    s = dict(min_stroke=0, min_area=min_area)
    for r in sh['rows']:
        bands = [r['top'] * ppm, r['bottom'] * ppm]
        (groups,) = row_groups(comps, s, bands, (r['x0'] * ppm, r['x1'] * ppm))
        for g in merge_parts(groups, r['char']):
            res.append(dict(g, ch=r['char'], sheet=key, row=f"{key}t{r['base']:.1f}", base=r['base'] * ppm))
    return res


# ---- baselines

def fit_baselines(allg, sheet_sw, xh_sw):
    rows = {}
    for g in allg: rows.setdefault(g['row'], []).append(g)
    for gs in rows.values():
        if all('base' in g for g in gs): continue      # template rows: the printed baseline
        if all(g['ch'] in XTOP_DESCENDERS for g in gs):
            # nothing sits on the baseline: hang it one x-height below the tops
            b = float(np.median([g['y'] for g in gs])) + xh_sw * sheet_sw[gs[0]['sheet']]
            for g in gs: g['base'] = b
            continue
        pts = [(g['x'] + g['w'] / 2, g['y'] + g['h']) for g in gs if g['ch'].isalnum() and g['ch'] not in DESCENDS]
        if len(pts) >= 3:
            xs, ys = np.array(pts).T; poly = np.polyfit(xs, ys, 1)
            for _ in range(2):
                r = ys - np.polyval(poly, xs); keep = np.abs(r) < max(2 * np.std(r), 5)
                if keep.sum() >= 3: poly = np.polyfit(xs[keep], ys[keep], 1)
            base = lambda x, poly=poly: float(np.polyval(poly, x))
        else:
            b = float(np.median([g['y'] + g['h'] for g in gs])); base = lambda x, b=b: b
        for g in gs: g['base'] = base(g['x'] + g['w'] / 2)


# ---- metrics and tiles

def measure(g, lab, dist, sw):
    x, y, w, h = g['x'], g['y'], g['w'], g['h']
    m = np.isin(lab[y:y + h, x:x + w], g['ids'])
    d = dist[y:y + h, x:x + w][skeletonize(m)]
    gsw = float(np.median(d) * 2) if d.size else sw
    ys_, xs_ = np.nonzero(m); xs_ = xs_ - xs_.mean(); ys_ = ys_ - ys_.mean()
    slant = float(np.degrees(np.arctan2(-(xs_ * ys_).mean(), (ys_ * ys_).mean()))) if h > w * 0.8 else None
    return dict(h_sw=round(h / sw, 2), w_sw=round(w / sw, 2), wt=round(gsw / sw, 3),
                top_sw=round((g['base'] - y) / sw, 2), bot_sw=round((y + h - g['base']) / sw, 2),
                slant=None if slant is None else round(slant, 1))


def tile(g, lab, sw):
    """Transparent PNG at a common scale, framed on the row baseline. The frame grows
    to fit tall or deep glyphs instead of clipping them."""
    x, y, w, h = g['x'], g['y'], g['w'], g['h']
    above = max(TILE['above'] * sw, g['base'] - y + 0.3 * sw)
    below = max(TILE['below'] * sw, y + h - g['base'] + 0.3 * sw)
    fy0 = int(round(g['base'] - above)); fy1 = int(round(g['base'] + below))
    pad = int(TILE['pad'] * sw); fx0 = x - pad; fx1 = x + w + pad
    H, W = lab.shape
    canvas = np.zeros((fy1 - fy0, fx1 - fx0), np.uint8)
    sy0, sy1 = max(fy0, 0), min(fy1, H); sx0, sx1 = max(fx0, 0), min(fx1, W)
    canvas[sy0 - fy0:sy1 - fy0, sx0 - fx0:sx1 - fx0] = np.isin(lab[sy0:sy1, sx0:sx1], g['ids']) * 255
    clipped = bool(canvas[0].any() or canvas[-1].any() or canvas[:, 0].any() or canvas[:, -1].any())
    s = TILE['px_per_stroke'] / sw
    small = cv2.resize(canvas, (max(1, int(canvas.shape[1] * s)), int(canvas.shape[0] * s)), interpolation=cv2.INTER_AREA)
    rgba = np.zeros(small.shape + (4,), np.uint8); rgba[..., 3] = small
    _, buf = cv2.imencode('.png', rgba, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    return buf.tobytes(), dict(tile_base=round((g['base'] - fy0) / (fy1 - fy0), 4), clipped=clipped)


def score(cands, s):
    """Score each candidate against the others of its character (the suggested keepers
    are the lowest scores), and flag the outer share across the whole font for size,
    weight, width, slant and bounce. Weight isn't judged on mostly horizontal glyphs
    (- – — _ = ~), where the skeleton measure is unreliable."""
    by = {}
    for g in cands: by.setdefault(g['ch'], []).append(g)
    dev = {k: [] for k in ('size', 'weight', 'width', 'slant', 'bounce')}
    for ch, gs in by.items():
        mh = np.median([g['h_sw'] for g in gs]); mb = np.median([g['bot_sw'] for g in gs])
        mw = np.median([g['w_sw'] for g in gs])
        sl = [g['slant'] for g in gs if g['slant'] is not None]; ms = np.median(sl) if sl else None
        for g in gs:
            size = g['h_sw'] / mh; rw = g['wt'] / size
            sd = g['slant'] - ms if ms is not None and g['slant'] is not None else None
            bd = g['bot_sw'] - mb
            sc = abs(math.log(size)) * 2 + abs(math.log(rw)) * 2 + (abs(sd) / 15 if sd is not None else 0) + abs(bd) / 3
            g.update(size=round(size, 2), rw=round(rw, 2), score=round(sc, 3), suggested=False, flags=[])
            g['_dev'] = dict(size=math.log(size), width=math.log(g['w_sw'] / mw),
                             weight=math.log(rw) if g['w_sw'] <= 2 * g['h_sw'] else None,
                             slant=sd, bounce=bd if ch.isalnum() else None)
            if len(gs) >= 3:
                for k, v in g['_dev'].items():
                    if v is not None: dev[k].append(abs(v))
        n = s['keep_frequent'] if ch in s['frequent'] else (s['keep_rare'] if ch in s['rare'] else s['keep'])
        for g in sorted(gs, key=lambda g: g['score'])[:n]: g['suggested'] = True
    cut = {k: float(np.percentile(v, s['flag_percentile'])) if v else math.inf for k, v in dev.items()}
    words = dict(size=('small', 'large'), weight=('light', 'heavy'), width=('narrow', 'wide'), bounce=('floats', 'drops'))
    for ch, gs in by.items():
        for g in gs:
            d = g.pop('_dev')
            if len(gs) < 3: continue
            for k, v in d.items():
                if v is None or abs(v) <= cut[k] or abs(v) < 1e-9: continue
                g['flags'].append(f"slant {'+' if v > 0 else '−'}{abs(v):.0f}°" if k == 'slant' else words[k][int(v > 0)])


# ---- stage

def run(p: Project, log=print) -> list[str]:
    """Returns the list of layout problems (rows whose counts don't match)."""
    d = p.load_decisions(); problems = []
    sheets = {k: imaging.load(p, k) for k in p.sheet_keys}
    srcsha = {k: sheets[k]['record']['source_sha256'] for k in p.sheet_keys}
    sheet_sw = {k: float(np.median([c['sw'] for c in sheets[k]['comps'] if c['sw'] > sheet_settings(p, k)['stroke_floor']]))
                if sheets[k]['comps'] else 0.0 for k in p.sheet_keys}
    lays = {lay['rev']: lay for lay in template.revisions(p)}
    ppm = imaging.settings(p)['px_per_mm']
    allg = []
    for k in p.sheet_keys:
        t = (sheets[k]['record'] or {}).get('template')
        if p.sheet(k).get('kind') == 'freeform':
            cs = sheets[k]['comps']
            if not cs: problems.append(f'sheet {k}: no ink found'); continue
            x0 = min(c['x'] for c in cs); y0 = min(c['y'] for c in cs)
            x1 = max(c['x'] + c['w'] for c in cs); y1 = max(c['y'] + c['h'] for c in cs)
            allg.append(dict(x=x0, y=y0, w=x1 - x0, h=y1 - y0, ids=[c['id'] for c in cs], ch=p.sheet(k)['char'],
                             sheet=k, row=f'{k}free', base=float(p.sheet(k).get('baseline', y1))))
        elif t and t['kind'] == 'chars':
            allg += label_template(k, sheets[k]['comps'], sheet_sw[k], lays[t['rev']], t['sheet'], ppm)
        elif t:
            log(f'  sheet {k}: {t["kind"]} page, kept for reference (harvesting comes with ligatures)')
        else:
            s = sheet_settings(p, k)
            for region in d['layout'].get(k, []):
                allg += label_region(k, sheets[k]['comps'], s, region, problems)
    xh_sheets = p.config.get('segment', {}).get('xheight_sheets', p.sheet_keys)
    xh = [g['h'] / sheet_sw[g['sheet']] for g in allg if g['sheet'] in xh_sheets and g['ch'] in XHEIGHT_CHARS]
    xh_sw = float(np.median(xh)) if xh else float('nan')   # only rows of g p q y alone need it
    fit_baselines(allg, sheet_sw, xh_sw)

    out = p.candidates_dir; out.mkdir(parents=True, exist_ok=True)
    for f in out.glob('*'):
        if f.suffix in ('.json', '.png'): f.unlink()
    cands = []; seen = set()
    for k in p.sheet_keys:
        lab = imaging.load_labels(p, k)
        ink = cv2.imread(str(sheets[k]['ink_path']), 0)
        dist = cv2.distanceTransform(ink, cv2.DIST_L2, 5)
        for g in (g for g in allg if g['sheet'] == k):
            cid = candidate_id(srcsha[k], g['x'], g['y'], g['w'], g['h'])
            if cid in seen: raise RuntimeError(f'duplicate candidate id {cid} on sheet {k}')
            seen.add(cid)
            ch = d['labels'].get(cid, g['ch'])
            if not ch: continue                       # relabelled to "" = dropped
            png, tinfo = tile(g, lab, sheet_sw[k])
            (out / f'{cid}.png').write_bytes(png)
            cands.append(dict(id=cid, ch=ch, sheet=k, ids=g['ids'], x=g['x'], y=g['y'], w=g['w'], h=g['h'],
                              base=g['base'], row=g['row'], **measure(g, lab, dist, sheet_sw[k]), **tinfo))
    score(cands, score_settings(p))
    for c in cands:
        (out / f"{c['id']}.json").write_text(json.dumps(c, ensure_ascii=False))
    index = dict(order=[c['id'] for c in cands], sheet_stroke=sheet_sw, xheight_strokes=xh_sw)
    (out / '_index.json').write_text(json.dumps(index))
    p.mark_stage(out, stage_fp(p), candidates=len(cands), problems=problems)
    for msg in problems: log('  ! ' + msg)
    log(f'  {len(cands)} candidates across {len({c["ch"] for c in cands})} characters')
    return problems


def load(p: Project) -> tuple[dict, dict]:
    """(candidates by id in segmentation order, index)."""
    d = p.candidates_dir
    index = json.loads((d / '_index.json').read_text())
    cands = {i: json.loads((d / f'{i}.json').read_text()) for i in index['order'] if (d / f'{i}.json').exists()}
    return cands, index


def tile_b64(p: Project, cid: str) -> str:
    return base64.b64encode((p.candidates_dir / f'{cid}.png').read_bytes()).decode()
