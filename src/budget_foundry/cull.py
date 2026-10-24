"""Stage 5, cull: the v0 culling sheet, fed from candidates and decisions.json.
Milestone 3 replaces it with the React cull view (normalised tiles, defaults, live preview)."""
from __future__ import annotations

import json
from importlib import resources

from PIL import Image

from . import segment
from .build import picks_from
from .project import Project

ORDER = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,:;…!?'\"“”‘’-–—_()[]{}<>«»/\\|+=×÷%*#@&~"


def write(p: Project):
    cands, _ = segment.load(p)
    drawn, _ = picks_from(p.load_decisions())
    kept = {i for ids in drawn.values() for i in ids}
    by = {}
    for c in cands.values(): by.setdefault(c['ch'], []).append(c)
    chars = [ch for ch in ORDER if ch in by] + [ch for ch in by if ch not in ORDER]
    data = []
    for ch in chars:
        tiles = []
        for c in by[ch]:
            b64 = segment.tile_b64(p, c['id'])
            with Image.open(p.candidates_dir / f"{c['id']}.png") as im: hpx = im.height
            tiles.append(dict(id=c['id'], img=b64, hpx=hpx, tile_base=c['tile_base'], flags=c['flags'],
                              pick=c['suggested'], kept=c['id'] in kept))
        data.append(dict(ch=ch, cands=tiles))
    html = (resources.files('budget_foundry') / 'templates' / 'cull.html').read_text()
    html = html.replace('__NAME__', p.config['name']).replace('__DATA__', json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/'))
    out = p.candidates_dir / 'cull.html'
    out.write_text(html)
    return out


def merge_picks(p: Project, exported: dict, log=print) -> int:
    """Replace each shown character's keepers with the exported ones. The default stays
    if it's still kept, otherwise the first keeper becomes the default."""
    d = p.load_decisions(); cands, _ = segment.load(p)
    shown = {c['ch'] for c in cands.values()}
    unknown = [i for ids in exported.values() for i in ids if i not in cands]
    if unknown: raise ValueError(f'unknown candidate ids: {unknown[:8]}')
    changed = 0
    for ch in shown:
        new = exported.get(ch, [])
        old = d['glyphs'].get(ch)
        if old and old['keep'] == new: continue
        changed += 1
        if not new:
            d['glyphs'].pop(ch, None); log(f'  {ch}: nothing kept, removed from the font'); continue
        default = old['default'] if old and old.get('default') in new else new[0]
        d['glyphs'][ch] = dict(keep=new, default=default, source='human')
    p.save_decisions(d)
    return changed
