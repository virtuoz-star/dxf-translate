---
name: translate-drawings
description: Translates Ukrainian SolidWorks DXF drawings (sheets, BOM, technical requirements) to English with the dxf-translate CLI, fills missing glossary terms, and fixes text overlaps until the overlap check is clean. Use when the user asks to translate drawings or DXF files, mentions креслення, перекласти креслення, перевести чертежи, чертежи DXF, or drops a folder of SolidWorks DXF exports to be made English.
---

# Translate drawings (UA → EN)

The CLI lives in this plugin. Run it with:

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" dxf-translate "<ABS_PATH>" [more paths] [--out DIR] [--no-review] [--overlaps-only]
```

- **Plugin root:** if `${CLAUDE_PLUGIN_ROOT}` above is empty or unexpanded, use the skill's base directory shown when this skill loaded and go two levels up (`skills/translate-drawings` → plugin root). Before the first run, check the root contains `pyproject.toml`.
- **Shell:** run commands with the Bash tool (Git Bash on Windows). Always double-quote paths (Cyrillic, spaces) and prefer forward slashes: `"C:/Замовлення/AS029"` (quoted backslashes also work). If the shell is PowerShell, write the literal plugin root path instead of the variable.
- `uv` must be installed (`uv --version`). If missing, tell the user to install it (https://docs.astral.sh/uv/) and stop.
- `--project` does not change the working directory: always pass **absolute** input paths.
- A folder is scanned recursively (skips `EN/`, `*_EN.dxf`, `~$*`). Output goes to `<folder>/EN` (`dxf/`, `pdf/`, `review/`).
- Order glossary = `<folder>/glossary.yaml` (sections `phrases`, `full_material`, `bom_material`, `notes`, `substr`, `assembly_suffix`). Order entries override the base glossary.
- Exit codes: `0` ok, `1` a file failed or bad glossary/Excel (message on stderr), `2` missing translations or overlaps.

## Workflow

1. **Run** the CLI on the user's folder (absolute path). Read the exit code and the whole output.
2. **Exit 1:** show the `!! FAILED` / `error:` lines. Fix a broken `glossary.yaml` yourself (the message names file and line); otherwise report to the user. Continue with the sheets that did translate.
3. **Exit 2 with `!! NO TRANSLATION: a | b`:**
   - Propose an English term for each missing text, following the layout rules below. Show the list to the user and **wait for their OK or corrections** before writing anything.
   - Then write the approved terms to `<folder>/glossary.yaml` by editing the YAML: whole labels/names/BOM cells → `phrases`; technical-requirement lines → `notes`; materials → `full_material` + `bom_material` (identical to the Excel string). Create the file if absent. Quote keys that start with `*`, contain `: ` or `#`.
   - Rerun step 1. Repeat until no `!! NO TRANSLATION` remains.
   - Touch the base glossary (`<plugin root>/src/dxf_translate/data/glossary.yaml`) only on the user's explicit request, and then via a branch + PR in a clone of the `dxf-translate` repository — never edit the installed copy.
4. **Overlaps (`TOTAL new overlaps: N`, N > 0):**
   - Open every crop in `<out>/review/crops/*.png` with the Read tool at full resolution. Never judge from downscaled previews or the whole-sheet PDF.
   - Fix by shorter wording in the order glossary first (show the proposed change to the user as in step 3), then rerun step 1 (a full run is needed — `--overlaps-only` does not retranslate).
   - If wording cannot fix it, edit the output DXF in `<out>/dxf/` (e.g. with ezdxf via `uv run --project "<plugin root>" python …`) and verify with `--overlaps-only` on the same input path. A later full run overwrites such manual edits — tell the user.
   - Done = `TOTAL new overlaps: 0`, or the user explicitly accepted each remaining listed overlap.
5. **Always** run the overlap check after translating (every full run does it). Never declare success without seeing `TOTAL new overlaps: 0` in the latest output.
6. **Report** to the user: number of sheets translated, failures (file + message), terms you added (and where), remaining overlaps if accepted, and the paths of `<out>/pdf/` and the review page `<out>/review/index.html`.

## Target EN layout rules (spec §4.5)

- whole GOST frame removed (border, side strip, title block, mirrored number box)
- sheet size and view positions unchanged
- roughness sign kept
- technical requirements bottom-right followed by "Part No.: / Name: / Material:"
- hole callouts "12 отв. Ø5,5" → "12 X Ø5,5"
- decimal comma kept
- tolerances unchanged
- "Розгортка" → "Flat pattern"
- US "Aluminum"
- BOM/Excel material strings identical
- always run the overlap checker after translating; never trust downscaled previews.
