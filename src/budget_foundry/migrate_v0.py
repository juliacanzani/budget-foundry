"""One-off: turn the v0 working set (Julia Marker, October 2026) into a project folder.

The hand-written label scripts become layout data by running them against a stub
`seg` module that records each `apply(sheet, bands, specs, xr)` call. Order-based
candidate IDs (A0019) map to content IDs through v0's meta.json, which recorded each
candidate's sheet and bounding box.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import types
from importlib import resources
from pathlib import Path
from string import Template

from . import imaging
from .build import components_sorted
from .project import Project, candidate_id, empty_decisions, sha256_file

V0_DRAWN = '''0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.,:;…!?'"“”-–—_()[]{}<>«»/\\|+=×÷%*#@&~'''
V0_SHEETS = {  # sheet key -> (file, segmentation settings from seg.py / extract.py)
    'A': ('IMG_3524.heic', dict(min_stroke=0, min_area=400, stroke_floor=0)),
    'B': ('IMG_3521_2.heic', dict(min_stroke=0, min_area=400, stroke_floor=0)),
    'C': ('IMG_3526.heic', dict(min_stroke=12, min_area=350, stroke_floor=12)),
    'D': ('IMG_3531.heic', dict(min_stroke=10, min_area=250, stroke_floor=12)),
}
SHEET_NOTES = {
    'A': 'A–Z, a–z (except i, q, r)',
    'B': 'figures and punctuation; left column + right block',
    'C': 'gap fills: i r k, parens, @ × ÷ #, … ; | { } « » – _ —, curly quotes, practice words',
    'D': 'C re-shot plus [ ] and q; used only for [ ] and q (lower resolution)',
}

V0_SPECIMEN = """
[specimen]
hero = "Julia’s digital garden"
samples = ["Julia’s digital garden", "The quick brown fox jumped over the lazy dog", "Notes, drafts & half-finished ideas…",
           "Kitchen: what’s on the menu (2026)", "Hello! Bonjour! Hallo?"]
sizes_text = "Some thoughts on making things by hand, & why they’re worth it."
"""


def read_layouts(scripts: Path) -> dict:
    calls = []
    stub = types.ModuleType('seg')
    def apply(k, bands, specs, xr=None):
        calls.append((k, dict(bands=list(bands), rows=[[list(t) for t in row] for row in specs],
                              x=list(xr) if xr and tuple(xr) != (0, 99999) else None)))
        return [], True
    stub.apply = apply
    stub.__all__ = ['apply']
    saved = sys.modules.get('seg'); sys.modules['seg'] = stub
    try:
        for k in 'ABCD':
            code = (scripts / f'label_{k}.py').read_text()
            exec(compile(code, f'label_{k}.py', 'exec'), {'__name__': f'label_{k}', 'print': lambda *a, **kw: None})
    finally:
        if saved is None: sys.modules.pop('seg', None)
        else: sys.modules['seg'] = saved
    layout = {}
    for k, region in calls:
        if region['x'] is None: region.pop('x')
        layout.setdefault(k, []).append(region)
    return layout


def toml_sheets(sheets: dict) -> str:
    out = []
    for k, (src, s) in sheets.items():
        out.append(f'[sheets.{k}]  # {SHEET_NOTES.get(k, "")}\nsource = "sources/{src}"\n'
                   + ''.join(f'{a} = {b}\n' for a, b in s.items()))
    return '\n'.join(out)


def migrate(v0: Path, dest: Path, sources: Path | None = None, log=print) -> Project:
    """`sources` holds the four sheet photos (default: v0's own sources/ folder)."""
    v0, dest = Path(v0), Path(dest)
    sources = Path(sources) if sources else v0 / 'sources'
    if (dest / 'project.toml').exists():
        raise FileExistsError(f'{dest} already holds a project')
    (dest / 'sources').mkdir(parents=True, exist_ok=True)
    for k, (src, _) in V0_SHEETS.items():
        shutil.copy2(sources / src, dest / 'sources' / src)
    tpl = resources.files('budget_foundry') / 'templates'
    text = Template((tpl / 'project.toml').read_text()).substitute(name='Julia Marker', vendor='TNGB', sheets=toml_sheets(V0_SHEETS))
    # v0 measured the x-height used to hang the q rows on sheet A only
    text = text.replace('# xheight_sheets = ["A"]', 'xheight_sheets = ["A"]')
    # v0 normalised against the kept glyphs only; keep that so the font reproduces
    text = text.replace('reference = "candidates"', 'reference = "kept"      # v0: statistics from the kept glyphs, at build time', 1)
    text += V0_SPECIMEN
    (dest / 'project.toml').write_text(text)
    # v0's own coverage, not today's default: characters added to the default since were never drawn
    charset = (tpl / 'charset.toml').read_text()
    (dest / 'charset.toml').write_text(re.sub(r"^drawn = '''.*?'''", lambda m: f"drawn = '''{V0_DRAWN}'''", charset, count=1, flags=re.M))

    p = Project.open(dest)
    d = empty_decisions()
    d['layout'] = read_layouts(v0 / 'scripts')

    meta = json.loads((v0 / 'data' / 'meta.json').read_text())['meta']
    picks = json.loads((v0 / 'data' / 'picks.json').read_text())
    sha = {k: sha256_file(p.source_path(k)) for k in V0_SHEETS}
    new_id = {old: candidate_id(sha[g['sheet']], g['x'], g['y'], g['w'], g['h']) for old, g in meta.items()}
    for ch, ids in picks.items():
        d['glyphs'][ch] = dict(keep=[new_id[i] for i in ids], default=new_id[ids[0]], source='human')

    # Curly singles, as v0's build made them: ‘ from the left half of each kept “;
    # ’ from both halves of the first kept ” written in two strokes, right half first.
    log('importing sheets to resolve quote components…')
    for k in V0_SHEETS: imaging.run(p, k, log)
    labs = {k: imaging.load_labels(p, k) for k in V0_SHEETS}
    def comps(old):
        return components_sorted(meta[old], labs[meta[old]['sheet']])
    d['glyphs']['‘'] = dict(keep=[f'{new_id[i]}#0' for i in picks['“']], source='auto')
    two = next(i for i in picks['”'] if len(comps(i)) >= 2)
    d['glyphs']['’'] = dict(keep=[f'{new_id[two]}#1', f'{new_id[two]}#0'], source='human')  # right half first: v0's chosen default
    for ch in ('‘', '’'): d['glyphs'][ch]['default'] = d['glyphs'][ch]['keep'][0]
    p.save_decisions(d)
    (dest / 'v0-ids.json').write_text(json.dumps(new_id, indent=0))
    log(f'migrated {len(picks)} characters, {sum(len(v) for v in picks.values())} keepers → {dest}')
    return p
