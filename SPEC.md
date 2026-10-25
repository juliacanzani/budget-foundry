# Budget Foundry — spec

Oct 23, 2026 · @Julia Canzani

Budget Foundry is a local app that turns photographed or scanned handwriting sheets into a web font with cycling alternates, in an afternoon instead of a multi-day back-and-forth. It packages the pipeline we used for Julia Marker (October 2026) and fixes the friction points we hit doing it by hand.

## Purpose and scope

One user, one machine, rerunnable at any point. Every human decision (labels, keepers, defaults, overrides) is stored as data, so changing one pick rebuilds the font without redoing anything else.

**Goals**

- Print a template, write on it, import a photo: segmentation and labelling are automatic for template sheets.
- Judge glyphs after size and baseline normalisation, not before.
- Keep, drop and choose the default variant in a single pass.
- Build OTF and WOFF2 with alternate cycling, spacing and kerning, verified in HarfBuzz before export.
- Export straight into a site repo, with a specimen page and a CSS snippet.

**Non-goals**

- A general font editor. Bezier editing happens in Glyphs or FontForge via UFO export.
- Variable fonts or non-Latin scripts.
- Multi-user, cloud sync or accounts.

## Stack and runtime

Python does the image and font work; a small web UI on localhost does the judging. One command starts both: `uv run budget-foundry serve ./my-font`, which opens the browser.

| Layer | Choice | Why |
| --- | --- | --- |
| Image processing | OpenCV, scikit-image, pillow-heif | Already proven on HEIC phone photos |
| Tracing | potrace CLI if installed, potracer (pure Python) as fallback | potracer handled about 300 glyphs fine; native is faster |
| Font build | fontTools (FontBuilder, feaLib, cu2qu), brotli for WOFF2 | Same as the current build |
| Shaping tests | uharfbuzz | Caught the `rand` problem; matches Chrome and Firefox |
| API | FastAPI, one process | Serves the UI and runs pipeline stages as jobs with progress events |
| UI | React + Tangible UI (TUI), Vite | TUI is React and MIT-licensed on npm, so the public repo can depend on it; glyphs drawn as inline SVG from traced outlines |
| CLI | Typer | Every stage also runs headless: `budget-foundry build`, `budget-foundry check` |

Long stages (import, trace, build) stream progress over server-sent events, so the UI shows which sheet or glyph it's on. The shipped app is a Tauri bundle for macOS, released from a public GitHub repo: the React UI runs in Tauri's webview and the Python pipeline ships as a sidecar binary built with PyInstaller. Tauri doesn't care which frontend framework you use, so TUI works as is. The Python sidecar is the main packaging risk and makes the app large (roughly 100–150 MB, estimate). Releases are signed and notarised with Julia's Apple Developer account, so they open without Gatekeeper warnings.

## Project folder and data model

A font is a folder; everything derived can be deleted and rebuilt from sources plus decisions. That's what makes a second weight or an accent sheet a rerun.

```
my-font/
  project.toml        name, metrics targets, charset, build options
  sources/            original photos and scans, never modified
  sheets/             per sheet: corrected image, ink mask, detected rows (derived)
  candidates/         one JSON + PNG per segmented glyph (derived)
  decisions.json      labels, merges/splits, keepers, defaults, manual overrides
  build/              traced outlines, features.fea, OTF, WOFF2, specimen (derived)
```

**Stable candidate IDs.** IDs are a short hash of the source file hash plus the glyph's bounding box in the corrected sheet, not their position in a list. Our IDs were order-based, which would have broken every pick if a row had been re-segmented.

**Decisions are data.** `decisions.json` holds only human choices: a label per candidate, keep or drop, the default per character, and override values (a nudged baseline, a manual kern pair). Thresholds and targets live in `project.toml`. Any stage reruns from these two files.

**Charset file.** One list per project of characters to cover, each marked drawn, derived (curly singles from double quotes, middle dot from period) or composite (accented letters from base + mark). Coverage is checked against it at build time.

**Workspace and families.** The app holds many font projects. A family groups projects as styles (a second pen becomes a second style) and shares their charset, metric targets and spacing defaults. You decide the grouping: two projects can merge into one family, and a style can be broken out into its own font. Merging re-normalises the incoming style to the family's metric targets.

## Workflow stages

Ten stages, each with a status (not run, stale, done) that goes stale when anything upstream changes. Stages 5, 7 and 8 loop back through the build preview until the font looks right.

1. **Template.** Generate a printable PDF from the charset.
   - A guide page first: how to print, write, photograph and import. It carries the revision marker and no corner markers, so import recognises and skips it, and anyone who doesn't want it prints from page 2.
   - Guide lines for baseline, x-height, cap height and descender, pale cyan for colour printers or light grey for mono ones. Import removes them by position (once the markers are found it knows where every guide sits) and by lightness, so a colour printer is never required.
   - One character per row, labelled in the margin in the guide colour. Symbols and look-alikes (I, l, 0, O) are named under the label, and where length or height is the question (hyphen, en and em dash, underscore, quotes) shown in a word. Rows are long enough for 8 repeats, spaced so letters don't touch.
   - Four ArUco markers in the corners plus a sheet code, so import knows the sheet, its row order and its scale.
   - A words page ("nanbncn" sequences, **Hamburgevons**, a pangram, the user's own phrases) for spacing reference and in-context harvesting. Its rows run the full width with the prompt above the cap line, clear of tall letters; a long phrase wraps onto the next row. Seeded with words containing common pairs (little, better, coffee, the other) so ligature candidates turn up naturally. An optional ligature page takes pairs written on purpose.
   - A marks page for accents: acute, grave, circumflex, diaeresis, cedilla, tilde, ring, plus œ, æ, ß.
2. **Import.** Drag in HEIC, JPG, PNG or PDF.
   - Detect markers, correct perspective, flat-field the lighting, remove the guides by position, threshold. Works the same on colour and grayscale prints.
   - Report per sheet: pixels per stroke width, cap height in pixels, and a warning below 120 px cap height.
   - Sheets without markers (like ours) fall back to the manual path: row detection plus typing the label string per row.
3. **Segment and label.** Connected components, merged by row and by vertical overlap (i, j, !, ?, :, ;, ÷).
   - Template sheets label themselves by row. Words-page glyphs are labelled from the known text and are candidates by default; letter pairs that touch are kept whole as ligature candidates.
   - Fix-up tools: merge, split with a drawn cut line (for touching glyphs like the 22s and 44s we lost), mark as skip.
   - Anything with a stroke width far from the sheet median (labels, specks) is excluded and shown in a "dropped" tray.
4. **Normalise.** Before anyone judges anything.
   - Baseline per row from the printed guide, not a fitted line. Each glyph keeps a share of its natural bounce (slider, default 50%, capped at ±25 units).
   - Height per character class scaled to targets (cap, x-height, ascender, descender, per-punctuation targets), keeping a share of within-class variation (default: square root of the ratio).
   - Stroke weight compensated when scaling: dilate or erode by stroke × (1/f − 1) / 2 before tracing, so scaled glyphs keep the pen weight. Dots (period, ellipsis) scale plainly.
5. **Cull and choose defaults.** One screen, one pass.
   - Per character, every candidate normalised and drawn on guides. Click to keep; press S to star the default.
   - Flags at percentile thresholds (roughly the outer 10%): slant, weight, width, bounce. Weight flags are suppressed for mostly horizontal glyphs, where the measure is unreliable.
   - Suggested keepers and default pre-selected by score; legibility-risk pairs (Y vs 4, a vs 2, S vs 6, l vs I vs 1) shown side by side.
   - A live preview line renders with alternates off and on, from the current picks.
6. **Trace.** Smooth the mask (Gaussian at 6% of stroke width), potrace, convert to font units.
   - Parameters per project: alphamax, turd size, optimisation tolerance. Preview at 100% and 400%.
7. **Space.** White-area method per side (as in HT Letterspacer), with targets per category: capitals, lowercase, figures, punctuation.
   - Sliders for each target and the depth limit; preview strings (nnHnn, the user's words) shown beside the scanned handwriting for comparison.
8. **Kern.** Profile-based, class-per-character, averaged across all variants.
   - Tighten pairs more open than their reference pair (H H, n n, H n) by 60% of the difference, floor so ink never touches, drop anything under 30 units.
   - Override table: pin a pair's value or exclude it. Overrides survive rebuilds.
9. **Features.** Generated, not hand-written.
   - `calt` cycle with two directions split across characters; spaces carry the state; doubles and triples never repeat.
   - `ss01`–`ss03` force a variant. No `rand`: HarfBuzz applies it by default and it overrides the cycle.
   - Composites for accented letters from base + mark, with mark anchors placed automatically. Ligatures from the words page go in \`dlig\` (opt-in) by default; any pair can be promoted to \`liga\`.
10. **Build and export.** OTF, WOFF2, optional subset, UFO for outside editing.
    - Specimen HTML with the font embedded; a CSS snippet with a size-matched fallback.
    - Optional asset pack: every glyph and alternate as SVG, as transparent PNG at a chosen size, and as its original source cutout (straightened, background removed, full colour). Export target configurable, for example `~/Source/Personal/personal-site/public/fonts/`.

## Project modes

The app assumes nothing about the pen or the style; each project picks a mode, and the mode changes the template and which normalisation steps run.

| Mode | What you make | Template | What changes in the pipeline |
| --- | --- | --- | --- |
| Written | Print handwriting, any monoline pen (Julia Marker) | Rows on guide lines, writing size | The default pipeline described above |
| Cursive | Joined handwriting | Letters between joining neighbours | Join model and cutting (see Cursive mode); no white-area spacing |
| Drawn | Built-up letters: hand-drawn serifs, display caps, contrast styles | One large cell per glyph with guide lines inside; filled shapes or outlines | Stroke-weight compensation off, since it would flatten thick-thin contrast; optional fill for outline-only drawings; serif and stem alignment snapping; smoothing matters more |

A family can mix modes, for example a drawn serif and a written marker as two styles.

## Freeform import

Any image can be a source, in any mode: one glyph per photo, a giant sheet, paint, sauce. Human review stands in for the template.

- **Per-glyph uploads.** Drop one or many images; each goes to review, then joins the candidates. File names can pre-fill the character (`A.jpg`, `a_2.png`).
- **Review screen.** Drag four corners to straighten perspective, rotate, crop. Drag guide lines onto the glyph to mark its baseline, x-height and cap height, which sets its scale and placement.
- **Ink by colour.** Eyedropper on the ink plus a tolerance slider, so red sriracha on kraft paper works as well as black on white, with a live mask preview.
- **Texture.** Keep specks within a set distance of the main shape (the splatter belongs to the letter) and drop the rest; a minimum speck size slider.
- **Huge sheets.** Imported at full resolution and processed per region; tiles are shown downsampled.
- **Mixed sources.** Freeform glyphs go through the same normalisation, cull and build as template glyphs.

The font itself stays one colour. Colour and texture survive in the asset pack instead (stage 10): every freeform glyph's original cutout exports as a full-colour PNG.

## Cursive mode

Cursive is a project mode, not a separate app: the same stages, with joins replacing sidebearings. It is the largest single addition, and how well it works depends on how consistent your joins are.

- **Join model.** Each letter enters and exits in one of three states: baseline (most joins), high (out of o and into f, as in "out" and "of"), or none, a pen lift (after capitals, and before p in "practice"). Every letter gets an entry variant per state it occurs in, and `calt` picks the one matching the previous letter's exit. Alternates multiply on top. These states come from Julia's sample page (October 2026): mostly baseline, a few high, frequent pen lifts.
- **Writing protocol.** Template rows write each letter between joining neighbours ("nan nbn ncn"), plus a second row after a high-exit letter ("oao obo"). The app cuts the neighbours away at the narrowest point of each connecting stroke inside a join zone; the manual cut line covers misses.
- **Join normalisation.** Cut ends are trimmed square to the stroke and moved to standard join points: a fixed height, at the advance edge, overlapping the next letter by about half a stroke so the marker strokes fuse with no seam.
- **Word edges.** Initial forms (no entry stroke, or a short lead-in) and final forms (exit tail) chosen by `calt` from space and punctuation context. Long word-final tails (as in "cursive" and "practice") are their own final alternates. Capitals don't join by default; joining capitals are a later option.
- **Spacing and kerning.** Advances come from the join points, so the white-area spacing step is skipped and kerning is mostly off.
- **Shaping.** Joins are done with `calt` substitutions, which every engine supports. GPOS `curs` anchors are a possible refinement once tested in Safari (CoreText support for Latin needs checking).
- **Culling.** Tiles show the join zones, so off-height entries and exits are visible before they reach the font. i dots and t crossbars are written as separate strokes; segmentation assigns each to the letter below or left of it, and a crossbar that reaches into the next letter becomes a ligature candidate.

## UI and interaction

A left rail lists the ten stages with their status; the main area is the current stage; a preview strip along the bottom always shows the latest build rendering a test line, with alternates and kerning toggles.

- **Sheets view.** Corrected sheet with segmentation boxes overlaid, coloured by label confidence. Click a box to relabel, merge or split.
- **Cull view.** One row per character, candidates as SVG tiles on guide lines, sorted by score. Keyboard first: arrow keys move (up and down between characters), Space keeps, S stars the default; each tile also has a star button for the pointer. A tally shows characters covered and characters without a default.
- **Spacing and kerning view.** Test strings at three sizes beside the scanned original; sliders update the preview within a second by re-spacing in the browser rather than rebuilding.
- **Build view.** Check results (next section), variant distribution chart from the sample corpus, file sizes, export button.
- Live parameter preview: every judgement call (smoothing, bounce, weight compensation, spacing targets, kern strength) is a range slider. Dragging re-traces and re-renders only the characters pinned in a focus tray, one to a handful, so the preview lands in about 200 ms; the full rebuild runs on release. Light and dark mode; glyph tiles invert with the theme.

Everything the UI does maps to a CLI command, so the UI is never the only way to rerun a stage.

### Milestone 4 design (October 2026)

- **Trace cache.** Each candidate's traced outline is cached on disk under `normalised/trace/`, keyed by everything that shapes it: its sheet import, its pixels and components, its scale factor, the weight and trace settings, and its own corrections. Geometry is stored in sheet pixels and converted to font units on load, so a change to the font-wide stroke unit doesn't retrace. Placement and spacing always rerun from the cache, which takes milliseconds for the whole font, so baseline, bounce, placement and spacing settings apply to every glyph live; settings that change tracing retrace the pinned characters while dragging and everything else in the background on release.
- **Sliders save on release** to `project.toml`, keeping its comments, and each has a reset to its default.
- **Global undo and redo** (after the LMS course builder's undo manager): a list of records `{label, target, from, to}` with a pointer; a new change drops the redo side. Only finished changes are recorded: a slider records on release, not per drag step, and "keep suggestions for 12" is one record. Undo writes `from` back through the same API that made the change, with `to` as the expected current value; if the file has changed since (the CLI, a hand edit), the server refuses and the undo says why instead of overwriting. Undo and redo buttons in the header, disabled when there is nothing to undo; ⌘Z and ⇧⌘Z outside text fields; each announces "<label> — undone". Blocked while a rebuild runs. History lives in the browser session; candidate IDs are content hashes, so nothing in it needs rewriting.
- **Inspector on the right** for the focused candidate: its source photo, flags, keep and default, and the corrections (rotate, float, resize, bolder or thinner), with each flag offering its own fix. On phones it becomes a drawer from the right.
- **Tile focus and keeping are separate.** Clicking or arrowing to a tile focuses it and shows it in the inspector; keeping is its own action: a check button on the tile beside the star for the pointer, Space on the keyboard. S or the star still sets the default.

## Automated checks

Every build runs these; a failure blocks export but not preview. Each one maps to a bug we only caught by looking at output.

| Check | Pass condition | Bug it would have caught |
| --- | --- | --- |
| Non-empty glyphs | Every glyph has ink | Shared row baselines that blanked q, dashes and brackets |
| Unclipped tiles | No candidate touches its preview frame | The long-tailed y and two # |
| Coverage | Every charset character is in the cmap or flagged as fallback | Missing square brackets |
| Glyph names | Production names only, validated against feaLib | The `.notdef` substring bug that named glyphs `t` and `.` |
| Variant distribution | Each slot within 25–40% on the sample corpus, shaped in HarfBuzz | `rand` overriding the cycle (default at 11%) |
| Doubles | No repeated identical glyph in ee, ss, oo, ll, tt on the sample corpus | — |
| Vertical extremes | Report tallest and deepest glyphs; warn beyond 1.3× cap or 1.5× descender | Oversized X, ! and ; before normalisation |
| Collisions | No kerned pair has ink overlap in the test corpus | — |
| Size | WOFF2 under 80 KB, warn above | — |

## AI assist

The build stays deterministic: given the same sources, `decisions.json` and `project.toml`, it produces the same font every time and never calls a model. AI only proposes changes to decisions. Each proposal is shown as a diff, accepted or rejected per item, and once accepted it becomes an ordinary decision. Off by default.

### Principles
- **Proposals, not writes.** AI output lands in `suggestions.json`, never in `decisions.json` directly. Accepting a suggestion copies it into `decisions.json` with provenance.
- **Provenance on every decision.** `source: "human" | "ai" | "auto"`, plus `reason` and `model` for AI decisions. The cull and kerning views show a small AI marker on accepted suggestions.
- **Cached and replayable.** Requests are keyed by a hash of (stage, inputs, prompt version, model). Reruns read from the cache; "re-ask" is explicit.
- **Never in the build path.** `budget-foundry build` must succeed offline with no API key.

### Suggestion record
```json
{
  "id": "sug_7f3a",
  "stage": "label | cull | default | kern | space | legibility | metrics",
  "target": { "candidate": "c_91b2e0", "char": "Y" },
  "proposal": { "op": "set_default", "value": "c_91b2e0" },
  "reason": "Variant 2 has the most closed arms; variants 1 and 3 read as '4' at 24 px.",
  "confidence": 0.7,
  "model": "claude-sonnet-...",
  "created": "2026-10-24T18:02:00Z",
  "status": "pending | accepted | rejected"
}
```

### Assist tasks, in priority order
1. **Label freeform and non-template sheets.** A vision model reads a sheet or row crop and proposes the label string per row, with skips marked. The human confirms in the sheets view. Highest value: it removes the most manual step.
2. **Legibility review.** Render each default and each alternate in test words, run OCR (Tesseract) as a deterministic first pass, then ask a vision model about glyphs the OCR misreads or confuses. Known risks: Y/4, a/2, S/6, l/I/1, cursive r/z. Proposes default changes or flags for culling.
3. **Cull reasons.** For characters with flagged candidates, the model explains outliers in plain language and proposes keepers. The metric scores stay primary; the reasons make overriding them faster.
4. **Spacing and kerning critique.** Render test strings at 24, 48 and 96 px; the model flags pairs or glyphs that look loose, tight or oversized and proposes override values ("period too large", "T o loose"). Output: kern overrides or per-glyph metric adjustments.
5. **Test corpus.** Generate words and sentences that exercise problem pairs and the project's languages; stored in `project.toml` as the sample corpus.
6. **Check diagnosis.** When an automated check fails, an agent reads the build log and check output and proposes a fix: a decision change, or a note for code.

### Two integration paths (build both, MCP first)
**MCP server (`budget-foundry mcp ./my-font`).** Exposes the project to an external agent (Claude Code, Cowork). That agent runs polish passes on its own and returns a single batch of suggestions. Tools:
- `list_characters`, `list_candidates(char)`, `get_candidate(id)` (image + metrics)
- `render(text, size, features)` → PNG
- `measure(char | pair)` → advance, side gaps, kern value, vertical extremes
- `run_checks()` → check results
- `propose(suggestions[])` → writes to `suggestions.json` only
- `list_suggestions(status)`

No tool writes `decisions.json`; only the UI (or `budget-foundry accept <id>`) does.

**Built-in Claude API.** Optional API key stored in macOS Keychain. Used by the review screens for tasks 1–3, so they work without an external agent. Model is configurable; prompts are versioned in the repo.

### UI
- Suggestions tray per stage: a list with the reason and confidence, accept and reject buttons, and accept all above a confidence threshold.
- Before/after preview for each suggestion, using the live preview path.
- Rejected suggestions are kept, so the same suggestion isn't proposed again unless its inputs change.

### Checks added
- `build` succeeds with no network and no key.
- Every decision has a `source`; every `ai` decision has a `reason` and `model`.

### Milestone
**AI assist.** The MCP server can land any time after Milestone 1, since its tools wrap the CLI. The built-in API and suggestion trays come after Milestone 3. Gate: an external agent, using only the MCP tools, finds and proposes fixes for the Y/4 default and the oversized period on Julia Marker, and accepting them reproduces the current font's choices.

## Milestones

Each milestone is usable on its own; the gate is what has to be true before starting the next.

1. **Package the existing pipeline as a CLI** with the project folder, stable IDs and `decisions.json`; handed to a Claude Code or Cowork agent. Gate: rebuilding Julia Marker from the four original photos and the exported picks reproduces the current WOFF2's glyphs.
2. **Template generator, marker-based import, and freeform import with the review screen.** Gate: a printed template, photographed on a phone, labels itself with no manual fixes, and a single photographed glyph goes through review into the candidates.
3. **Cull-and-defaults UI** in React with TUI, run in a browser tab against the local API, with normalised tiles and the live preview line. Gate: a full charset culled in under 15 minutes.
4. **Sliders with live preview, spacing and kerning UI**, focus tray and override table. Gate: a slider change previews in about 200 ms on the pinned characters.
5. **Tauri packaging.** Python sidecar, signed and notarised macOS bundle, GitHub release workflow. Gate: a fresh Mac installs from the release page and builds a font with no Python installed.
6. **Families, drawn mode, composites, ligatures and the asset pack.** Multiple projects, merge and break-out, marks sheet and accented letters, ligatures from the words page and the optional ligature page. Gate: a two-style family renders French text without fallback.
7. **Cursive mode.** Join templates, join-zone cutting, join normalisation, entry-variant `calt`, initial and final forms. Gate: a paragraph in your cursive sets with no visible seams at 96 px in Chrome and Safari.

## Backlog

Not yet in a milestone, or follow-ups from using it. Newest asks first within each group.

**Template and charset options.** What changes the font lives in `project.toml` or `charset.toml` and the template follows from it; writing aids live under `[template]`. Every new guide shape goes into the saved layout, so import can remove it and old printouts still import.
- [ ] **Monospace.** `[metrics] advance` in font units; unset means proportional. The template draws one cell per copy (cell width from cap height × advance ÷ cap), which also lets segmentation group by cell. The build sets every advance to it, centres each glyph, turns kerning off, and warns on a glyph wider than its cell. Its own project (e.g. Digital Marker Mono) rather than a switch, since mono letters are written differently; families (Milestone 6) group them.
- [ ] Character sets to opt into (`sets = ["basic", "symbols", "currency"]`) instead of editing the `drawn` string.
- [ ] Accents to opt into (`marks = true` or a named set such as Latin-1): the marks sheet and composites from Milestone 6.
- [ ] Ligatures to include (`[ligatures] pairs`): the ligature page from Milestone 6.
- [ ] Extra writing guides (`[template.guides]`): a crossbar line, aperture ellipses for round letters.

**From the first real font (Digital Marker, October 2026).**
- [ ] **Per-candidate corrections in the cull view: rotate, float (baseline), resize, bolder or thinner.** Stored as overrides on the candidate in `decisions.json`, beside the baseline nudge that already exists, and applied in normalise, which already scales, shifts and dilates or erodes for stroke weight; rotation is new. The flags (slant, bounce, size, weight) say which candidates need it, so a flag can offer its own fix ("slant +11°" → straighten). Belongs with Milestone 4's override table and focus-tray preview. Weight correction only within about a stroke's width before it reads as a different pen.
- [ ] Words-page harvesting: the page is kept for reference only; spacing and ligature candidates come from it later.

**Upstream (Tangible UI).**
- [x] Drawer heading back to `Sidebar.Header` (TUI 0.2.32 makes Header and Footer plain `div`s).
- [x] Stage list on TUI 0.2.33's status-only `StepList`, stale stages as done with `attention`, the `--bf-ring` override dropped.

## Open questions and assumptions

**Assumptions**

- Runs on macOS with Python 3.12 and `uv`; native potrace via Homebrew is optional.
- A printer is available for templates. A flatbed scanner is not assumed; phone photos must work.
- One user, so no auth, locking or migrations beyond a version number in `project.toml`.

**Open questions**

- [ ] Which font to make first with the app. Not blocking; each project picks its mode at creation.

**Decided**

- Name: Budget Foundry.
- Package the current pipeline scripts and picks now; Milestone 1 is handed to a Claude Code or Cowork agent.
- Installable macOS app via Tauri, UI in React with TUI (MIT, on npm), released from a public GitHub repo.
- Releases are signed and notarised with Julia's Apple Developer account.
- Texture and spacing judgement calls get range sliders with near-live preview on a few chosen characters.
- Multiple font projects; you choose how they group into families, and projects can merge or styles break out.
- Words-page glyphs are candidates by default; touching pairs become ligature candidates.
- Ligatures from both sources, each optional: pairs harvested from the seeded words page, and pairs from an optional ligature page.
- The app is style-agnostic: written, cursive and drawn modes, chosen per project (see Project modes).
- Templates work printed in grayscale: guides are removed by position, not colour.
- The template PDF opens with a guide page; skipping it is a print range, not an option.
