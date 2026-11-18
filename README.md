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
Програма — один файл, який при кожному запуску спершу розпаковується, тому перший старт
(особливо після завантаження чи перевірки антивірусом) може тривати 10–30 секунд.
Переклади, введені у вікні («Зберегти та перезапустити»), записуються у `glossary.yaml`
в корені папки замовлення (поруч із перетягнутою папкою/кресленнями); файл перезаписується
повністю, коментарі в ньому не зберігаються.

**Варіант 2 — Claude Code.** Потрібен встановлений і авторизований
[Claude Code](https://code.claude.com/docs) (передплата Claude або API-ключ).

1. Встановіть [Claude Code](https://code.claude.com/docs) та
   [`uv`](https://docs.astral.sh/uv/getting-started/installation/).
2. У Claude Code виконайте:

       /plugin marketplace add virtuoz-star/dxf-translate
       /plugin install dxf-translate@dxf-translate

3. Напишіть, наприклад: «Переклади креслення в папці C:\Замовлення\AS029». Claude запустить
   перекладач і запропонує переклад для невідомих термінів; після вашого підтвердження (або
   виправлень) запише їх у `glossary.yaml` замовлення. Базовий глосарій змінюється лише на ваше
   окреме прохання. Потім Claude перевірить накладання тексту і дасть посилання на сторінку перегляду `EN/review/index.html`.

## Доступ / Access

Репозиторій приватний. / The repository is private.

* **UA:** ваш обліковий запис GitHub має бути доданий до репозиторію `virtuoz-star/dxf-translate`
  (попросіть власника). Програму `.exe` завантажуйте зі сторінки Releases, увійшовши в GitHub.
  Для плагіна Claude Code git має мати доступ до приватного репозиторію: виконайте
  `gh auth login` ([GitHub CLI](https://cli.github.com/)) або увійдіть через Git Credential
  Manager (входить до Git for Windows) — перевірка: `git ls-remote https://github.com/virtuoz-star/dxf-translate`.
  Для фонового автооновлення плагіна Claude Code потрібен токен у змінній середовища
  `GITHUB_TOKEN` (або `GH_TOKEN`) з правом читання цього репозиторію.
* **EN:** your GitHub account must be added to `virtuoz-star/dxf-translate` (ask the owner);
  download the `.exe` from Releases while signed in. The Claude Code plugin is fetched with
  git, so git needs credentials for the private repo: `gh auth login` or Git Credential Manager
  (bundled with Git for Windows); check with `git ls-remote https://github.com/virtuoz-star/dxf-translate`.
  Background plugin auto-updates need a token in `GITHUB_TOKEN` (or `GH_TOKEN`) with read
  access to the repo.

## Claude Code plugin

The repository root is both a plugin marketplace (`.claude-plugin/marketplace.json`) and the
plugin itself (`.claude-plugin/plugin.json`, source `"./"`). The plugin root has to be the repo
root: an installed plugin is copied into the plugin cache without anything outside its source
directory, and the skill runs the Python package that lives next to it.

Prerequisites: [Claude Code](https://code.claude.com/docs) installed and signed in (Claude
subscription or API key), git access to the private repo (see "Access"), and
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
The exe is a PyInstaller one-file build that unpacks itself on every start, so the first
start (especially right after download / an antivirus scan) can take 10–30 s.
"Save and re-run" writes the entered translations to `glossary.yaml` in the order root (the
dropped folder, or the folder of the first dropped DXF); the file is rewritten as a whole, so
YAML comments in it are lost.

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
  `assembly_suffix`, `part_no_pattern` — regex a Part No. must match, base `"^AS"`).
* Inputs whose output names would collide (same file name in two sub-folders, case-insensitive)
  all fail with `output name collision`; nothing is translated for them.
* `--overlaps-only` re-checks existing `<out>/dxf/*_EN.dxf` without translating; prints
  `checked N of M sheet(s)` and `!! SKIPPED` for sheets without output (exit 1 if none checked).
* `--crop PDF X Y` renders an 80 × 50 mm, 300 dpi PNG around sheet point (X, Y) mm of an EN PDF
  into `<out>/review/points/` and lists the review crops containing that point.
* Output lines: `!! NO TRANSLATION: …`, `file: !! title block: … not found` (a framed sheet
  whose Part No. / name / material could not be read), `file: 'text' at (x, y) mm crosses n
  line(s)`, `TOTAL new overlaps: N`.
* Exit code: `0` ok, `1` a file failed or bad glossary/Excel, `2` missing translations,
  title-block warnings or overlaps.

## Development

See `CLAUDE.md`. Tests: `uv run pytest`. Compare two output folders:

    uv run python scripts/compare_dxf.py <dir_a> <dir_b>
