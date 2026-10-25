"""Milestone 2 gate, on synthetic photos: a printed template, photographed, labels itself
with no manual fixes (colour and grayscale prints), and a single photographed glyph goes
through freeform import into the candidates."""
from collections import Counter
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageChops, ImageDraw
from fontTools.ttLib import TTFont

from budget_foundry import pipeline, segment, template
from budget_foundry.freeform import char_from_name
from budget_foundry.project import Project
from budget_foundry.shaping import Poly
from budget_foundry.workspace import add_glyphs, add_sources, new_project
from synth import page_image, photograph, write_rows

ROOT = Path(__file__).resolve().parents[1]
FONT = ROOT / 'budget-foundry-v0' / 'build' / 'JuliaMarker-Regular.otf'
QUIET = dict(log=lambda *a: None)


def photo_of(p, pdf, n, tmp, seed, gamma=1.0, rotate=3.0):
    lay = template.layout(p)
    img, expected = write_rows(page_image(pdf, n + template.GUIDE_PAGES, 12), lay['sheets'][n], 12, FONT, seed=seed, guide_gamma=gamma)
    f = tmp / f'sheet{n + 1}-{seed}.jpg'
    f.write_bytes(photograph(img, seed=seed, rotate=rotate))
    return f, expected


@pytest.fixture(scope='module')
def proj(tmp_path_factory):
    tmp = tmp_path_factory.mktemp('tpl')
    p = new_project(tmp / 'hand', 'Test Hand')
    colour, _ = template.write_pdf(p, tmp / 'colour.pdf')
    mono, _ = template.write_pdf(p, tmp / 'mono.pdf', mono=True)
    lay = template.layout(p)
    quotes = next(i for i, s in enumerate(lay['sheets']) if any(r['char'] == '“' for r in s['rows']))
    shots = [photo_of(p, colour, 0, tmp, 1, rotate=4),
             photo_of(p, mono, quotes, tmp, 2, gamma=1.6, rotate=-5)]   # darkened grey guides
    add_sources(p, [f for f, _ in shots], **QUIET)
    return Project.open(p.root), tmp, [e for _, e in shots]


def test_layout_is_stable_and_saved(proj):
    p, _, _ = proj
    lay = template.layout(p)
    assert lay['rev'] == template.layout(p)['rev']
    assert (p.root / 'templates' / f"{lay['rev']}.json").exists()
    assert lay['sheets'][-1]['kind'] == 'words'


def test_template_sheets_label_themselves(proj):
    p, _, expected = proj
    assert pipeline.run_segment(p, **QUIET) == []
    cands, _ = segment.load(p)
    got = Counter((c['sheet'], c['ch']) for c in cands.values())
    for key, exp in zip(p.sheet_keys, expected):
        for ch, n in exp:
            assert got[(key, ch)] == n, (key, ch, got[(key, ch)])
    assert sum(got.values()) == sum(n for exp in expected for _, n in exp)


def test_candidates_sit_on_the_printed_baseline(proj):
    p, _, _ = proj
    cands, _ = segment.load(p)
    for c in cands.values():
        if c['ch'] in 'ABCDEFHIKLMNPRTUVWXYZ':
            assert abs(c['bot_sw']) < 1.0, (c['ch'], c['bot_sw'])   # within a stroke of the guide


def test_old_printout_survives_charset_change(proj):
    p, tmp, _ = proj
    old = template.layout(p)['rev']
    (p.root / 'charset.toml').write_text((p.root / 'charset.toml').read_text().replace("drawn = '''", "drawn = '''ß"))
    p2 = Project.open(p.root)
    template.write_pdf(p2, tmp / 'new.pdf')
    assert template.layout(p2)['rev'] != old
    pipeline.run_segment(p2, force=True, **QUIET)
    recs = [p2.stage_record(p2.sheet_dir(k))['template']['rev'] for k in p2.sheet_keys]
    assert recs == [old, old]


def test_pdf_scan_imports(proj, tmp_path):
    p, tmp, _ = proj
    lay = template.layout(p)
    img, exp = write_rows(page_image(tmp / 'colour.pdf', 1 + template.GUIDE_PAGES, 12), lay['sheets'][1], 12, FONT, seed=5)
    pdf = tmp_path / 'scan.pdf'
    img.save(pdf, 'PDF', resolution=300)
    p = Project.open(p.root)
    (key,) = add_sources(p, [pdf], **QUIET)
    p = Project.open(p.root)
    pipeline.run_segment(p, **QUIET)
    cands, _ = segment.load(p)
    got = Counter(c['ch'] for c in cands.values() if c['sheet'] == key)
    assert got == Counter(dict(exp))


def test_guide_page_is_skipped(proj, tmp_path):
    """A whole exported PDF, guide page first (a tablet export), imports with the guide skipped."""
    p, tmp, _ = proj
    lay = template.layout(p)
    guide = page_image(tmp / 'colour.pdf', 0, 12)
    img, exp = write_rows(page_image(tmp / 'colour.pdf', 2 + template.GUIDE_PAGES, 12), lay['sheets'][2], 12, FONT, seed=6)
    pdf = tmp_path / 'export.pdf'
    guide.save(pdf, 'PDF', resolution=300, save_all=True, append_images=[img])
    p = Project.open(p.root)
    first, second = add_sources(p, [pdf], **QUIET)
    p = Project.open(p.root)
    pipeline.run_segment(p, **QUIET)
    rec = p.stage_record(p.sheet_dir(first))
    assert rec['template'] == dict(rev=lay['rev'], kind='guide') and rec['components'] == 0
    cands, _ = segment.load(p)
    assert not [c for c in cands.values() if c['sheet'] == first]
    assert Counter(c['ch'] for c in cands.values() if c['sheet'] == second) == Counter(dict(exp))


def test_freeform_glyph_by_colour(proj, tmp_path):
    p, _, _ = proj
    W, H = 1200, 1400
    rng = np.random.default_rng(3)
    kraft = np.full((H, W, 3), (176, 142, 104), np.float32) + rng.normal(0, 7, (H, W, 1))
    gs = TTFont(str(FONT)).getGlyphSet(); pen = Poly(gs); gs['uni0053'].draw(pen)
    m = Image.new('1', (W, H), 0)
    for poly in pen.polys:
        t = Image.new('1', (W, H), 0)
        ImageDraw.Draw(t).polygon([(300 + x * 1.2, 1100 - y * 1.2) for x, y in poly], fill=1)
        m = ImageChops.logical_xor(m, t)
    d = ImageDraw.Draw(m)
    d.ellipse((320, 1105, 336, 1121), fill=1)          # splatter touching distance
    d.ellipse((1120, 80, 1140, 100), fill=1)           # a far speck
    a = np.asarray(m, np.float32)[..., None]
    f = tmp_path / 'S_sauce.jpg'
    Image.fromarray(np.clip(kraft * (1 - a) + np.array((190, 30, 25), np.float32) * a, 0, 255).astype(np.uint8)).save(f, quality=88)
    p = Project.open(p.root)
    [(key, ch)] = add_glyphs(p, [f])
    assert ch == 'S'
    p = Project.open(p.root)
    pipeline.run_segment(p, **QUIET)
    cands, _ = segment.load(p)
    [c] = [c for c in cands.values() if c['sheet'] == key]
    assert c['ch'] == 'S' and len(c['ids']) == 2      # letter + its splatter, far speck dropped
    assert c['x'] + c['w'] < 900                       # crop stops well short of the far speck


def test_char_from_file_name():
    assert char_from_name('A') == 'A'
    assert char_from_name('a_2') == 'a'
    assert char_from_name('uni00DF') == 'ß'
    assert char_from_name('question-1') == '?'
    assert char_from_name('IMG_3521') is None


def test_long_words_wrap_onto_rows():
    assert template.wrap('The quick brown fox jumps over the lazy dog.', 33) == ['The quick brown fox jumps over', 'the lazy dog.']
    assert template.wrap('nanbncndnenf', 7) == ['nanbnc', 'ndnenf']    # even cuts keep each letter beside an n
