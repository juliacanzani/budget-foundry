"""budget-foundry: every stage runs headless. The UI (Milestone 3) calls the same functions."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Optional

import typer

from . import __version__, pipeline
from .project import Project

app = typer.Typer(no_args_is_help=True, add_completion=False,
                  help='Turn photographed handwriting sheets into a web font with cycling alternates.')
ProjectArg = Annotated[Path, typer.Argument(help='Project folder', show_default=False)]
Force = Annotated[bool, typer.Option('--force', help='Rerun even if up to date')]


def _open(path: Path) -> Project:
    try:
        return Project.open(path)
    except FileNotFoundError as e:
        typer.echo(str(e), err=True); raise typer.Exit(2)


def _print_checks(res) -> bool:
    mark = {'pass': '✓', 'warn': '!', 'fail': '✗'}
    for r in res:
        typer.echo(f"  {mark[r['status']]} {r['check']}: {r['detail']}")
    return not any(r['status'] == 'fail' for r in res)


@app.command()
def version():
    """Print the version."""
    typer.echo(__version__)


@app.command()
def new(dest: ProjectArg, name: Annotated[str, typer.Option(help='Font family name')],
        paper: Annotated[str, typer.Option(help='letter or a4')] = 'letter'):
    """Start a font project: project.toml, charset.toml, decisions.json, sources/."""
    from .workspace import new_project
    p = new_project(dest, name, paper)
    typer.echo(f'{p.root}\nNext: budget-foundry template {dest}')


@app.command()
def template(project: ProjectArg, mono: Annotated[bool, typer.Option('--mono', help='Light grey guides for mono printers')] = False,
             out: Annotated[Optional[Path], typer.Option('-o', help='PDF path')] = None):
    """Stage 1: printable template PDF. Colour and mono prints share one layout."""
    from . import template as t
    p = _open(project)
    out = out or p.root / f"template{'-mono' if mono else ''}.pdf"
    path, lay = t.write_pdf(p, out, mono)
    rows = sum(len(s['rows']) for s in lay['sheets'] if s['kind'] == 'chars')
    typer.echo(f"{path}  ({len(lay['sheets'])} sheets, {rows} characters, rev {lay['rev']}, {lay['paper']})")


@app.command()
def add(project: ProjectArg, files: Annotated[list[Path], typer.Argument(help='Photos (HEIC, JPG, PNG) or PDFs')]):
    """Copy sheets into sources/ and register them. Template sheets find themselves by their markers."""
    from .workspace import add_sources
    for k in add_sources(_open(project), files): typer.echo(f'  + {k}')


@app.command('add-glyph')
def add_glyph(project: ProjectArg, files: Annotated[list[Path], typer.Argument(help='One image per glyph')],
              char: Annotated[Optional[str], typer.Option(help='The character (default: from the file name)')] = None,
              ink: Annotated[Optional[str], typer.Option(help='Ink colour as #rrggbb (default: auto)')] = None,
              tolerance: Annotated[Optional[float], typer.Option(help='Colour distance (ΔE) counted as ink')] = None,
              rotate: Annotated[Optional[float], typer.Option(help='Degrees to straighten, anticlockwise')] = None,
              baseline: Annotated[Optional[float], typer.Option(help='Baseline y in px of the cropped image (default: ink bottom)')] = None):
    """Freeform import: any photo of one glyph, ink found by colour, nearby splatter kept."""
    from .workspace import add_glyphs
    for k, ch in add_glyphs(_open(project), files, char, ink=ink, tolerance=tolerance, rotate=rotate, baseline=baseline):
        typer.echo(f'  + {k}: {ch}')


@app.command()
def serve(project: ProjectArg, port: int = 8765, open_browser: Annotated[bool, typer.Option('--open/--no-open')] = True):
    """Open the app: the cull view and preview in your browser, against this project."""
    import threading, webbrowser
    import uvicorn
    from .server import create_app
    app_ = create_app(_open(project).root)
    url = f'http://127.0.0.1:{port}/'
    if open_browser: threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    typer.echo(f'Budget Foundry on {url}  (Ctrl+C to stop)')
    uvicorn.run(app_, host='127.0.0.1', port=port, log_level='warning')


@app.command('import-v0')
def import_v0(v0: Annotated[Path, typer.Argument(help='The budget-foundry-v0 folder')], dest: ProjectArg,
              sources: Annotated[Optional[Path], typer.Option(help='Folder with the four sheet photos (default: <v0>/sources)')] = None):
    """Turn the v0 working set (Julia Marker) into a project folder, picks and all."""
    from .migrate_v0 import migrate
    p = migrate(v0, dest, sources)
    problems = pipeline.run_segment(p)
    if problems: raise typer.Exit(1)
    ids = json.loads((dest / 'v0-ids.json').read_text())
    from . import segment
    cands, _ = segment.load(p)
    lost = [old for old, new in ids.items() if new not in cands]
    typer.echo(f'{len(ids) - len(lost)} of {len(ids)} v0 candidates found again' + (f'; lost {lost[:10]}' if lost else ''))


@app.command('import')
def import_(project: ProjectArg, force: Force = False):
    """Stage 2: correct, flat-field and threshold each sheet; find components."""
    pipeline.run_import(_open(project), force)


@app.command()
def segment(project: ProjectArg, force: Force = False):
    """Stage 3: group components into glyphs and label them from the sheet layouts."""
    problems = pipeline.run_segment(_open(project), force)
    if problems: raise typer.Exit(1)


@app.command()
def build(project: ProjectArg, force: Force = False):
    """Stages 4–10: normalise, trace, place, space, kern, features, OTF + WOFF2, checks."""
    ok = _print_checks(pipeline.run_build(_open(project), force))
    if not ok: typer.echo('Checks failed: preview is fine, export is blocked.')


@app.command()
def check(project: ProjectArg):
    """Run the automated checks on the current build. Exit 1 on any failure."""
    p = _open(project)
    from . import checks
    if not _print_checks(checks.run(p)): raise typer.Exit(1)


@app.command()
def status(project: ProjectArg):
    """Show each stage as not run, stale or done."""
    for name, st in pipeline.status(_open(project)):
        typer.echo(f'  {name:<12} {st}')


@app.command()
def render(project: ProjectArg, text: Annotated[list[str], typer.Argument(help='Lines to set')],
           out: Annotated[Path, typer.Option('-o', help='PNG path')] = Path('render.png'),
           size: int = 90):
    """Set lines of text in the built font with HarfBuzz and save a PNG."""
    from .shaping import render_sheet
    p = _open(project)
    render_sheet(p.build_dir / f'{p.ps_name}.otf', text, out, size)
    typer.echo(str(out))


@app.command()
def cull(project: ProjectArg):
    """Write the culling sheet (candidates/cull.html) with current keepers preselected."""
    from . import cull as c
    typer.echo(str(c.write(_open(project))))


@app.command()
def picks(project: ProjectArg, file: Annotated[Optional[Path], typer.Argument(help='JSON exported from the culling sheet')] = None,
          suggested: Annotated[bool, typer.Option('--suggested', help='Characters without picks take the suggested keepers')] = False):
    """Merge picks exported from the culling sheet into decisions.json."""
    from . import cull as c
    p = _open(project)
    if file: typer.echo(f'{c.merge_picks(p, json.loads(file.read_text()))} characters changed')
    if suggested: typer.echo(f'{c.accept_suggested(p)} characters took the suggested keepers')
    if not file and not suggested: typer.echo('Pass a picks file, --suggested, or both.', err=True); raise typer.Exit(2)


@app.command()
def specimen(project: ProjectArg):
    """Write the specimen page and CSS snippet into build/."""
    from . import specimen as s
    for f in s.write(_open(project)): typer.echo(str(f))


@app.command()
def export(project: ProjectArg, to: Annotated[Optional[Path], typer.Option(help='Overrides export_to')] = None,
           force: Annotated[bool, typer.Option('--force', help='Export despite failing checks')] = False):
    """Copy WOFF2, CSS snippet and specimen to the export target. Blocked by failing checks."""
    from . import checks, specimen as s
    p = _open(project)
    res = checks.run(p)
    if not _print_checks(res) and not force:
        typer.echo('Export blocked by failing checks (use --force to override).', err=True); raise typer.Exit(1)
    target = to or (Path(p.config['export_to']).expanduser() if 'export_to' in p.config else None)
    if target is None:
        typer.echo('No export target: pass --to or set export_to in project.toml.', err=True); raise typer.Exit(2)
    for f in s.export(p, target): typer.echo(f'  → {f}')
