# dxf-translate

Translates Ukrainian SolidWorks DXF drawings to English (glossary-driven, layout-aware):
removes the GOST frame, translates names, BOM, technical requirements and callouts,
writes `EN/dxf/*_EN.dxf` + `EN/pdf/*.pdf`, checks text/line overlaps and builds a review page.

## Швидкий старт (українською)

**Варіант 1 — програма для Windows.** Завантажте `.exe` з
[GitHub Releases](https://github.com/virtuoz-star/dxf-translate/releases), перетягніть папку
з DXF-кресленнями у вікно. Результат — у папці `EN` поруч із кресленнями.
Під час першого запуску Windows SmartScreen може попередити про невідомого видавця —
натисніть «Докладніше» → «Усе одно запустити» (More info → Run anyway).

**Варіант 2 — Claude Code.**

1. Встановіть [Claude Code](https://code.claude.com/docs) та
   [`uv`](https://docs.astral.sh/uv/getting-started/installation/).
2. У Claude Code виконайте:

       /plugin marketplace add virtuoz-star/dxf-translate
       /plugin install dxf-translate@dxf-translate

3. Напишіть, наприклад: «Переклади креслення в папці C:\Замовлення\AS029». Claude запустить
   перекладач і запропонує переклад для невідомих термінів; після вашого підтвердження (або
   виправлень) запише їх у `glossary.yaml` замовлення. Базовий глосарій змінюється лише на ваше
   окреме прохання. Потім Claude перевірить накладання тексту і дасть посилання на сторінку перегляду `EN/review/index.html`.

## Claude Code plugin

The repository root is both a plugin marketplace (`.claude-plugin/marketplace.json`) and the
plugin itself (`.claude-plugin/plugin.json`, source `"./"`). The plugin root has to be the repo
root: an installed plugin is copied into the plugin cache without anything outside its source
directory, and the skill runs the Python package that lives next to it.

Prerequisites: [Claude Code](https://code.claude.com/docs) installed, and
[`uv`](https://docs.astral.sh/uv/) on `PATH`.

    /plugin marketplace add virtuoz-star/dxf-translate
    /plugin install dxf-translate@dxf-translate

The skill `dxf-translate:translate-drawings` runs
`uv run --project "${CLAUDE_PLUGIN_ROOT}" dxf-translate <folder>`; the first run creates a
virtual environment inside the installed plugin copy. For missing terms it proposes English
translations, waits for the user's OK or corrections, then writes them to the order glossary
(the base glossary only on explicit request, via branch + PR). It inspects overlap crops at full resolution and reruns until `TOTAL new overlaps: 0`.

To try a local checkout without installing: `claude --plugin-dir /path/to/dxf-translate`.

## Desktop app

Windows: download `dxf-translate-<version>.exe` from
[GitHub Releases](https://github.com/virtuoz-star/dxf-translate/releases) — a single file, no
install. The exe is not code-signed, so on first launch Windows SmartScreen shows
"Windows protected your PC": click **More info → Run anyway**. Drop a folder with DXF drawings
(and optionally the UA/EN Excel lists) onto the window; results go to `EN` next to them.

From source: `uv sync --extra gui && uv run dxf-translate-gui [PATH...]`.
Build the exe: `uv run pyinstaller packaging/dxf-translate.spec` → `dist/dxf-translate(.exe)`;
`dist/dxf-translate --selftest` translates a generated sheet without a window and exits 0/1.
Tags `v*` build and publish the Windows exe via `.github/workflows/release.yml`.

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
