"""The local API: reads stage outputs, writes only decisions.json, previews with HarfBuzz."""
import json
import re

import numpy as np
import pytest
from fastapi.testclient import TestClient

from budget_foundry.server import create_app
from synth import synthetic_project


@pytest.fixture(scope='module')
def client(tmp_path_factory):
    # sheet 1 holds A–J; the quotes sheet exercises derived curly singles
    from budget_foundry import template
    tmp = tmp_path_factory.mktemp('srv')
    p = synthetic_project(tmp, sheets=(0, 7))
    assert any(r['char'] == '“' for r in template.layout(p)['sheets'][7]['rows'])
    return TestClient(create_app(p.root, log=lambda *a: None)), p


def test_project_summary(client):
    c, _ = client
    pr = c.get('/api/project').json()
    assert pr['name'] == 'Test Hand' and pr['metrics']['upm'] == 1000
    assert {s['name']: s['state'] for s in pr['stages']}['normalise'] == 'done'


def test_glyphs_carry_normalised_outlines(client):
    c, _ = client
    g = {e['char']: e for e in c.get('/api/glyphs').json()}
    assert len(g['A']['candidates']) == 6
    tile = g['A']['candidates'][0]
    assert tile['path'].startswith('M') and tile['advance'] > 0
    assert -30 < tile['ymin'] < 30 and 650 < tile['ymax'] < 760      # on the baseline, at cap height


def test_choosing_writes_decisions_with_provenance(client):
    c, p = client
    ids = [k['id'] for k in c.get('/api/glyphs').json()[0]['candidates']]
    ch = c.get('/api/glyphs').json()[0]['char']
    r = c.put(f'/api/glyphs/U+{ord(ch):04X}', json={'keep': ids[:3], 'default': ids[2]})
    assert r.status_code == 200
    d = json.loads((p.root / 'decisions.json').read_text())['glyphs'][ch]
    assert d == {'keep': ids[:3], 'default': ids[2], 'source': 'human'}
    assert c.put(f'/api/glyphs/U+{ord(ch):04X}', json={'keep': ['nope']}).status_code == 422
    assert c.put(f'/api/glyphs/U+{ord(ch):04X}', json={'keep': ids[:1], 'default': ids[2]}).status_code == 422




def test_characters_that_are_path_syntax_can_be_chosen(client):
    c, p = client
    assert c.put('/api/glyphs/U+002E', json={'keep': []}).status_code == 200      # '.', which a path drops
    assert c.put('/api/glyphs/U+002F', json={'keep': []}).status_code == 200      # '/'
    assert c.put('/api/glyphs/nope', json={'keep': []}).status_code == 404

def test_keeps_stop_at_what_the_font_cycles(client):
    c, p = client
    a = next(e for e in c.get('/api/glyphs').json() if e['char'] == 'A')
    ids = [k['id'] for k in a['candidates']]
    assert len(ids) == 6 and c.get('/api/project').json()['max_keep'] == 4
    assert c.put('/api/glyphs/U+0041', json={'keep': ids[:5]}).status_code == 422
    # an older decisions file can be over; the preview says which, and shrinking is allowed
    f = p.root / 'decisions.json'; d = json.loads(f.read_text())
    d['glyphs']['A'] = {'keep': ids, 'default': ids[0], 'source': 'human'}; f.write_text(json.dumps(d))
    r = c.get('/api/preview', params={'text': 'A'})
    assert r.status_code == 409 and 'A (6)' in r.json()['detail']
    assert c.get('/api/glyphs').status_code == 200
    assert c.put('/api/glyphs/U+0041', json={'keep': ids[:5]}).status_code == 200
    assert c.put('/api/glyphs/U+0041', json={'keep': ids[:3]}).status_code == 200
    assert c.get('/api/preview', params={'text': 'A'}).status_code == 200

def test_preview_cycles_and_reports_missing(client):
    c, _ = client
    g = c.get('/api/glyphs').json()
    for e in g:
        if not e['keep'] and e['candidates'] and e['char'] not in '‘’':
            ids = [k['id'] for k in e['candidates']][:3]
            c.put(f"/api/glyphs/{e['codepoint']}", json={'keep': ids})
    r = c.get('/api/preview', params={'text': 'AAA DEF xyz'}).json()
    names = [x['name'] for x in r['glyphs']]
    assert names[:3] == ['uni0041', 'uni0041.alt1', 'uni0041.alt2'] or len(set(names[:3])) == 3
    assert all(x['path'] for x in r['glyphs'][:3])
    assert set(r['missing']) == set('xyz')
    off = c.get('/api/preview', params={'text': 'AAA', 'calt': False}).json()
    assert [x['name'] for x in off['glyphs']] == ['uni0041'] * 3


def test_curly_singles_follow_the_rule_until_chosen(client):
    c, _ = client
    q = {e['char']: e for e in c.get('/api/glyphs').json()}['‘']
    assert q['source'] == 'auto' and q['keep']


def test_source_tile(client):
    c, _ = client
    cid = c.get('/api/glyphs').json()[0]['candidates'][0]['id']
    r = c.get(f'/api/candidates/{cid}/source.png')
    assert r.status_code == 200 and r.headers['content-type'] == 'image/png'


def nums(path):
    return np.array([float(v) for v in re.findall(r'-?\d+\.?\d*', path)])


def test_corrections_reshape_one_candidate_and_undo_cleanly(client):
    c, p = client
    a = next(e for e in c.get('/api/glyphs').json() if e['char'] == 'A')
    cid = a['candidates'][0]['id']; before = a['candidates'][0]
    others = {x['id']: x['path'] for x in a['candidates'][1:]}
    assert before['corrections'] == {'baseline': 0, 'rotate': 0, 'scale': 1, 'width': 1, 'weight': 0}
    r = c.put(f'/api/candidates/{cid}/corrections', json={'set': {'scale': 0.8, 'rotate': 5}})
    assert r.status_code == 200
    after = next(x for x in r.json()['candidates'] if x['id'] == cid)
    assert after['ymax'] - after['ymin'] < 0.9 * (before['ymax'] - before['ymin'])
    # the others don't move: within half a unit (the class median now leaves the corrected one out)
    for x in r.json()['candidates'][1:]:
        assert np.allclose(nums(x['path']), nums(others[x['id']]), atol=0.5)
    d = json.loads((p.root / 'decisions.json').read_text())['overrides']
    assert d['scale'][cid] == 0.8 and d['rotate'][cid] == 5 and cid not in d['weight']
    assert c.put(f'/api/candidates/{cid}/corrections', json={'set': {'scale': 3}}).status_code == 422
    # undo: back to neutral, but only from the state it expects
    assert c.put(f'/api/candidates/{cid}/corrections', json={'set': {}, 'expect': {}}).status_code == 409
    r = c.put(f'/api/candidates/{cid}/corrections', json={'set': {}, 'expect': after['corrections']})
    assert next(x for x in r.json()['candidates'] if x['id'] == cid)['path'] == before['path']
    # width stretches across only
    r = c.put(f'/api/candidates/{cid}/corrections', json={'set': {'width': 1.25}})
    wide = next(x for x in r.json()['candidates'] if x['id'] == cid)
    span = lambda x: np.ptp(nums(x['path']).reshape(-1, 2)[:, 0])
    assert 1.15 < span(wide) / span(before) < 1.35
    assert abs((wide['ymax'] - wide['ymin']) - (before['ymax'] - before['ymin'])) < 0.05 * (before['ymax'] - before['ymin'])


def test_choosing_refuses_a_stale_expectation(client):
    c, _ = client
    g = next(e for e in c.get('/api/glyphs').json() if e['char'] == 'B')
    ids = [k['id'] for k in g['candidates']]
    c.put('/api/glyphs/U+0042', json={'keep': ids[:2]})
    stale = {'keep': ids[:1], 'default': ids[0]}
    assert c.put('/api/glyphs/U+0042', json={'keep': [], 'expect': stale}).status_code == 409
    assert c.put('/api/glyphs/U+0042', json={'keep': [], 'expect': {'keep': ids[:2], 'default': ids[0]}}).status_code == 200
