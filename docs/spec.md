# dxf-translate — specification

Status: agreed 2026-11-18 (grilling session, Q1–Q22).

## 1. Goal

Turn the working prototype in `~/Projects/translate/tool` (SolidWorks DXF, Ukrainian →
English, GOST frame removed, PDF rendered) into a reusable product that a colleague can
install on their own Windows machine and use either

* from a **desktop app** (drag & drop files, get results, open the result folder), or
* from **Claude Code** via a plugin whose skill drives the full workflow
  (translate → check overlaps → review → extend glossary → rerun).

Scope is deliberately the current use case only: SolidWorks DXF, UA → EN, GOST frame.
Glossary and layout rules are data, so other projects can extend them without code
changes. Other formats/languages are out of scope until a real task needs them.

## 2. Non-goals

* No automatic fixing of text/geometry overlaps (reported only).
* No Claude API calls from the desktop app (possible later as "suggest translation").
* No auto-update of the desktop app.
* No customer data in the repository (drawings, Excel lists, outputs, example PDFs).

## 3. Users and environment

* Primary target: Windows user without Python experience.
* Desktop app ships as a single `.exe` (no Python needed on the machine).
* Plugin path requires Claude Code + `uv`; `uv` provisions Python 3.12 and dependencies.
* Linux must keep working for the author (development machine).

## 4. Architecture

One Python core, two front-ends.

```
dxf-translate/
  core/dxf_translate/        # python package (importable, no hardcoded paths)
    translate.py             # was translate_dxf.py
    overlaps.py              # was check_overlaps.py
    review.py                # was build_review.py
    glossary.py              # loader/merger for YAML glossaries
    data/glossary.yaml       # base glossary (was glossary.py constants)
    fonts/                   # OpenGost Type A (OFL) + osifont + licenses
    cli.py                   # `dxf-translate` entry point
    pipeline.py              # run_job(): one call used by CLI, GUI and skill
  gui/dxf_translate_gui/     # PySide6 window
  plugin/skills/translate-drawings/SKILL.md
  .claude-plugin/marketplace.json (+ plugin manifest)
  pyproject.toml             # uv project, Python 3.12
  tests/
  .github/workflows/build.yml
```

(Exact package layout may be simplified during planning, e.g. a single `src/` package
with a `gui` extra — the contract below is what matters.)

### 4.1 Core contract — `run_job`

Input: a list of paths (files and/or folders) and optional output dir.

1. Collect `*.dxf` (case-insensitive) from given paths (folders are scanned recursively; sub-folders named `EN`, `*_EN.dxf` and `~$*` files are skipped).
2. Collect `*.xlsx`; classify as UA if its cells contain Cyrillic, EN otherwise.
   Exactly one UA + one EN → used as translation source. None → warning
   "Excel not found", continue with glossary only. Ambiguous → error with message.
3. Glossary = base `glossary.yaml` merged with optional `glossary.yaml` in the
   order folder (order entries win).
4. Translate every DXF → `<out>/dxf/*_EN.dxf` and `<out>/pdf/*.pdf`, where default `<out>` = `<first dropped folder>/EN` (or `<folder of first DXF>/EN` if only files were given)
   (same naming as today). Inputs whose `<stem>_EN` output names coincide
   (case-insensitive — e.g. `old/AS1.001.dxf` and `new/as1.001.DXF`) are **all** reported as
   failures naming each other; none of them is translated (output names stay `<stem>_EN.*`).
   A sheet that had a GOST frame but whose title block gave no Part No. (any sheet), no name
   (first sheet; not on continuation sheets `_01`, `_02`…) or no material (part drawings; not
   on assembly drawings "СБ" nor continuation sheets) gets a per-sheet warning
   (`SheetResult.warnings`, surfaced in the result's warnings as `<file>: !! title block: …`);
   it counts as "needs attention" (exit 2). Sheets without a frame (translated by hand
   earlier) are not checked.
5. Run overlap check against sources.
6. Build review page `<out>/review/index.html` from this run's sheets only; a sheet whose
   PDF is missing is skipped with a warning.
7. Return a result object: sheets translated, failures (per file, with message),
   missing translations (unique texts, with file names where seen), overlaps
   (per file, text, count), warnings, paths of output/review.

Progress is reported through a callback (for the GUI progress bar).
Failure of one DXF must not abort the others.

Translation output for the current order must be **content-identical** to the existing
`~/Projects/translate/EN/dxf` (same texts at same positions, same removed entities) and
`check_overlaps` must report `TOTAL new overlaps: 0`.

### 4.2 Glossary

* Format: YAML, sections mirroring today's constants (phrases, substrings, notes,
  BOM materials, full materials, assembly suffix …), plus `part_no_pattern`: the regex a
  Part No. must match on the title block and in the Excel "Позначення" column (base
  `"^AS"`; an order glossary may override it).
* Base glossary is bundled (package data, embedded in the `.exe`).
* Per-order `glossary.yaml` next to the inputs; the GUI writes user-entered
  translations there (the file is rewritten; YAML comments are not kept).
* Promotion to base glossary: in Claude Code, "add order terms to base glossary" →
  Claude edits `data/glossary.yaml` and opens a PR; a release follows.

### 4.3 CLI

`dxf-translate <paths...> [--out DIR] [--no-review]` → runs `run_job`, prints the
summary (incl. `!! NO TRANSLATION` lines and `TOTAL new overlaps: N`), exit code 0 on
success, 1 if any file failed, 2 if missing translations, title-block warnings or overlaps
(so the skill can branch). Sub-commands or flags for running only the overlap check / review
are allowed: `--overlaps-only` prints `checked N of M sheet(s)`, lists sheets without output
as skipped and exits 1 if nothing was checked; `--crop PDF X Y` renders a 300 dpi PNG around a
sheet point and lists the review crops that contain it.

### 4.4 Desktop app (PySide6)

* UI language: Ukrainian.
* Window: drop zone (files or folder) + "choose files" button; version shown.
* Runs `run_job` in a worker thread; progress bar; log.
* Result panel: N sheets translated; failures; overlaps count + list;
  missing-translations table with an editable "English" column →
  "Save and re-run" writes order `glossary.yaml` and reruns.
* Buttons: "Open results folder", "Open review page".
* If overlaps > 0: hint "fix in Claude Code or manually".
* If no Excel: visible warning.

### 4.5 Claude Code plugin

* Repo is a plugin marketplace (`.claude-plugin/marketplace.json`) with one plugin.
* Install: `/plugin marketplace add <owner>/dxf-translate` then `/plugin install`.
* Skill `translate-drawings` encodes:
  * workflow: run CLI via `uv run --project <plugin dir> dxf-translate …`;
    on missing translations add them to order `glossary.yaml` (or base, on request)
    and rerun; on overlaps inspect full-resolution crops and fix — only the crops of the
    reported point (review crops containing it, or a `--crop` render), never every crop;
  * target EN layout rules: whole GOST frame removed (border, side strip, title block,
    mirrored number box), sheet size and view positions unchanged, roughness sign kept,
    technical requirements bottom-right followed by "Part No.: / Name: / Material:",
    hole callouts "12 отв. Ø5,5" → "12 X Ø5,5", decimal comma kept, tolerances
    unchanged, "Розгортка" → "Flat pattern", US "Aluminum", BOM/Excel material
    strings identical;
  * rule: always run the overlap checker after translating; never trust downscaled
    previews.

### 4.6 Release

GitHub Actions on tag `v*`: check the tag equals `v` + `dxf_translate.__version__` (the only
version source; `pyproject.toml` reads it dynamically), run tests, build Windows `.exe` with
PyInstaller (fonts + base glossary embedded), attach to GitHub Release.

## 5. Testing

* Unit tests: Excel classification, glossary merge, callout translation.
* Synthetic end-to-end test: generate a DXF with ezdxf (GOST frame, notes,
  "4 отв. Ø6" callout, Cyrillic texts), run `run_job`, assert: no Cyrillic left,
  frame removed, info block present, `new overlaps == 0`.
* Regression check (local only, not in CI — customer data): rerun current order,
  compare with existing `EN/dxf` by content.

## 6. Repository

* Private GitHub repo `virtuoz-star/dxf-translate`.
* Proprietary (no LICENSE file); fonts keep their own licenses.
* `.gitignore` excludes `*.dxf`, `*.xlsx`, `EN/`, `*.pdf` outside tests/fixtures.

## 7. Delivery order

1. Repo + core refactor (no hardcoded paths, YAML glossary, pyproject, CLI) + tests +
   regression check. Commit.
2. Plugin + skill. Commit.
3. Desktop app. Commit.
4. CI release build. Commit + tag.
