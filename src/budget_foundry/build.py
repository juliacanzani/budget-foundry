"""Stages 4, 6, 7, 9, 10: normalise, trace, place, space, features, compile.

Normalisation here happens at build time on the kept candidates (as in v0); moving it
ahead of culling is Milestone 3. Kerning (stage 8) runs on an unkerned compile of the
same outlines, then the font is compiled again with the kern feature.
"""
from __future__ import annotations

import io
import json
import os
import sys

import cv2
import numpy as np
import potrace
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTFont

from . import features, imaging, kern, segment
from .project import Project, code_fp, fingerprint

FLAT_CAPS = 'EFHIKLTXZ'                 # cap height is measured on these
XHEIGHT_CHARS = 'acemnorsuvwxz'
DESC_C = 'gjpqyQ'                       # placed by their tops
ROUND_BOT = set('OCGSQUJ0368935ocesuvwg')  # overshoot below the baseline

DEFAULTS = dict(
    metrics=dict(upm=1000, cap=700, overshoot=12, ascender=900, descender=-300, space=260),
    normalise=dict(height_variation=0.5, scale_min=0.55, scale_max=1.7, weight_share=0.6,
                   weight_clip=[0.85, 1.15], bounce=0.5, bounce_clamp=25, dots={'.': 135, '…': 140}),
    trace=dict(smoothing=0.06, turdsize=4, alphamax=1.0, opttolerance=0.25),
    placement=dict(comma_top=1.1, semicolon_top=0.97, quote_above_cap=10, math_axis=0.52,
                   underscore_top=-70, slash_bottom=-0.04, at_bottom=-0.14),
    spacing=dict(depth=1.25, capitals=0.95, lowercase=0.80, figures=0.80, punctuation=0.55,
                 min_sidebearing=0.12, dot_sidebearing=0.35),
)


def settings(p: Project) -> dict:
    return {sec: {**v, **p.config.get(sec, {})} for sec, v in DEFAULTS.items()}


def stage_fp(p: Project) -> str:
    d = p.load_decisions()
    return fingerprint('build', code_fp(sys.modules[__name__], features, kern), segment.stage_fp(p), settings(p), p.config.get('targets', {}),
                       p.config.get('kern', {}), p.config.get('features', {}), p.charset,
                       {k: p.config.get(k) for k in ('name', 'style', 'font_version', 'vendor')},
                       d['glyphs'], d['overrides'])


# ---- targets

def resolve_targets(p: Project, cap, xh, os_):
    """[targets] maps a string of characters to a height: a number of units, or
    {ref = "cap" | "xheight", plus = units, overshoot = n} (n × overshoot added)."""
    out = {}
    for chars, v in p.config.get('targets', {}).items():
        if isinstance(v, dict):
            t = {'cap': cap, 'xheight': xh}[v['ref']] + v.get('plus', 0) + v.get('overshoot', 0) * os_
        else:
            t = v
        for c in chars: out[c] = t
    return out


def components_sorted(g, lab):
    """Component labels of a candidate, left to right, ignoring specks."""
    x, y, w, h = g['x'], g['y'], g['w'], g['h']
    out = []
    for c in g['ids']:
        ys, xs = np.nonzero(lab[y:y + h, x:x + w] == c); out.append((xs.mean(), c, len(xs)))
    out = [o for o in out if o[2] > 0.3 * max(q[2] for q in out)]
    return [c for _, c, _ in sorted(out)]


def picks_from(decisions: dict) -> tuple[dict, dict]:
    """(drawn: ch -> [candidate ids, default first], refs: ch -> ['id#component', ...])."""
    drawn, refs = {}, {}
    for ch, e in decisions['glyphs'].items():
        keep = list(e['keep'])
        if e.get('default') in keep:
            keep.remove(e['default']); keep.insert(0, e['default'])
        if not keep: continue
        (refs if '#' in keep[0] else drawn)[ch] = keep
    return drawn, refs


class Builder:
    def __init__(self, p: Project, log=print):
        self.p, self.log = p, log
        self.s = settings(p)
        self.cands, index = segment.load(p)
        self.SW = index['sheet_stroke']
        self.decisions = p.load_decisions()
        self.picks, self.refs = picks_from(self.decisions)
        missing = [i for ids in self.picks.values() for i in ids if i not in self.cands]
        missing += [r.split('#')[0] for rs in self.refs.values() for r in rs if r.split('#')[0] not in self.cands]
        if missing:
            raise RuntimeError(f'{len(missing)} kept candidates no longer exist (relabelled or re-segmented): {missing[:8]}')
        sheets = {self.cands[i]['sheet'] for ids in [*self.picks.values(), *[[r.split('#')[0] for r in rs] for rs in self.refs.values()]] for i in ids}
        self.labs = {k: imaging.load_labels(p, k) for k in p.sheet_keys if k in sheets}
        for ch, spec in p.charset.get('derived', {}).items():
            if spec.get('method') != 'component' or ch in self.refs or spec['from'] not in self.picks: continue
            n = 0 if spec.get('half', 'left') == 'left' else -1
            refs = [f'{i}#{n}' for i in self.picks[spec['from']] if self._splits(i)]
            if not refs:   # no kept one was written in two strokes: try the other candidates
                others = sorted((c for c in self.cands.values() if c['ch'] == spec['from']), key=lambda c: c.get('score', 0))
                refs = [f"{c['id']}#{n}" for c in others if self._splits(c['id'])][:1]
            if refs: self.refs[ch] = refs

    def _splits(self, i):
        k = self.cands[i]['sheet']
        if k not in self.labs: self.labs[k] = imaging.load_labels(self.p, k)
        return len(self.components_sorted(i)) >= 2

    # ---- measurement in stroke widths
    def top_sw(self, i): g = self.cands[i]; return (g['base'] - g['y']) / self.SW[g['sheet']]
    def bot_sw(self, i): g = self.cands[i]; return (g['base'] - (g['y'] + g['h'])) / self.SW[g['sheet']]
    def hu(self, i): g = self.cands[i]; return g['h'] * self.U / self.SW[g['sheet']]

    def normalise(self):
        m, n = self.s['metrics'], self.s['normalise']
        P = self.picks
        self.UPM, self.CAP, self.OS = m['upm'], m['cap'], m['overshoot']
        cap_sw = np.median([self.top_sw(i) - self.bot_sw(i) for c in FLAT_CAPS if c in P for i in P[c]])
        self.U = self.CAP / cap_sw                                   # font units per stroke width
        self.XH = np.median([self.top_sw(i) - self.bot_sw(i) for c in XHEIGHT_CHARS if c in P for i in P[c]]) * self.U
        self.log(f'  stroke={self.U:.0f}u x-height={self.XH:.0f}u')
        TGT = resolve_targets(self.p, self.CAP, self.XH, self.OS)
        self.FACT = {}
        for ch, ids in P.items():
            if ch not in TGT: continue
            med = np.median([self.hu(i) for i in ids])
            for i in ids:
                T = TGT[ch] * (self.hu(i) / med) ** n['height_variation']
                sw = self.U
                self.FACT[i] = float(np.clip((T - sw) / (self.hu(i) - sw), n['scale_min'], n['scale_max']))
        self.DOTS = n['dots']
        for ch, T0 in self.DOTS.items():
            if ch not in P: continue
            med = np.median([self.hu(i) for i in P[ch]])
            for i in P[ch]: self.FACT[i] = T0 * (self.hu(i) / med) ** n['height_variation'] / self.hu(i)

    def mask_of(self, i, comp=None):
        g = self.cands[i]; k = g['sheet']; SWk = self.SW[k]; p = int(SWk)
        x, y, w, h = g['x'], g['y'], g['w'], g['h']
        lab = self.labs[k]; H, W = lab.shape
        x0, y0, x1, y1 = max(x - p, 0), max(y - p, 0), min(x + w + p, W), min(y + h + p, H)
        ids = g['ids'] if comp is None else [comp]
        m = np.isin(lab[y0:y1, x0:x1], ids).astype(np.float32)
        f = self.FACT.get(i, 1.0) if comp is None else 1.0
        n = self.s['normalise']; lo, hi = n['weight_clip']
        wt = 1 + n['weight_share'] * (float(np.clip(g['wt'], lo, hi)) - 1)
        # keep the pen weight through scaling: dilate/erode by stroke × (1/f − wt) / 2
        r = 0 if g['ch'] in self.DOTS else SWk * (1 / f - wt) / 2
        if abs(r) >= 1:
            m = np.pad(m, int(abs(r)) + 2); x0 -= int(abs(r)) + 2; y0 -= int(abs(r)) + 2
            ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * int(round(abs(r))) + 1,) * 2)
            m = (cv2.dilate if r > 0 else cv2.erode)(m, ker)
        m = cv2.GaussianBlur(m, (0, 0), SWk * self.s['trace']['smoothing']) > 0.5
        return m, x0, y0, f

    def components_sorted(self, i):
        return components_sorted(self.cands[i], self.labs[self.cands[i]['sheet']])

    def trace(self):
        t = self.s['trace']
        # (glyph char, slot, candidate id, component label or None, source ref)
        sources = [(ch, s, i, None, i) for ch, ids in self.picks.items() for s, i in enumerate(ids)]
        for ch, rs in self.refs.items():
            for s, r in enumerate(rs):
                i, n = r.split('#'); sources.append((ch, s, i, self.components_sorted(i)[int(n)], r))
        self.G = {}
        for ch, s, i, comp, ref in sources:
            g = self.cands[i]; k = g['sheet']; m, x0, y0, fs = self.mask_of(i, comp)
            pad = 4
            plist = potrace.Bitmap(~np.pad(m, pad)).trace(turdsize=int(t['turdsize']), alphamax=t['alphamax'],
                                                          opticurve=True, opttolerance=t['opttolerance'])
            kpx = self.U / self.SW[k] * fs
            ys, xs = np.nonzero(m)
            def tx(pt, x0=x0, y0=y0, kpx=kpx, base=g['base']):
                return ((pt.x - pad + x0) * kpx, (base - (pt.y - pad + y0)) * kpx)
            contours = []
            for c in plist:
                segs = []
                for sg in c.segments:
                    if sg.is_corner: segs.append(('L', tx(sg.c))); segs.append(('L', tx(sg.end_point)))
                    else: segs.append(('C', tx(sg.c1), tx(sg.c2), tx(sg.end_point)))
                contours.append((tx(c.start_point), segs))
            rows_u = (g['base'] - (np.arange(m.shape[0]) + y0)) * kpx
            left = np.array([(np.nonzero(r)[0].min() + x0) * kpx if r.any() else np.nan for r in m])
            right = np.array([(np.nonzero(r)[0].max() + x0) * kpx if r.any() else np.nan for r in m])
            self.G[(ch, s)] = dict(contours=contours, xmin=(xs.min() + x0) * kpx, xmax=(xs.max() + x0) * kpx,
                                   ymax=(g['base'] - (ys.min() + y0)) * kpx, ymin=(g['base'] - (ys.max() + y0)) * kpx,
                                   rows=rows_u, left=left, right=right, dy=0.0, src=ref)

    def place(self):
        G, CAP, XH, OS = self.G, self.CAP, self.XH, self.OS
        n, pl = self.s['normalise'], self.s['placement']
        classof = lambda ch: [G[(c, s)] for (c, s) in G if c == ch]
        def place_bottom(ch, t):
            for g in classof(ch): g['dy'] = t - g['ymin']
        def place_top(ch, t):
            for g in classof(ch): g['dy'] = t - g['ymax']
        def place_center(ch, t):
            for g in classof(ch): g['dy'] = t - (g['ymin'] + g['ymax']) / 2
        b, bc = n['bounce'], n['bounce_clamp']
        for ch in self.picks:
            gs = classof(ch)
            if ch.isalnum() and ch not in DESC_C:
                m = np.median([g['ymin'] for g in gs]); t = -OS if ch in ROUND_BOT else 0
                for g in gs: g['dy'] = t - g['ymin'] + float(np.clip(b * (g['ymin'] - m), -bc, bc))
            elif ch == 'j':                       # align to the i, keep some bounce
                itop = np.median([q['ymax'] for q in classof('i')]); m = np.median([q['ymax'] for q in gs])
                for g in gs: g['dy'] = itop - m - b * (g['ymax'] - m)
            elif ch in 'gpqy':                    # bowl top on the x-height
                m = np.median([g['ymax'] for g in gs])
                for g in gs: g['dy'] = XH + OS - m - b * (g['ymax'] - m)
            elif ch in DESC_C:                    # Q: top on the cap height
                d = CAP - np.median([q['ymax'] for q in gs])
                for g in gs: g['dy'] = d
        self.DOT = np.median([g['ymax'] - g['ymin'] for g in classof('.')])
        self.DESC = -np.median([g['ymin'] + g['dy'] for c in 'gpqy' for g in classof(c)])
        for ch in '.…!?%#&:': place_bottom(ch, 0)
        place_top(',', self.DOT * pl['comma_top']); place_top(';', XH * pl['semicolon_top'])
        for ch in ["'", '"', '“', '”', '‘', '’', '*']: place_top(ch, CAP + pl['quote_above_cap'])
        self.AX = XH * pl['math_axis']
        for ch in '-–—~+=×÷<>«»': place_center(ch, self.AX)
        place_top('_', pl['underscore_top'])
        for ch in '()[]{}|': place_center(ch, (CAP - self.DESC) / 2)
        for ch in '/\\': place_bottom(ch, pl['slash_bottom'] * CAP)
        place_bottom('@', pl['at_bottom'] * CAP)
        nudges = self.decisions['overrides']['baseline']
        for g in G.values():
            g['dy'] += nudges.get(g['src'], 0)
            g['ymin'] += g['dy']; g['ymax'] += g['dy']; g['rows'] = g['rows'] + g['dy']

    def space(self):
        """White-area spacing per side (HT Letterspacer style), targets in stroke widths."""
        sp, U, XH, CAP = self.s['spacing'], self.U, self.XH, self.CAP
        D = sp['depth'] * U
        def zone(ch, g):
            if ch.islower(): return (0, XH)
            if ch.isupper() or ch.isdigit(): return (0, CAP)
            return (g['ymin'], g['ymax'])
        def side(g, ch, which):
            z0, z1 = zone(ch, g); sel = (g['rows'] >= z0) & (g['rows'] <= z1)
            prof = g['left'][sel] - g['xmin'] if which == 'L' else g['xmax'] - g['right'][sel]
            prof = np.where(np.isnan(prof), D, np.minimum(prof, D))
            return float(prof.mean()) if prof.size else D
        def target(ch):
            if ch.isupper(): return sp['capitals'] * U
            if ch.islower(): return sp['lowercase'] * U
            if ch.isdigit(): return sp['figures'] * U
            return sp['punctuation'] * U
        for (ch, s), g in self.G.items():
            T = target(ch)
            g['lsb'] = max(T - side(g, ch, 'L'), sp['min_sidebearing'] * U)
            g['rsb'] = max(T - side(g, ch, 'R'), sp['min_sidebearing'] * U)
            if ch in '.,:;…!': g['lsb'] = g['rsb'] = max(g['lsb'], sp['dot_sidebearing'] * U)
            g['adv'] = round(g['lsb'] + (g['xmax'] - g['xmin']) + g['rsb'])

    # ---- glyphs
    @staticmethod
    def drawer(contours, P):
        def f(pen):
            for st, segs in contours:
                pen.moveTo(P(st))
                for sg in segs:
                    if sg[0] == 'L': pen.lineTo(P(sg[1]))
                    else: pen.curveTo(P(sg[1]), P(sg[2]), P(sg[3]))
                pen.closePath()
        return f

    def glyph_table(self):
        G, U = self.G, self.U
        self.glyphs = {}; self.nvar = {}
        for (ch, s), g in G.items():
            ox, dy = g['lsb'] - g['xmin'], g['dy']
            P = lambda q, ox=ox, dy=dy: (round(q[0] + ox), round(q[1] + dy))
            self.glyphs[features.gname(ch, s)] = (g['adv'], self.drawer(g['contours'], P)); self.nvar[ch] = max(self.nvar.get(ch, 0), s + 1)
        for ch, spec in self.p.charset.get('derived', {}).items():
            if spec.get('method') != 'scale' or (spec['from'], 0) not in G: continue
            g = G[(spec['from'], 0)]; scale = spec.get('scale', 1.0)
            cy = {'axis': self.AX}.get(spec.get('centre', 'axis'), spec.get('centre'))
            cx = (g['xmin'] + g['xmax']) / 2; mid = (g['ymin'] + g['ymax']) / 2
            w = (g['xmax'] - g['xmin']) * scale; lsb = 0.5 * U; dyb = g['dy']
            P = lambda q, cx=cx, mid=mid, w=w, lsb=lsb, dyb=dyb, scale=scale, cy=cy: (
                round((q[0] - cx) * scale + lsb + w / 2), round((q[1] + dyb - mid) * scale + cy))
            self.glyphs[features.gname(ch, 0)] = (round(w + 2 * lsb), self.drawer(g['contours'], P)); self.nvar[ch] = 1
        sv = self.p.config.get('features', {}).get('space_variants', 3)
        space = self.s['metrics']['space']
        for s in range(sv): self.glyphs['space' if s == 0 else f'space.alt{s}'] = (space, lambda pen: None)
        self.glyphs['.notdef'] = (500, lambda pen: (pen.moveTo((50, 0)), pen.lineTo((450, 0)), pen.lineTo((450, 700)), pen.lineTo((50, 700)), pen.closePath()))
        head = ['.notdef'] + ['space' if s == 0 else f'space.alt{s}' for s in range(sv)]
        self.order = head + sorted(n for n in self.glyphs if n not in head)
        self.cmap = {32: 'space', 0xA0: 'space'}
        for ch in self.nvar: self.cmap[ord(ch)] = features.gname(ch, 0)
        self.space_variants = sv

    def compile(self, fea: str) -> TTFont:
        cfg, m = self.p.config, self.s['metrics']
        fam, style = cfg['name'], cfg.get('style', 'Regular'); ps = self.p.ps_name
        fb = FontBuilder(self.UPM, isTTF=False)
        fb.setupGlyphOrder(self.order); fb.setupCharacterMap(self.cmap)
        cs, adv, lsbs = {}, {}, {}; ymax = ymin = 0
        for n in self.order:
            a, f = self.glyphs[n]; pen = T2CharStringPen(a, None); f(pen); cs[n] = pen.getCharString(); adv[n] = a
            bp = BoundsPen(None); f(bp); b = bp.bounds
            lsbs[n] = b[0] if b else 0
            if b: ymax = max(ymax, b[3]); ymin = min(ymin, b[1])
        fb.setupCFF(ps, {'FullName': fam}, cs, {})
        fb.setupHorizontalMetrics({n: (adv[n], round(lsbs[n])) for n in self.order})
        self.win = (round(ymax) + 10, round(ymin) - 10)
        fb.setupHorizontalHeader(ascent=m['ascender'], descent=m['descender'], lineGap=0)
        ver = cfg.get('font_version', '1.000')
        fb.setupNameTable({'familyName': fam, 'styleName': style, 'uniqueFontIdentifier': f'{ps}-{float(ver):.1f}',
                           'psName': ps, 'version': f'Version {ver}'})
        fb.setupOS2(sTypoAscender=m['ascender'], sTypoDescender=m['descender'], sTypoLineGap=0,
                    usWinAscent=self.win[0], usWinDescent=-self.win[1], sxHeight=round(self.XH), sCapHeight=self.CAP,
                    fsSelection=0x40 | 0x80, achVendID=cfg.get('vendor', 'NONE'))
        fb.setupPost()
        addOpenTypeFeaturesFromString(fb.font, fea)
        buf = io.BytesIO(); fb.save(buf); buf.seek(0)
        return TTFont(buf)

    def extremes(self):
        ext = []
        for n in self.order:
            bp = BoundsPen(None); self.glyphs[n][1](bp)
            if bp.bounds: ext.append((bp.bounds[3], bp.bounds[1], n))
        return ext


def run(p: Project, log=print) -> dict:
    b = Builder(p, log)
    b.normalise(); b.trace(); b.place(); b.space(); b.glyph_table()
    out = p.build_dir; out.mkdir(parents=True, exist_ok=True)
    base_fea = features.generate(b.nvar, b.space_variants)
    unkerned = b.compile(base_fea)
    kfea, kinfo = kern.generate(unkerned, round(b.U), p.config.get('kern', {}), p.load_decisions()['overrides'])
    fea = base_fea + '\n' + kfea
    font = b.compile(fea)
    (out / 'features.fea').write_text(fea)
    (out / 'kern.fea').write_text(kfea)
    otf = out / f'{p.ps_name}.otf'; woff2 = out / f'{p.ps_name}.woff2'
    font.save(otf)
    w = TTFont(otf); w.flavor = 'woff2'; w.save(woff2)
    (out / 'spacing.json').write_text(json.dumps(
        {f'{c}|{s}': dict(lsb=round(g['lsb']), rsb=round(g['rsb']), adv=g['adv'], src=g['src']) for (c, s), g in b.G.items()},
        ensure_ascii=False))
    ext = b.extremes()
    metrics = dict(stroke=b.U, xheight=b.XH, cap=b.CAP, descender=b.DESC, dot=b.DOT, math_axis=b.AX,
                   win_ascent=b.win[0], win_descent=b.win[1], glyphs=len(b.order), kern_pairs=kinfo['pairs'],
                   otf_bytes=os.path.getsize(otf), woff2_bytes=os.path.getsize(woff2),
                   tallest=sorted(ext)[-4:], deepest=sorted(ext, key=lambda e: e[1])[:4])
    (out / 'metrics.json').write_text(json.dumps(metrics, indent=1, ensure_ascii=False))
    p.mark_stage(out, stage_fp(p), otf=otf.name, woff2=woff2.name)
    log(f'  {len(b.order)} glyphs, {kinfo["pairs"]} kern pairs, otf {metrics["otf_bytes"]:,} B, woff2 {metrics["woff2_bytes"]:,} B')
    return metrics
