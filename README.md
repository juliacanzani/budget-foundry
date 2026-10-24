# Budget Foundry

Turns photographed handwriting sheets into a web font with cycling alternates. See [SPEC.md](SPEC.md) for the whole app; this is Milestone 1: the v0 pipeline as a CLI, with a project folder, stable candidate IDs and `decisions.json`.

## Setup

```sh
brew install uv
uv sync
```

Python 3.12 is fetched by `uv`. Tracing uses potracer (pure Python); native potrace isn't needed.

## A new font

```sh
uv run budget-foundry new fonts/my-hand --name "My Hand"     # --paper a4 if you're not on Letter
uv run budget-foundry template fonts/my-hand                 # template.pdf; add --mono for grey guides
# print, write each character along its row (up to 8 times), photograph each sheet flat and whole
uv run budget-foundry add fonts/my-hand ~/Desktop/IMG_*.heic # photos or a scanned PDF
uv run budget-foundry segment fonts/my-hand                  # every row labels itself from its markers
uv run budget-foundry cull fonts/my-hand                     # open candidates/cull.html, export picks
uv run budget-foundry picks fonts/my-hand picks.json         # or --suggested to take the scored picks
uv run budget-foundry build fonts/my-hand
```

Templates print fine on a mono printer: guides are removed by where they are, not by their colour. Each sheet carries ArUco markers for its page number and the template revision, so an old printout still imports after the charset changes. Import warns when the cap height is under 120 px in the photo.

Single glyphs from anything (paint, sauce, a marker on a napkin): `add-glyph fonts/my-hand S_sauce.jpg`. The character comes from the file name (`A.jpg`, `a_2.png`, `uni00DF.png`, `question.jpg`) or `--char`; ink is found by colour (`--ink "#be1e19"` to set it), splatter near the letter is kept, and `--rotate` straightens it.

## Julia Marker from v0

```sh
uv run budget-foundry import-v0 budget-foundry-v0 projects/julia-marker --sources samples/julia-marker
uv run budget-foundry build projects/julia-marker
```

`import-v0` copies the four HEICs from `samples/julia-marker/` (location metadata stripped, pixels untouched), turns the hand-written `label_*.py` row specs into layout data, and maps every v0 pick (`A0019`) to its content ID through v0's `meta.json` (`v0-ids.json` keeps the mapping). The build reproduces the shipped font's outlines, advances, cmap and kerning exactly (`uv run pytest`). GSUB differs on purpose: the shipped `calt` cycle never showed the default i, o or t (the only characters with four variants), so those now look back two glyphs (`features.wide_slot`).

## Commands

| Command | Does |
| --- | --- |
| `new <dir> --name …` | Start a project |
| `template <project> [--mono]` | Stage 1: printable template PDF |
| `add <project> files…` | Register photos or PDF pages as sheets |
| `add-glyph <project> files…` | Freeform: one glyph per image, ink by colour |
| `status <project>` | Each stage as not run, stale or done |
| `import <project>` | Stage 2: flat-field, threshold, components per sheet |
| `segment <project>` | Stage 3: group and label candidates from the layouts; score them |
| `cull <project>` | Write `candidates/cull.html`, current keepers preselected |
| `picks <project> [file.json] [--suggested]` | Merge picks from the culling sheet; `--suggested` fills characters without picks |
| `build <project>` | Stages 4–10, then checks. Runs stale upstream stages first |
| `check <project>` | Automated checks; exit 1 on failure |
| `render <project> "line" …` | HarfBuzz render to PNG |
| `specimen <project>` | Specimen page and CSS snippet with a size-matched fallback |
| `export <project> [--to dir]` | WOFF2, CSS and specimen to `export_to`; blocked by failing checks |

## A project

```
my-font/
  project.toml     metrics, height targets, per-sheet settings, every tunable
  charset.toml     characters to cover: drawn and derived
  sources/         original photos, never modified
  decisions.json   human choices only
  sheets/          derived
  candidates/      derived: <id>.json + <id>.png per candidate
  build/           derived: OTF, WOFF2, features.fea, kern.fea, metrics, checks
```

Delete any derived folder and the next command rebuilds it. Each one holds a `_stage.json` fingerprint of what it was built from.

`decisions.json`:

- `layout`: per sheet, regions of horizontal `bands` and per-row specs `[char, count, groups_per_glyph?]`; `SKIP` drops groups. A row whose count doesn't match is reported, never guessed.
- `labels`: `{candidate: char}` relabels; `""` drops.
- `glyphs`: `{char: {keep: [...], default, source}}`. Derived characters keep `"<candidate>#<component>"` refs, as in the curly singles cut from double quotes.
- `overrides`: `baseline` `{source: units}`, `kern` `{"To": -60}` pins a pair, `kern_exclude` `["To"]` drops one.

Candidate IDs are a hash of the source file's content and the glyph's bounding box, so re-segmenting a row doesn't renumber anything else.

## Not in Milestone 1

Harvesting glyphs from the words page and the marks page (M6), the drag-the-corners review screen (M3; flags for now), normalised tiles before culling and the React cull view (M3), sliders and the focus tray (M4), Tauri (M5), composites, ligatures and the asset pack (M6), cursive (M7).
