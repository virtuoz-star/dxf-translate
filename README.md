# dxf-translate

Translates Ukrainian SolidWorks DXF drawings to English (glossary-driven, layout-aware):
removes the GOST frame, translates names, BOM, technical requirements and callouts,
writes `EN/dxf/*_EN.dxf` + `EN/pdf/*.pdf`, checks text/line overlaps and builds a review page.

## Швидкий старт (українською)

**Варіант 1 — програма для Windows.** Завантажте `.exe` з
[GitHub Releases](https://github.com/virtuoz-star/dxf-translate/releases), перетягніть папку
з DXF-кресленнями у вікно. Результат — у папці `EN` поруч із кресленнями.

**Варіант 2 — Claude Code.**

1. Встановіть [`uv`](https://docs.astral.sh/uv/getting-started/installation/).
2. У Claude Code виконайте:

       /plugin marketplace add virtuoz-star/dxf-translate
       /plugin install dxf-translate@dxf-translate

3. Напишіть, наприклад: «Переклади креслення в папці C:\Замовлення\AS029». Claude запустить
   перекладач, запропонує переклад для невідомих термінів (запише їх у `glossary.yaml` замовлення),
   перевірить накладання тексту і дасть посилання на сторінку перегляду `EN/review/index.html`.

## Claude Code plugin

The repository root is both a plugin marketplace (`.claude-plugin/marketplace.json`) and the
plugin itself (`.claude-plugin/plugin.json`, source `"./"`). The plugin root has to be the repo
root: an installed plugin is copied into the plugin cache without anything outside its source
directory, and the skill runs the Python package that lives next to it.

Prerequisite: [`uv`](https://docs.astral.sh/uv/) on `PATH`.

    /plugin marketplace add virtuoz-star/dxf-translate
    /plugin install dxf-translate@dxf-translate

(Claude Code 2.1.275+ also accepts the one-step form
`/plugin install dxf-translate --marketplace virtuoz-star/dxf-translate`.)

The skill `dxf-translate:translate-drawings` runs
`uv run --project "${CLAUDE_PLUGIN_ROOT}" dxf-translate <folder>`; the first run creates a
virtual environment inside the installed plugin copy. It then fills missing terms in the order
glossary, inspects overlap crops at full resolution and reruns until `TOTAL new overlaps: 0`.

To try a local checkout without installing: `claude --plugin-dir /path/to/dxf-translate`.

## Desktop app

Windows build: [GitHub Releases](https://github.com/virtuoz-star/dxf-translate/releases).

## CLI

    uv sync
    uv run dxf-translate PATH... [--out DIR] [--no-review] [--overlaps-only]

* `PATH` — DXF/XLSX files or folders; folders are scanned recursively (skips `EN/`, `*_EN.dxf`, `~$*`).
* Output: `<first folder>/EN` (or `<folder of first DXF>/EN`) unless `--out` is given:
  `dxf/*_EN.dxf`, `pdf/*.pdf`, `review/index.html`, `review/crops/*.png`.
* Excel: one UA + one EN production list among the inputs adds UA→EN pairs; none → warning.
* Glossary: bundled base `src/dxf_translate/data/glossary.yaml`, overridden by `glossary.yaml`
  in the order folder (sections `phrases`, `full_material`, `bom_material`, `notes`, `substr`,
  `assembly_suffix`).
* `--overlaps-only` re-checks existing `<out>/dxf/*_EN.dxf` without translating.
* Output lines: `!! NO TRANSLATION: …`, `file: 'text' at (x, y) mm crosses n line(s)`,
  `TOTAL new overlaps: N`.
* Exit code: `0` ok, `1` a file failed or bad glossary/Excel, `2` missing translations or overlaps.

## Development

See `CLAUDE.md`. Tests: `uv run pytest`. Compare two output folders:

    uv run python scripts/compare_dxf.py <dir_a> <dir_b>
