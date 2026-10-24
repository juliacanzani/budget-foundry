"""Milestone 1 gate: rebuilding Julia Marker from the four original photos and the
exported picks reproduces the shipped WOFF2's glyphs.

GSUB is the one deliberate difference: the shipped cycle never showed the default of
the four-variant characters (i, o, t), so the calt rules changed (features.wide_slot)."""
from pathlib import Path

import pytest
from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont

from budget_foundry import pipeline, segment
from budget_foundry.migrate_v0 import migrate

ROOT = Path(__file__).resolve().parents[1]
V0 = ROOT / 'budget-foundry-v0'
SAMPLES = ROOT / 'samples' / 'julia-marker'
REFERENCE = V0 / 'build' / 'JuliaMarker-Regular.woff2'


@pytest.fixture(scope='module')
def project(tmp_path_factory):
    p = migrate(V0, tmp_path_factory.mktemp('jm') / 'julia-marker', SAMPLES, log=lambda *a: None)
    assert pipeline.run_segment(p, log=lambda *a: None) == []
    pipeline.run_build(p, log=lambda *a: None)
    return p


def test_every_v0_candidate_found_again(project):
    import json
    ids = json.loads((project.root / 'v0-ids.json').read_text())
    cands, _ = segment.load(project)
    assert len(ids) == 658
    assert all(new in cands for new in ids.values())


def test_glyphs_match_reference(project):
    built, ref = TTFont(project.build_dir / 'JuliaMarker-Regular.woff2'), TTFont(REFERENCE)
    assert built.getGlyphOrder() == ref.getGlyphOrder()
    gb, gr = built.getGlyphSet(), ref.getGlyphSet()
    for n in ref.getGlyphOrder():
        pb, pr = RecordingPen(), RecordingPen()
        gb[n].draw(pb); gr[n].draw(pr)
        assert pb.value == pr.value, n
        assert gb[n].width == gr[n].width, n


def test_layout_tables_match_reference(project):
    built, ref = TTFont(project.build_dir / 'JuliaMarker-Regular.woff2'), TTFont(REFERENCE)
    assert built.getBestCmap() == ref.getBestCmap()
    for t in ('GPOS', 'hmtx', 'hhea', 'OS/2'):
        assert built[t].compile(built) == ref[t].compile(ref), t


def test_kerning_matches_v0(project):
    assert (project.build_dir / 'kern.fea').read_text() == (V0 / 'data' / 'kern.fea').read_text()


def test_every_variant_shows_in_running_text(project):
    from collections import Counter
    from budget_foundry.shaping import CORPUS, Shaper
    sh = Shaper(project.build_dir / 'JuliaMarker-Regular.otf')
    slots, _ = sh.slots(CORPUS)
    for ch in 'iot':
        seen = Counter(s for c, s in zip(CORPUS, slots) if c == ch)
        assert set(seen) == {0, 1, 2, 3}, (ch, seen)


def test_checks_pass(project):
    from budget_foundry import checks
    assert [r for r in checks.run(project) if r['status'] == 'fail'] == []


def test_build_is_fresh_after_build(project):
    assert all(state == 'done' for _, state in pipeline.status(project))


def test_baseline_nudge_makes_build_stale(project):
    d = project.load_decisions()
    d['overrides']['baseline']['x'] = 5
    project.save_decisions(d)
    try:
        assert dict(pipeline.status(project))['build'] == 'stale'
        assert dict(pipeline.status(project))['segment'] == 'done'
    finally:
        d['overrides']['baseline'].pop('x'); project.save_decisions(d)


@pytest.mark.skipif(not (ROOT / 'src' / 'budget_foundry' / 'web' / 'specimen' / 'specimen.js').exists(),
                    reason='UI not built (pnpm build in ui/)')
def test_specimen_is_one_self_contained_file(project):
    import json, re
    from budget_foundry import specimen
    page, css = specimen.write(project)
    html = page.read_text()
    assert 'data:font/woff2;base64,' in html and '<script src=' not in html
    data = json.loads(re.search(r'<script type="application/json" id="specimen-data">(.*?)</script>', html, re.S).group(1))
    assert data['family'] == 'Julia Marker' and len(data['grid']) == 104
    assert {g['char']: g['variants'] for g in data['grid']}['o'] == 4
    assert 'Julia Marker Fallback' in css.read_text()
