# Single Translation File Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the UA+EN Excel pair with one explicitly given translation file, export the English production list from it, and give the GUI a separate translation-file input.

**Architecture:** `excel.py` is rewritten around one workbook (`read_translations`, `export_en`); the pair code is deleted. `run_job` gets a `translations: Path | None` argument and stops collecting `.xlsx` from folders. CLI gets `--translations`; GUI gets a second input; skill/README/guide follow.

**Tech Stack:** Python 3.12, openpyxl, ezdxf 1.4.5, PySide6, pytest/pytest-qt, uv.

**Spec:** `docs/spec-translation-file.md` (addendum to `docs/spec.md`)

## Global Constraints

- Repo `/home/king/Projects/dxf-translate`, branch master; commit trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; push only when the controller says.
- Never commit customer data (`*.dxf`, `*.xlsx`, `*.pdf`, `*.png`); test workbooks are generated in `tmp_path`.
- Required headers (exact): `Позначення`, `Назва`, `Name`, `Матеріал`, `Material`.
- Old UA+EN pair: not supported (no code path left for it).
- `.xlsx` inside dropped folders are ignored; translation file only via `--translations` / GUI input.
- EN list path: `<out>/<translation file stem>_EN.xlsx`.
- Program never writes into the translation file.
- Regression: AS029 must give `DIFF FILES: 0` vs `/home/king/Projects/translate/_baseline/dxf` and `TOTAL new overlaps: 0`.
- GUI copy Ukrainian, in `gui/texts.py`.

## Review Focus

- Translation file open in Excel on Windows (locked) while exporting → warning, drawings still produced. Test in Task 2 (monkeypatch save to raise PermissionError).
- Header row not the first row / extra columns / reordered columns → still read. Test in Task 1.
- Merged section rows spanning the dropped UA columns → merges recomputed, no openpyxl error. Test in Task 2.
- User passes the EN export (`*_EN.xlsx`) or an old-format list as `--translations` → clear GlossaryError naming missing headers. Test in Task 1.
- GUI: translation file chosen, then DXF folder dropped twice → second run still uses the file; "×" clears it. Test in Task 3.

---

### Task 1: Read the translation file; CLI/pipeline input; convert AS029

**Files:**
- Modify: `src/dxf_translate/excel.py` (replace pair code), `src/dxf_translate/pipeline.py`, `src/dxf_translate/cli.py`, `src/dxf_translate/data/glossary.yaml`
- Create: `scripts/convert_pair.py`, `tests/test_translations.py`
- Modify tests: `tests/test_excel.py` (delete pair tests), `tests/test_pipeline.py`, `tests/test_cli.py`
- Modify: `skills/translate-drawings/SKILL.md`, `README.md` (CLI usage + skill wording), `docs/spec.md` (pointer to the addendum in §4.1)

**Interfaces:**
- Produces:
  ```python
  # excel.py
  REQUIRED = ("Позначення", "Назва", "Name", "Матеріал", "Material")
  @dataclass
  class TranslationFile:
      path: Path
      header_row: int                    # 1-based
      cols: dict[str, int]               # header text -> 1-based column, for every non-empty header cell
      pairs: int                         # glossary entries added
      missing: list[tuple[str, str, str]]  # (ua_text, column "Name"|"Material", part_no)
  def read_translations(g: Glossary, path: Path) -> TranslationFile   # GlossaryError on unreadable file / missing headers (message lists the missing ones)
  ```
  ```python
  # pipeline.py
  def collect_inputs(paths: list[Path]) -> list[Path]          # DXFs only now
  def run_job(paths, out_dir=None, progress=None, review=True, translations: Path | None = None) -> JobResult
  # JobResult: `excel`/`excel_pairs` replaced by `translations: TranslationFile | None`; missing kind "excel" for TranslationFile.missing (MissingText.text = ua_text, files = [], new field `hint: str = ""` = f"{column} · {part_no}")
  ```
  CLI: `--translations FILE`; summary line `Translation file: N UA->EN pairs from <name>`; kind `excel` printed as `!! TRANSLATION FILE: fill <column> for <part_no>: <ua_text>`; counts toward exit 2.
- `scripts/convert_pair.py UA EN OUT`: writes one workbook: UA sheet copied (values + styles + merges + widths), with a `Name` column inserted right after `Назва` and `Material` right after `Матеріал`, filled from the EN file's same cells; prints how many cells were filled.

- [ ] **Step 1: Tests (`tests/test_translations.py`)** — build workbooks with openpyxl in tmp_path:
  - `test_reads_pairs_and_parts`: header in row 1, one data row `AS1.001 | Балка | Beam-EN | Лист 3 алюм. | Sheet 3 Al` → `pairs >= 2`, `g.phrases["Балка"]=="Beam-EN"`, `g.full_material`/`g.bom_material` have the material, `g.parts["AS1.001"]==("Beam-EN","Sheet 3 Al")`.
  - `test_header_not_first_row_and_reordered`: two title rows above the header, columns shuffled, an extra column → same result.
  - `test_missing_name_reported`: empty `Name` and Cyrillic `Material` → `missing == [("Балка","Name","AS1.001"), ("Лист 3 алюм.","Material","AS1.001")]` (order by row then column), nothing added for them.
  - `test_missing_headers_error`: workbook with only UA headers (old format) → `GlossaryError` whose message contains `Name` and `Material`; garbage bytes → `GlossaryError` naming the file.
  - pipeline: `test_folder_xlsx_ignored` (xlsx in the dropped folder, no `--translations` → `"no_excel" in warnings`, no error); `test_translations_used` (unknown fixture name translated via the file); `test_excel_missing_exit_2`.
  - CLI: `--translations` works; old-format file → exit 1, stderr names missing headers.
- [ ] **Step 2:** FAIL → **Step 3:** implement; delete `pick_pair`, `classify`, `add_excel_pairs` and their tests; base glossary gains `Деталі: Parts`, `Зварювальні роботи: Welded assemblies`, `Контрольні збірки: Test assemblies`, `СК: AD` under phrases (comment "production list"). Update `tests/test_glossary.py::test_base_sizes_frozen` counts. → **Step 4:** PASS (`uv run --extra gui pytest`, and plain `uv run pytest`).
- [ ] **Step 5: Convert + regression:** `uv run python scripts/convert_pair.py "/home/king/Projects/translate/AS29V2 Виробництво 2026.11.11.xlsx" "/home/king/Projects/translate/AS29V2 Production 2026.11.11.xlsx" "/home/king/Projects/translate/AS29V2 2026.11.11.xlsx"`; make a fresh scratch order `/home/king/Projects/translate/_e2e2/` with `dxf/` copied from `/home/king/Projects/translate/dxf`; `uv run dxf-translate /home/king/Projects/translate/_e2e2 --translations "/home/king/Projects/translate/AS29V2 2026.11.11.xlsx"` → compare with `_baseline/dxf` → `DIFF FILES: 0`, overlaps 0, exit 0.
- [ ] **Step 6:** SKILL.md: pass `--translations` per spec §3; README CLI section. Commit `feat: single translation file replaces the UA/EN Excel pair`.

### Task 2: Export the English production list

**Files:**
- Modify: `src/dxf_translate/excel.py`, `src/dxf_translate/pipeline.py`, `src/dxf_translate/cli.py`
- Test: `tests/test_export_en.py`

**Interfaces:**
- Consumes: `TranslationFile` (Task 1), `Glossary.lookup`.
- Produces:
  ```python
  def export_en(tf: TranslationFile, g: Glossary, out_dir: Path) -> tuple[Path, list[str]]   # (written path, untranslated Cyrillic cells as UA text)
  # JobResult gains: en_list: Path | None
  ```
  `run_job` calls it after translating sheets when `translations` is given; untranslated cells → `MissingText(kind="phrase")`; any exception while writing → warning `"en_list_failed: <TypeName>: <msg>"` (GUI/CLI show it), job continues. CLI prints `EN production list: <path>`.
- Cell rules: drop columns `Назва` and `Матеріал`; header cells and other Cyrillic cells via `g.lookup("phrases", text)` (exact after `norm`); keep numbers/Latin untouched; copy styles (font, fill, border, alignment, number_format, protection), column widths (shifted), row heights, and merged ranges recomputed (a merge fully inside dropped columns is removed; a merge spanning them shrinks).

- [ ] **Step 1: Tests**
  - `test_columns_dropped_and_headers_translated`: header `Ф|Поз.|Позначення|Назва|Name|Кільк.|Матеріал|Material|Довжина` → exported header `F|Item|Part No.|Name|Qty|Material|Length`, data row values match, column widths of kept columns preserved.
  - `test_merged_section_row`: merged A2:I2 `Деталі` → exported merged A2:G2 `Parts`; a style (bold) on the section cell survives.
  - `test_untranslated_cell_reported`: section `Невідомий розділ` → returned in the list, cell kept as is.
  - `test_locked_file_warning` (pipeline): monkeypatch workbook save to raise `PermissionError` → `JobResult.en_list is None`, warning starts with `en_list_failed`, sheets translated, `exit_code == 2` (the warning needs attention).
- [ ] **Step 2:** FAIL → **Step 3:** implement → **Step 4:** PASS.
- [ ] **Step 5: Regression:** rerun Task 1 Step 5 command; then a throwaway script compares `<out>/AS29V2 2026.11.11_EN.xlsx` with `/home/king/Projects/translate/AS29V2 Production 2026.11.11.xlsx` cell by cell (values): report every difference; acceptable only where the original EN cell is blank and the UA one isn't (Item/Qty). `DIFF FILES: 0` still.
- [ ] **Step 6:** Commit `feat: export English production list`.

### Task 3: GUI translation-file input, docs

**Files:**
- Modify: `src/dxf_translate/gui/window.py`, `gui/worker.py`, `gui/texts.py`, `tests/test_gui.py`, `README.md`, `skills/translate-drawings/SKILL.md` (if wording left), `/tmp/claude-1000/-home-king-Projects-translate/3aa28791-b844-45de-a7be-2fa43bc6fca4/scratchpad/dxf-guide/index.html` (colleague guide; controller republishes)

**Interfaces:**
- Consumes: `run_job(..., translations=)`, `JobResult.translations`, `JobResult.en_list`, `MissingText.kind == "excel"` with `hint`.
- `JobWorker(paths, translations: Path | None)`.
- `MainWindow.translations: Path | None`; `set_translations(path: Path | None)`; drop handling: a dropped `.xlsx` (alone or with DXF/folders) sets the translation file, everything else goes to the DXF input; translation zone label shows the file name or `texts.NO_TRANSLATIONS`; buttons "Обрати файл перекладу…" and "×".
- Result panel: line "Англійський виробничий список: <name>" + button "Відкрити список" when `en_list`; missing rows of kind `excel` read-only, Тип = "файл перекладу", tooltip/hint "Впишіть у файл перекладу, колонка Name/Material (<Part No.>)"; warning `no_excel` text → "Файл перекладу не вибрано — назви та матеріали перекладаються лише за глосарієм"; `en_list_failed` → "Не вдалося записати англійський список (файл відкритий у Excel?)".

- [ ] **Step 1: Tests:** `test_xlsx_drop_sets_translations` (drop xlsx + folder in one QMimeData → translations set, job paths exclude the xlsx); `test_translations_reused_on_rerun_and_cleared`; `test_excel_missing_row_readonly_with_hint`; `test_en_list_button`.
- [ ] **Step 2:** FAIL → **Step 3:** implement → **Step 4:** PASS (run test_gui.py 20× in a loop, no segfault).
- [ ] **Step 5:** Offscreen screenshot of a fixture run with a translation file that has one empty Name → `/home/king/Projects/translate/_e2e2/gui-translations.png`; view it.
- [ ] **Step 6:** README (UA + EN) and the colleague guide: "Що підготувати" → one translation file with Name/Material columns next to Назва/Матеріал; the window's second input; EN list in results. Commit `feat: GUI translation-file input; docs`.
