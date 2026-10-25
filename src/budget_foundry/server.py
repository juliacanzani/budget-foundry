"""Local API for the UI: one process, one project, localhost only.

Reads come from the stage outputs (candidates/, normalised/); the only writes are to
decisions.json, and only through the glyph endpoint. Long jobs (build) run on a
worker thread and stream their log over server-sent events.
"""
from __future__ import annotations

import asyncio
import io
import json
import queue
import threading
from importlib import resources
from pathlib import Path

import uharfbuzz as hb
from fastapi import FastAPI, HTTPException
from fontTools.pens.svgPathPen import SVGPathPen
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import build, checks, features, pipeline, segment
from .project import Project, fingerprint
from .template import WRITING_ORDER


class GlyphChoice(BaseModel):
    keep: list[str]
    default: str | None = None


def svg_path(g: dict) -> str:
    """Outline in font units, y up, origin at the glyph's own left sidebearing."""
    ox, dy = g['lsb'] - g['xmin'], g['dy']
    f = lambda q: f'{q[0] + ox:.1f} {q[1] + dy:.1f}'
    out = []
    for st, segs in g['contours']:
        out.append('M' + f(st))
        for sg in segs:
            out.append(('L' + f(sg[1])) if sg[0] == 'L' else ('C' + f(sg[1]) + ' ' + f(sg[2]) + ' ' + f(sg[3])))
        out.append('Z')
    return ''.join(out)


class State:
    """Everything the endpoints share. One lock serialises writes and rebuilds."""

    def __init__(self, root: Path, log=print):
        self.root = Path(root); self.lock = threading.RLock(); self.log = log
        self.jobs: dict[str, dict] = {}
        self.subscribers: list[queue.Queue] = []
        self._preview_key = None; self._preview = None; self._builder = None
        self.refresh()

    @property
    def p(self) -> Project:
        return Project.open(self.root)

    def refresh(self):
        """Bring candidates and normalised outlines up to date (cheap when fresh)."""
        with self.lock:
            pipeline.run_segment(self.p, log=self.log)
            p = self.p
            if not build.by_reference(p):
                # v0 projects build from kept glyphs, but the cull view still needs every candidate drawn
                p.config.setdefault('normalise', {})['reference'] = 'candidates'
            if not p.is_fresh(build.normalised_path(p).parent, build.normalise_fp(p)):
                self.log('normalise'); build.run_normalise(p, self.log)
            self.norm = json.loads(build.normalised_path(p).read_text())
            self.norm_fp = build.normalise_fp(p)
            self.cands, _ = segment.load(p)
            self._builder = None; self._preview_key = None

    def derived_by_component(self) -> set[str]:
        return {ch for ch, s in self.p.charset.get('derived', {}).items() if s.get('method') == 'component'}

    # ---- events
    def emit(self, event: dict):
        for q in list(self.subscribers): q.put(event)

    def run_job(self, name: str, fn):
        if self.jobs.get(name, {}).get('state') == 'running':
            raise HTTPException(409, f'{name} is already running')
        self.jobs[name] = dict(state='running', log=[])
        def log(msg):
            self.jobs[name]['log'].append(msg); self.emit(dict(job=name, line=msg))
        def work():
            try:
                with self.lock:
                    result = fn(log)
                self.jobs[name].update(state='done', result=result)
            except Exception as e:          # report, never kill the server
                self.jobs[name].update(state='failed', error=str(e)); log(f'! {e}')
            self.emit(dict(job=name, state=self.jobs[name]['state']))
        threading.Thread(target=work, daemon=True).start()

    # ---- preview
    def preview_font(self, decisions: dict):
        """Unkerned font from the current decisions and the normalised cache, compiled
        once per change of decisions. Returns (harfbuzz font, glyph order, path of)."""
        key = fingerprint(self.norm_fp, decisions['glyphs'])
        if key != self._preview_key:
            if self._builder is None:
                b = build.Builder(self.p, log=lambda *a: None)
                b.G = self.norm['glyphs']
                for k, v in self.norm['metrics'].items(): setattr(b, k, v)
                self._builder = b
            b = self._builder
            b.choose(decisions)
            b.picks = {ch: rs for ch, rs in b.picks.items() if all(r in b.G for r in rs)}
            b.refs = {ch: rs for ch, rs in b.refs.items() if all(r in b.G for r in rs)}
            b.glyph_table()
            font = b.compile(features.generate(b.nvar, b.space_variants))
            buf = io.BytesIO(); font.save(buf)
            gs = font.getGlyphSet(); paths = {}
            def path_of(name):
                if name not in paths:
                    pen = SVGPathPen(gs); gs[name].draw(pen); paths[name] = pen.getCommands() or None
                return paths[name]
            self._preview = (hb.Font(hb.Face(hb.Blob(buf.getvalue()))), font.getGlyphOrder(), path_of, set(b.cmap))
            self._preview_key = key
        return self._preview


def create_app(root: Path, log=print) -> FastAPI:
    st = State(root, log)
    app = FastAPI(title='Budget Foundry', docs_url='/api/docs', openapi_url='/api/openapi.json')

    def char_order(p):
        chars = list(dict.fromkeys(c['ch'] for c in st.cands.values()))
        derived = [ch for ch, s in p.charset.get('derived', {}).items() if s.get('method') == 'component']
        listed = [c for c in WRITING_ORDER if c in chars or c in derived]
        return listed + [c for c in chars if c not in listed]

    def entry(ch, d):
        e = d['glyphs'].get(ch, {})
        refs = [r for r, g in st.norm['glyphs'].items() if g['ch'] == ch]
        refs.sort(key=lambda r: st.cands[r.split('#')[0]].get('score', 0))
        cands = []
        for r in refs:
            g = st.norm['glyphs'][r]; c = st.cands[r.split('#')[0]]
            cands.append(dict(id=r, path=svg_path(g), advance=g['adv'], ymin=g['ymin'], ymax=g['ymax'],
                              flags=[] if '#' in r else c['flags'], score=c['score'],
                              suggested=False if '#' in r else c['suggested'], sheet=c['sheet']))
        keep, default, source = e.get('keep', []), e.get('default'), e.get('source')
        if not keep and ch in st.derived_by_component():
            try:
                st.preview_font(d)                   # resolves the rule's picks on the shared builder
                keep = st._builder.refs.get(ch, [])
            except RuntimeError: keep = []           # decisions the font can't take yet; the preview says why
            default = keep[0] if keep else None; source = 'auto' if keep else None
        return dict(char=ch, codepoint=f'U+{ord(ch):04X}', candidates=cands, keep=keep, default=default, source=source)

    @app.get('/api/project')
    def project():
        p = st.p; m = st.norm['metrics']; d = p.load_decisions()
        order = char_order(p)
        decided = [ch for ch in order if d['glyphs'].get(ch, {}).get('keep')]
        return dict(name=p.config['name'], mode=p.config.get('mode', 'written'),
                    metrics=dict(upm=m['UPM'], cap=m['CAP'], xheight=round(m['XH']), descender=round(m['DESC']),
                                 ascender=build.settings(p)['metrics']['ascender'], stroke=round(m['U'])),
                    stages=[dict(name=n, state=s) for n, s in pipeline.status(p)],
                    characters=len(order), decided=len(decided), max_keep=features.MAX_VARIANTS,
                    without_default=[ch for ch in decided if not d['glyphs'][ch].get('default')])

    @app.get('/api/glyphs')
    def glyphs():
        p = st.p; d = p.load_decisions()
        return [entry(ch, d) for ch in char_order(p)]

    @app.put('/api/glyphs/{char}')
    def choose(char: str, body: GlyphChoice):
        with st.lock:
            p = st.p; d = p.load_decisions()
            valid = {r for r, g in st.norm['glyphs'].items() if g['ch'] == char}
            bad = [i for i in body.keep if i not in valid]
            if bad: raise HTTPException(422, f'not candidates for {char!r}: {bad}')
            # More than the font can cycle; shrinking a set already over (from an old file) is allowed
            before = d['glyphs'].get(char, {}).get('keep', [])
            if len(body.keep) > features.MAX_VARIANTS and len(body.keep) >= len(before):
                raise HTTPException(422, f'at most {features.MAX_VARIANTS} kept per character')
            if body.default is not None and body.default not in body.keep:
                raise HTTPException(422, 'the default must be one of the kept candidates')
            if body.keep:
                d['glyphs'][char] = dict(keep=body.keep, default=body.default or body.keep[0], source='human')
            else:
                d['glyphs'].pop(char, None)
            p.save_decisions(d)
            return entry(char, d)

    @app.get('/api/preview')
    def preview(text: str, calt: bool = True):
        if len(text) > 500: raise HTTPException(413, 'preview text is limited to 500 characters')
        with st.lock:
            try: font, order, path_of, cmap = st.preview_font(st.p.load_decisions())
            except RuntimeError as e: raise HTTPException(409, str(e))
            buf = hb.Buffer(); buf.add_str(text); buf.guess_segment_properties()
            hb.shape(font, buf, {'calt': calt})
            x = 0; out = []
            for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
                name = order[info.codepoint]
                out.append(dict(name=name, x=x, advance=pos.x_advance, path=path_of(name)))
                x += pos.x_advance
        return dict(width=x, glyphs=out, missing=[c for c in dict.fromkeys(text) if c != ' ' and ord(c) not in cmap])

    @app.get('/api/candidates/{cid}/source.png')
    def source_tile(cid: str):
        f = st.p.candidates_dir / f"{cid.split('#')[0]}.png"
        if not f.exists(): raise HTTPException(404)
        return FileResponse(f, media_type='image/png')

    @app.get('/api/build/files/{name}')
    def build_file(name: str):
        d = st.p.build_dir
        allowed = {f.name: f for f in d.glob('*') if f.suffix in ('.woff2', '.otf', '.html', '.css')} if d.exists() else {}
        if name not in allowed: raise HTTPException(404)
        return FileResponse(allowed[name], filename=name if name.endswith(('.woff2', '.otf')) else None)

    @app.post('/api/export')
    def export():
        from . import specimen
        p = st.p
        if 'export_to' not in p.config: raise HTTPException(409, 'set export_to in project.toml first')
        with st.lock:
            res = checks.run(p)
            failed = [r['check'] for r in res if r['status'] == 'fail']
            if failed: raise HTTPException(409, f'export is blocked by failing checks: {", ".join(failed)}')
            out = specimen.export(p, Path(p.config['export_to']).expanduser())
        return dict(files=[str(f) for f in out])

    @app.post('/api/build')
    def run_build():
        st.run_job('build', lambda log: _build(st.p, log))
        return dict(state='running')

    @app.get('/api/jobs/{name}')
    def job(name: str):
        return st.jobs.get(name, dict(state='idle'))

    @app.get('/api/events')
    async def events():
        q: queue.Queue = queue.Queue(); st.subscribers.append(q)
        async def stream():
            try:
                yield 'retry: 2000\n\n'
                while True:
                    try:
                        ev = q.get_nowait()
                        yield f'data: {json.dumps(ev, ensure_ascii=False)}\n\n'
                    except queue.Empty:
                        await asyncio.sleep(0.2)
            finally:
                st.subscribers.remove(q)
        return StreamingResponse(stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache'})

    web = Path(str(resources.files('budget_foundry') / 'web'))
    if (web / 'index.html').exists():
        app.mount('/', StaticFiles(directory=str(web), html=True), name='web')
    else:
        @app.get('/')
        def no_ui():
            from fastapi.responses import PlainTextResponse
            return PlainTextResponse('The UI is not built yet: run `pnpm install && pnpm build` in ui/, then reload. '
                                     'The API is up at /api/docs.', status_code=503)
    app.state.bf = st
    return app


def _build(p: Project, log):
    from . import specimen
    pipeline.run_build(p, log=log)
    res = checks.run(p)
    spec, css = specimen.write(p)
    return dict(checks=res, metrics=json.loads((p.build_dir / 'metrics.json').read_text()),
                files=dict(woff2=f'{p.ps_name}.woff2', otf=f'{p.ps_name}.otf', specimen=spec.name, css=css.name),
                export_to=p.config.get('export_to'), blocked=any(r['status'] == 'fail' for r in res))
