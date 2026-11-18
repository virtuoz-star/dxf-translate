# dxf-translate — single translation file (spec addendum)

Status: agreed 2026-11-18 (Q1–Q8). Supersedes the Excel parts of `docs/spec.md`
(§4.1 step 2, §4.3 inputs, §4.4 drop zone); everything else there stays.

## 1. Why

Today an order needs two Excel production lists (UA and EN) whose rows must line up cell for
cell. Rows drift as soon as somebody edits one file (the AS029 EN list already has blank
Item/Qty cells the UA list doesn't). One file with the UA and EN text side by side cannot drift.

## 2. The translation file

One `.xlsx`, first sheet. Header row = the first row that contains the five required headers
(exact text, surrounding whitespace ignored): `Позначення`, `Назва`, `Name`, `Матеріал`,
`Material`. Column order is free; other columns are allowed and kept.

| Ф | Поз. | Позначення | Назва | Name | Кільк. | Матеріал | Material | Довжина |
|---|---|---|---|---|---|---|---|---|
| Деталі (merged row) | | | | | | | | |
|   | 1 | AS18v1.110.016 | Втулка різьбова | Threaded bushing | 408 | Круг 12 алюм. | Round bar 12 Aluminum EN AW-6063 T5 | 15 |

* A data row is a row whose `Позначення` cell matches the glossary `part_no_pattern`.
* For each data row: `Назва`→`Name` and `Матеріал`→`Material` become glossary entries exactly as
  the old pair did (name → `phrases`; material → `full_material` and `bom_material`), and
  `parts[Part No.] = (Name, Material)`.
* Empty or still-Cyrillic `Name`/`Material` for a row with a UA value → a missing translation of
  kind `excel` (text = the UA value, plus the Part No.), shown with the hint "fill in the
  translation file, column Name/Material". The program never writes into the translation file.
* All other Cyrillic cells (headers, section rows such as `Деталі`, the `Ф` column such as `СК`)
  are translated through the glossary only when the EN list is exported (§4). Base glossary gains
  the AS029 ones: `Деталі`→`Parts`, `Зварювальні роботи`→`Welded assemblies`,
  `Контрольні збірки`→`Test assemblies`, `СК`→`AD` (headers are already there).
* A file without the required headers → `GlossaryError` naming the file and the missing headers.

The old UA + EN pair is **not supported** any more. A dev script `scripts/convert_pair.py UA EN OUT`
converts an old pair once (used for AS029).

## 3. Inputs

* The translation file is given **explicitly**; `.xlsx` files inside dropped folders are ignored.
  * CLI: `dxf-translate PATH... [--translations FILE.xlsx]`.
  * GUI: a separate input "Файл перекладу" (drop zone + "Обрати файл перекладу…" button),
    remembered until the window closes, so "Зберегти та перезапустити" reuses it; a "×" clears it.
  * Skill: passes `--translations` when the user names the file or exactly one `.xlsx` with the
    required headers sits in the order folder (Claude asks if unsure).
* Without a translation file the job still runs on the glossary only, with the existing
  `no_excel` warning (GUI text updated to "файл перекладу не вибрано").

## 4. English production list

With a translation file, the job also writes `<out>/<translation file stem>_EN.xlsx`:

* same rows, same order; the UA columns `Назва` and `Матеріал` are dropped;
* every other Cyrillic cell is translated via the glossary (`Ф`→`F`, `Поз.`→`Item`,
  `Позначення`→`Part No.`, `Кільк.`→`Qty`, `Довжина`→`Length`, section rows, `СК`); a Cyrillic cell
  without translation is kept and reported as a missing `phrase`;
* merged ranges, column widths, row heights, fonts, fills, borders and number formats are kept
  (merges recomputed for the removed columns);
* failure to write it (e.g. file open in Excel) → a warning, drawings are still produced.

## 5. Acceptance

* AS029 converted to one file; `dxf-translate <order> --translations <file>` gives `DIFF FILES: 0`
  against `_baseline/dxf` and `TOTAL new overlaps: 0`.
* The exported EN list equals `AS29V2 Production 2026.11.11.xlsx` cell for cell, except cells
  that were blank in that file but filled in the UA list (Item/Qty) — list them in the report.
