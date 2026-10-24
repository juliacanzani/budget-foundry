# Budget Foundry v0 — handoff

Working scripts that produced **Julia Marker** (October 2026), extracted from a Claude chat session.
A proof of concept, not an app: paths are hardcoded, labelling is hand-written per sheet, and stages
pass JSON/PNG/NPY files through one working directory.
Target app spec: https://claude.ai/artifact/7oi7FH9CzKTriaoF3NNy3i
Milestone 1 = turn this into the `budget-foundry` CLI with a project folder, stable IDs and decisions.json.

## Requirements
Python 3.12; `pip install opencv-python scikit-image pillow pillow-heif potracer fonttools uharfbuzz brotli numpy`

## Sheets (sources/)
| Sheet | File | Contents |
|---|---|---|
| A | IMG_3524.heic | A–Z, a–z (except i, q, r) |
| B | IMG_3521_2.heic | figures and punctuation; left column + right block |
| C | IMG_3526.heic | gap fills: i r k, parens, @ × ÷ #, … ; \| { } « » – _ —, curly quotes, practice words |
| D | IMG_3531.heic | C re-shot plus [ ] and q; used only for [ ] and q (lower resolution) |

## Pipeline order
Scripts originally ran in /home/claude/font with PNGs in /home/claude.
0. `convert_heic.py`: HEIC → PNG. Fix the path prep.py reads from.
1. `prep.py`: flat-field + threshold → `<S>_norm.png`, `<S>_ink.png`.
2. `comps.py`: connected components + stroke width → `comps.json`, `<S>_lab.npy` (large, not shipped; regenerate).
3. `label_A/B/C/D.py` (use `seg.py`): **hand-written** y-bands, x-ranges and per-row label specs.
   Spec tuples: `(char, count)` or `(char, count, groups_per_glyph)`; `SKIP` drops groups. `ruler.py` renders ruled sheets for finding bands.
4. `extract.py`: crops on row baselines + metrics → `cands.json`, `meta.json` (bbox, component ids, baseline per candidate).
5. `score.py`: flags + suggested keepers → `data.json`, injected into `page.html` (`__DATA__`) for the culling sheet.
6. Human culling → `data/picks.json`. Defaults (`data/defaults_choice.json`) are already applied: the first id per character in picks.json is the default.
7. `build.py`: size normalisation with stroke-weight compensation, trace, vertical placement, white-area spacing, features, OTF + WOFF2. Reads `kern.fea` if present.
8. `kern.py`: profile kerning on the built OTF → `kern.fea`; then run `build.py` again.
9. `render.py`, `cyc.py`: HarfBuzz render to PNG; variant distribution check. `defaults.py` builds the default-picker data.

## Candidate IDs
`<sheet><index>`, index = position in the combined labelled list from label_A..D. **Fragile:** any label-spec
change renumbers everything after it and breaks picks.json. Replace with content hashes in Milestone 1.

## Lessons baked into these scripts
- Row keys include the band; without it, separate rows shared a baseline (blanked q, dashes, brackets).
- Glyph names are always `uniXXXX`; an `in '.notdef'` substring test once named glyphs `t` and `.`.
- **No `rand` feature**: HarfBuzz applies it by default and overrides the calt cycle.
- potracer traces False pixels, so pass `~mask`.
- Next time, normalise before culling; weight flags are unreliable on mostly horizontal glyphs.
- Tunables (size targets, 12u overshoot, 50% bounce with ±25u clamp, spacing targets, kern thresholds) are constants in build.py and kern.py.

## Font facts
UPM 1000 · cap 700 · x-height ≈465 · stroke ≈110u · descender ≈230 · hhea 900/−300 · 292 glyphs · ≈1,240 kern pairs · WOFF2 ≈48 KB.
`calt` two-direction cycle (crc32 parity of the character picks the direction), spaces carry state; `ss01`–`ss03` force a variant.
