"""Stage 10 outputs beyond the font: specimen page, CSS snippet with a size-matched fallback, export."""
from __future__ import annotations

import base64
import html
import json
import shutil
from importlib import resources
from pathlib import Path

from fontTools.ttLib import TTFont

from .cull import ORDER
from .shaping import CORPUS

# Arial shares Helvetica's advance widths (per 1000 em); used to size-match the fallback.
ARIAL = dict(zip('abcdefghijklmnopqrstuvwxyz ', [556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833,
                                                   556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 278]))
DEFAULTS = dict(hero='Handwriting, set in type',
                samples=['The quick brown fox jumped over the lazy dog', 'Notes, drafts & half-finished ideas…',
                         'Hello! Bonjour! Hallo?'],
                sizes_text='Some thoughts on making things by hand, & why they’re worth it.')


def _settings(p):
    return {**DEFAULTS, **p.config.get('specimen', {})}


def fallback_metrics(tt: TTFont) -> dict:
    upm = tt['head'].unitsPerEm; cmap = tt.getBestCmap(); hm = tt['hmtx'].metrics
    text = [c for c in CORPUS.lower() if c in ARIAL and ord(c) in cmap]
    ours = sum(hm[cmap[ord(c)]][0] for c in text) / upm
    arial = sum(ARIAL[c] for c in text) / 1000
    adj = ours / arial
    hhea = tt['hhea']
    return dict(size_adjust=adj, ascent=hhea.ascent / upm / adj, descent=-hhea.descent / upm / adj)


def css(p, woff2_name: str, tt: TTFont) -> str:
    fam = p.config['name']; m = fallback_metrics(tt)
    return (f'@font-face {{\n  font-family: "{fam}";\n  src: url("{woff2_name}") format("woff2");\n  font-display: swap;\n}}\n\n'
            f'/* Arial resized to take the same line length and height, so the swap doesn\'t shift layout. */\n'
            f'@font-face {{\n  font-family: "{fam} Fallback";\n  src: local("Arial"), local("ArialMT");\n'
            f'  size-adjust: {m["size_adjust"]:.2%};\n  ascent-override: {m["ascent"]:.2%};\n'
            f'  descent-override: {m["descent"]:.2%};\n  line-gap-override: 0%;\n}}\n\n'
            f'/* font-family: "{fam}", "{fam} Fallback", cursive; */\n')


def page(p, tt: TTFont, woff2: Path) -> str:
    s = _settings(p); cmap = tt.getBestCmap(); order = set(tt.getGlyphOrder())
    chars = [c for c in ORDER if ord(c) in cmap] + [c for c in p.charset.get('derived', {}) if ord(c) in cmap and c not in ORDER]
    chars += [chr(cp) for cp in sorted(cmap) if chr(cp) not in chars and cp > 32 and cp != 0xA0]
    cells = []
    for c in chars:
        base = cmap[ord(c)]
        n = 1 + sum(1 for s_ in range(1, 4) if f'{base}.alt{s_}' in order)
        feats = ["'calt' 0"] + [f"'calt' 0, 'ss0{s_}' 1" for s_ in range(1, n)]
        spans = ''.join(f'<span class="v" style="font-feature-settings:{f}">{html.escape(c)}</span>' for f in feats)
        cells.append(f'<div class="cell"><div class="vs">{spans}</div><div class="cp">U+{ord(c):04X}</div></div>')
    missing = [chr(cp) for cp in range(0x21, 0x7F) if cp not in cmap]
    accents = any(cp >= 0xC0 and chr(cp).isalpha() for cp in cmap)
    gaps = ' '.join(missing) + (' and accented letters' if not accents else '')
    fallback = (f'{html.escape(gaps.strip())} fall back to the next font in your stack.' if gaps.strip()
                else 'Every printable ASCII character is covered.')
    t = (resources.files('budget_foundry') / 'templates' / 'specimen.html').read_text()
    for k, v in {'__FAMILY__': html.escape(p.config['name']), '__HERO__': html.escape(s['hero']),
                 '__WOFF2__': base64.b64encode(woff2.read_bytes()).decode(), '__GRID__': ''.join(cells),
                 '__SAMPLES__': _js(s['samples']), '__SIZES__': _js(s['sizes_text']),
                 '__FALLBACK__': fallback}.items():
        t = t.replace(k, v)
    return t


def _js(v) -> str:
    return json.dumps(v, ensure_ascii=False).replace('</', '<\\/')


def slug(p) -> str:
    return p.config['name'].lower().replace(' ', '-')


def write(p) -> list[Path]:
    woff2 = p.build_dir / f'{p.ps_name}.woff2'; tt = TTFont(woff2)
    spec = p.build_dir / f'{slug(p)}-specimen.html'; spec.write_text(page(p, tt, woff2))
    snippet = p.build_dir / f'{slug(p)}.css'; snippet.write_text(css(p, woff2.name, tt))
    return [spec, snippet]


def export(p, target: Path) -> list[Path]:
    target.mkdir(parents=True, exist_ok=True)
    spec, snippet = write(p)
    woff2 = p.build_dir / f'{p.ps_name}.woff2'
    out = []
    for f in (woff2, snippet, spec):
        shutil.copy2(f, target / f.name); out.append(target / f.name)
    return out
