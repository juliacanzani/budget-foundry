"""Milestone 1 gate: rebuilding Julia Marker from the four original photos and the
exported picks reproduces the shipped WOFF2's glyphs."""
from pathlib import Path

import pytest
from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont

from budget_foundry import pipeline, segment
from budget_foundry.migrate_v0 import migrate

ROOT = Path(__file__).resolve().parents[1]
V0 = ROOT / 'budget-foundry-v0'
REFERENCE = V0 / 'build' / 'JuliaMarker-Regular.woff2'


@pytest.fixture(scope='module')
def project(tmp_path_factory):
    p = migrate(V0, tmp_path_factory.mktemp('jm') / 'julia-marker', log=lambda *a: None)
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
    for t in ('GSUB', 'GPOS', 'hmtx', 'hhea', 'OS/2'):
        assert built[t].compile(built) == ref[t].compile(ref), t


def test_features_match_v0(project):
    assert (project.build_dir / 'features.fea').read_text() == (V0 / 'data' / 'features.fea').read_text()


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
