# dxf-translate — developer notes

Python 3.12 package `dxf_translate` (`src/`), managed with `uv`. The repo root is also a
Claude Code plugin + marketplace (`.claude-plugin/`, skill in `skills/translate-drawings/`).

## Tests

    uv run pytest

Tests build synthetic sheets with `dxf_translate._selftest.make_sheet` (re-exported by `tests/fixtures.py`) in `tmp_path`; never add real drawings as fixtures. The same sheet backs `dxf-translate-gui --selftest`.

## Windows build

`uv run pyinstaller packaging/dxf-translate.spec` then `dist/dxf-translate --selftest` (exit 0). CI: `.github/workflows/test.yml` (push/PR, ubuntu + windows), `release.yml` (tag `v*` → exe on the GitHub Release). Fonts are bundled-only (`fonts.setup()` clears ezdxf's system font cache).

## Regression check (before merging changes to translation, glossary or overlap logic)

1. On `master`, translate a reference order into a baseline folder:
   `uv run dxf-translate <order> --out /tmp/baseline --no-review`
2. On your branch, translate the same order into another folder:
   `uv run dxf-translate <order> --out /tmp/candidate --no-review`
3. Compare: `uv run python scripts/compare_dxf.py /tmp/baseline/dxf /tmp/candidate/dxf`
   — last line `DIFF FILES: N`, exit 0 iff no differences. Explain every intended difference in the PR.
4. The candidate run must still print `TOTAL new overlaps: 0`.

## Rules

* Never commit customer data: no `*.dxf`, `*.xlsx`, `*.pdf`, `EN/` output, order `glossary.yaml`
  files or crops (`.gitignore` covers the file types — don't force-add).
* Base glossary (`src/dxf_translate/data/glossary.yaml`) changes go through a branch + PR, never
  straight to `master`; a release follows.
* Skill changes: keep `skills/translate-drawings/SKILL.md` in sync with the CLI flags/output and with
  the layout rules in `docs/spec.md` §4.5; run `claude plugin validate .` after editing manifests.
