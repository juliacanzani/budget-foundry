"""The trace cache: a rerun retraces only what a change actually shapes."""
import json
import re

from budget_foundry import build, pipeline
from budget_foundry.project import Project
from synth import synthetic_project


def traced(p) -> int:
    lines = []
    build.run_normalise(Project.open(p.root), log=lines.append)
    m = [re.match(r'\s*traced (\d+) of', l) for l in lines]
    return next((int(x[1]) for x in m if x), 0)


def set_toml(p, section, key, value):
    f = p.root / 'project.toml'; t = f.read_text()
    f.write_text(re.sub(rf'(?m)^{key} = \S+', f'{key} = {value}', t, count=1) if f'\n{key} = ' in t
                 else t + f'\n[{section}]\n{key} = {value}\n')


def test_rerun_retraces_only_what_changed(tmp_path):
    p = synthetic_project(tmp_path)
    pipeline.run_segment(p, log=lambda *a: None)
    n = traced(p)
    assert n > 0
    before = (p.root / 'normalised' / 'glyphs.json').read_text()
    assert traced(p) == 0                                     # nothing changed
    assert (p.root / 'normalised' / 'glyphs.json').read_text() == before
    set_toml(p, 'spacing', 'capitals', 1.1)                   # spacing: placed and spaced, not traced
    assert traced(p) == 0
    assert json.loads((p.root / 'normalised' / 'glyphs.json').read_text()) != json.loads(before)
    set_toml(p, 'trace', 'smoothing', 0.09)                   # shapes every outline
    assert traced(p) == n
    assert len(list((p.root / 'normalised' / 'trace').glob('*.json'))) == n   # the old outlines pruned
