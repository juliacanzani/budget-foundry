from budget_foundry import features
from budget_foundry.build import picks_from, resolve_targets
from budget_foundry.project import Project, candidate_id


def test_candidate_id_depends_on_content_not_order():
    a = candidate_id('abc', 10, 20, 30, 40)
    assert a == candidate_id('abc', 10, 20, 30, 40)
    assert a != candidate_id('abd', 10, 20, 30, 40)
    assert a != candidate_id('abc', 11, 20, 30, 40)
    assert len(a) == 10


def test_default_goes_first():
    drawn, refs = picks_from(dict(glyphs={'a': dict(keep=['x', 'y', 'z'], default='z'),
                                          '’': dict(keep=['q#1', 'q#0'], default='q#1')}))
    assert drawn == {'a': ['z', 'x', 'y']}
    assert refs == {'’': ['q#1', 'q#0']}


def test_targets_resolve_refs_and_overshoot(tmp_path):
    p = Project(tmp_path, config=dict(targets={'CO': {'ref': 'cap', 'overshoot': 2}, 'gp': {'ref': 'xheight', 'plus': 255}, 'Q': 780}))
    t = resolve_targets(p, cap=700, xh=465, os_=12)
    assert t == {'C': 724, 'O': 724, 'g': 720, 'p': 720, 'Q': 780}


def test_features_have_no_rand_and_cycle_spaces():
    fea = features.generate({'a': 3, 'b': 2, '.': 1})
    assert 'rand' not in fea
    assert 'space.alt2' in fea
    assert 'feature calt' in fea and 'feature ss02' in fea


def test_production_glyph_names():
    assert features.gname('t', 0) == 'uni0074'
    assert features.gname('.', 2) == 'uni002E.alt2'
