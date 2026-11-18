"""Desktop window tests (offscreen Qt). Skipped when the `gui` extra is not installed."""
import gc
from pathlib import Path
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

import yaml  # noqa: E402
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QDropEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from dxf_translate import __version__  # noqa: E402
from dxf_translate.gui import texts  # noqa: E402
from dxf_translate.gui.window import MainWindow  # noqa: E402
from fixtures import make_sheet  # noqa: E402

T = 60000


@pytest.fixture
def window(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    yield w
    w.wait_idle()
    w.close()
    w.deleteLater()
    QApplication.processEvents()       # run DeferredDelete on the UI thread
    gc.collect()


def _run(qtbot, window, paths):
    with qtbot.waitSignal(window.job_done, timeout=T):
        window.start(paths)


def test_version_shown(window):
    assert f"v{__version__}" in window.version_label.text()


def test_drop_runs_job(qtbot, window, tmp_path):
    make_sheet(tmp_path / "a.dxf")
    assert not window.open_dir_btn.isEnabled()
    _run(qtbot, window, [tmp_path])
    assert texts.COUNTS.format(ok=1, failed=0, overlaps=0) == window.counts_label.text()
    assert window.open_dir_btn.isEnabled() and window.open_review_btn.isEnabled()
    assert window.excel_warning.isVisibleTo(window)          # no Excel in the folder
    assert window.missing_table.rowCount() == 0


def test_controls_disabled_while_running(qtbot, window, tmp_path):
    make_sheet(tmp_path / "a.dxf")
    with qtbot.waitSignal(window.job_done, timeout=T):
        window.start([tmp_path])
        assert not window.choose_btn.isEnabled()
        assert not window.save_btn.isEnabled()
        assert not window.acceptDrops()
    assert window.choose_btn.isEnabled() and window.acceptDrops()


def test_drop_event_with_file_urls(qtbot, window, tmp_path):
    make_sheet(tmp_path / "a.dxf")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(tmp_path))])
    ev = QDropEvent(QPointF(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    with qtbot.waitSignal(window.job_done, timeout=T):
        window.dropEvent(ev)
    assert window.last_paths == [tmp_path]
    assert window.counts_label.text() == texts.COUNTS.format(ok=1, failed=0, overlaps=0)


def test_missing_saved_and_rerun(qtbot, window, tmp_path):
    make_sheet(tmp_path / "a.dxf", name="Невідома деталь")
    _run(qtbot, window, [tmp_path])
    t = window.missing_table
    assert t.rowCount() == 1 and t.item(0, 0).text() == "Невідома деталь"
    t.item(0, 3).setText("Mystery part")
    with qtbot.waitSignal(window.job_done, timeout=T):
        window.save_btn.click()
    data = yaml.safe_load((tmp_path / "glossary.yaml").read_text(encoding="utf-8"))
    assert data["phrases"]["Невідома деталь"] == "Mystery part"
    assert window.missing_table.rowCount() == 0
    assert window.result.missing == []


def test_save_skips_empty_cells(qtbot, window, tmp_path, monkeypatch):
    make_sheet(tmp_path / "a.dxf", name="Невідома деталь")
    _run(qtbot, window, [tmp_path])
    infos = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a: infos.append(a))
    window.save_btn.click()
    assert not (tmp_path / "glossary.yaml").exists() and infos


def test_part_rows_read_only(qtbot, window, tmp_path):
    from dxf_translate.pipeline import JobResult, MissingText
    res = JobResult(out_dir=tmp_path / "EN", order_dir=tmp_path,
                    missing=[MissingText("AS1.001", "part", ["a.dxf"])])
    window.show_result(res)
    item = window.missing_table.item(0, 3)
    assert not item.flags() & Qt.ItemIsEditable
    assert item.text() == texts.PART_FIX_EXCEL
    assert window.missing_table.item(0, 1).text() == texts.KINDS["part"]


def test_overlaps_hint(qtbot, window, tmp_path):
    from dxf_translate.overlaps import Overlap
    from dxf_translate.pipeline import JobResult
    res = JobResult(out_dir=tmp_path / "EN", order_dir=tmp_path,
                    overlaps=[Overlap("a_EN.dxf", "Part No.", 10.0, 20.0, 2)],
                    failed=[("b.dxf", "boom")])
    window.show_result(res)
    assert window.overlap_hint.isVisibleTo(window)
    assert window.overlaps_list.count() == 1 and window.failures_list.count() == 1
    assert window.counts_label.text() == texts.COUNTS.format(ok=0, failed=1, overlaps=1)


def test_xlsx_in_folder_ignored(qtbot, window, tmp_path, monkeypatch):
    import openpyxl
    make_sheet(tmp_path / "a.dxf")
    for name, text in (("one.xlsx", "Балка"), ("two.xlsx", "Деталь")):
        wb = openpyxl.Workbook(); wb.active["A1"] = text; wb.save(tmp_path / name)
    calls = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a: calls.append(a))
    _run(qtbot, window, [tmp_path])
    assert not calls and window.excel_warning.isVisibleTo(window)
    assert window.choose_btn.isEnabled()


def test_no_dxf_shows_ukrainian_error(qtbot, window, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a: calls.append(a))
    _run(qtbot, window, [tmp_path])
    assert calls and calls[0][2] == texts.NO_DXF


def test_worker_unexpected_error(qtbot, monkeypatch, tmp_path):
    from dxf_translate.gui import worker as worker_mod

    def boom(*a, **k):
        raise RuntimeError("kaput")
    monkeypatch.setattr(worker_mod, "run_job", boom)
    w = worker_mod.JobWorker([tmp_path])
    with qtbot.waitSignal(w.error, timeout=T) as sig:
        w.run()
    assert sig.args == ["RuntimeError: kaput"]


def test_open_buttons(qtbot, window, tmp_path, monkeypatch):
    from dxf_translate.gui import window as window_mod
    make_sheet(tmp_path / "a.dxf")
    _run(qtbot, window, [tmp_path])
    opened = []
    monkeypatch.setattr(window_mod.QDesktopServices, "openUrl", lambda u: opened.append(u.toLocalFile()))
    window.open_dir_btn.click()
    window.open_review_btn.click()
    assert [Path(u) for u in opened] == [Path(window.result.out_dir), Path(window.result.review)]


def test_gc_paused_during_job_and_worker_released(qtbot, window, tmp_path):
    make_sheet(tmp_path / "a.dxf")
    assert gc.isenabled()
    with qtbot.waitSignal(window.job_done, timeout=T):
        window.start([tmp_path])
        assert not gc.isenabled()          # no GC pass can run on the worker thread
    assert gc.isenabled()
    assert window.worker is None and window._thread is None


def test_gc_reenabled_after_error(qtbot, window, tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "critical", lambda *a: None)
    _run(qtbot, window, [tmp_path])        # no DXF -> error path
    assert gc.isenabled()
    assert window.worker is None and window._thread is None


def _missing_result(tmp_path, order_dir):
    from dxf_translate.pipeline import JobResult, MissingText
    return JobResult(out_dir=tmp_path / "EN", order_dir=order_dir,
                     missing=[MissingText("Невідома деталь", "phrase", ["a.dxf"])])


def test_save_unexpected_error_shown(qtbot, window, tmp_path, monkeypatch):
    from dxf_translate.gui import window as window_mod

    def boom(*a):
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(window_mod, "save_terms", boom)
    calls = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a: calls.append(a))
    window.last_paths = [tmp_path]
    window.show_result(_missing_result(tmp_path, tmp_path))
    window.missing_table.item(0, 3).setText("Mystery part")
    window.save_btn.click()
    assert calls and calls[0][2] == "RuntimeError: disk on fire"
    assert not window.busy


def test_save_without_order_dir_uses_out_parent(qtbot, window, tmp_path, monkeypatch):
    saved = []
    from dxf_translate.gui import window as window_mod
    monkeypatch.setattr(window_mod, "save_terms", lambda p, t: saved.append(p))
    monkeypatch.setattr(window, "start", lambda paths: None)
    window.last_paths = [tmp_path]
    window.show_result(_missing_result(tmp_path, None))
    window.missing_table.item(0, 3).setText("Mystery part")
    window.save_btn.click()
    assert saved == [tmp_path / "glossary.yaml"]


def test_worker_maps_no_inputs_by_type(qtbot, monkeypatch, tmp_path):
    from dxf_translate.gui import worker as worker_mod
    from dxf_translate.pipeline import NoInputsError

    def other(*a, **k):
        raise ValueError("no DXF files")    # same text, but not NoInputsError
    monkeypatch.setattr(worker_mod, "run_job", other)
    w = worker_mod.JobWorker([tmp_path])
    with qtbot.waitSignal(w.error, timeout=T) as sig:
        w.run()
    assert sig.args == ["no DXF files"]
    monkeypatch.setattr(worker_mod, "run_job", lambda *a, **k: (_ for _ in ()).throw(NoInputsError("x")))
    with qtbot.waitSignal(w.error, timeout=T) as sig:
        w.run()
    assert sig.args == [texts.NO_DXF]


def test_selftest_flag_exits_zero_without_window(qapp, capsys):
    from dxf_translate.gui import app
    assert app.main(["dxf-translate", "--selftest"]) == 0
    assert "selftest OK" in capsys.readouterr().out
    assert not [w for w in QApplication.topLevelWidgets() if w.isVisible()]


def test_failures_explained_in_ukrainian(qtbot, window, tmp_path):
    from dxf_translate.pipeline import JobResult
    tech = "PermissionError: [Errno 13] Permission denied: 'a_EN.pdf'"
    res = JobResult(out_dir=tmp_path / "EN", order_dir=tmp_path, failed=[("a.dxf", tech)],
                    warnings=["review failed: RuntimeError: x"])
    window.show_result(res)
    item = window.failures_list.item(0)
    assert item.text() == f"a.dxf: {texts.FILE_IN_USE}" and item.toolTip() == tech
    log = window.log.toPlainText()
    assert tech in log and texts.REVIEW_FAILED in log


# --- translation file input ------------------------------------------------------

TR_HEAD = ["Позначення", "Назва", "Name", "Матеріал", "Material"]


def _translations(path, rows):
    import openpyxl
    wb = openpyxl.Workbook()
    for r in [TR_HEAD] + rows:
        wb.active.append(r)
    wb.save(path)
    return path


def _drop(window, paths):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    window.dropEvent(QDropEvent(QPointF(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier))


def test_xlsx_drop_sets_translations(qtbot, window, tmp_path):
    make_sheet(tmp_path / "a.dxf", name="Невідома деталь")
    t = _translations(tmp_path / "t.xlsx", [["AS1.001", "Невідома деталь", "Mystery part",
                                             "Лист 3 алюм.", "Sheet 3 Al"]])
    with qtbot.waitSignal(window.job_done, timeout=T):
        _drop(window, [t, tmp_path])
    assert window.translations == t and window.last_paths == [tmp_path]
    assert window.translations_label.text() == "t.xlsx"
    assert window.result.translations is not None and window.result.missing == []
    assert not window.excel_warning.isVisibleTo(window)


def test_xlsx_alone_only_sets_translations(qtbot, window, tmp_path):
    t = _translations(tmp_path / "T.XLSX", [])
    _drop(window, [t])
    assert window.translations == t and not window.busy and window.last_paths == []
    assert window.clear_translations_btn.isEnabled()


def test_translations_reused_on_rerun_and_cleared(qtbot, window, tmp_path):
    make_sheet(tmp_path / "a.dxf", name="Невідома деталь")
    t = _translations(tmp_path / "t.xlsx", [["AS1.001", "Балка", "Beam", "Лист 3 алюм.", "Sheet 3 Al"]])
    window.set_translations(t)
    _run(qtbot, window, [tmp_path])
    assert window.result.translations.path == t
    window.missing_table.item(0, 3).setText("Mystery part")
    with qtbot.waitSignal(window.job_done, timeout=T):
        window.save_btn.click()
    assert window.result.translations.path == t and window.result.en_list.is_file()
    window.clear_translations_btn.click()
    assert window.translations is None and window.translations_label.text() == texts.NO_TRANSLATIONS
    assert not window.clear_translations_btn.isEnabled()
    _run(qtbot, window, [tmp_path])
    assert window.result.translations is None and window.excel_warning.isVisibleTo(window)
    assert window.excel_warning.text() == texts.NO_EXCEL


def test_translation_controls_disabled_while_running(qtbot, window, tmp_path):
    make_sheet(tmp_path / "a.dxf")
    window.set_translations(_translations(tmp_path / "t.xlsx", []))
    with qtbot.waitSignal(window.job_done, timeout=T):
        window.start([tmp_path])
        assert not window.choose_translations_btn.isEnabled()
        assert not window.clear_translations_btn.isEnabled()
    assert window.choose_translations_btn.isEnabled() and window.clear_translations_btn.isEnabled()


def test_excel_missing_row_readonly_with_hint(qtbot, window, tmp_path):
    from dxf_translate.pipeline import JobResult, MissingText
    res = JobResult(out_dir=tmp_path / "EN", order_dir=tmp_path,
                    missing=[MissingText("Кришка", "excel", [], "Name · AS1.009")])
    window.show_result(res)
    t = window.missing_table
    hint = texts.EXCEL_HINT.format(col="Name", pn="AS1.009")
    assert hint == "Впишіть у файл перекладу, колонка Name (AS1.009)"
    assert t.item(0, 0).text() == "Кришка" and t.item(0, 1).text() == "файл перекладу"
    assert t.item(0, 3).text() == hint and t.item(0, 3).toolTip() == hint
    assert not t.item(0, 3).flags() & Qt.ItemIsEditable
    assert window.collect_terms() == {}
    assert not window.save_btn.isEnabled()


def test_en_list_button(qtbot, window, tmp_path, monkeypatch):
    from dxf_translate.gui import window as window_mod
    make_sheet(tmp_path / "a.dxf")
    window.set_translations(_translations(tmp_path / "List.xlsx", [["AS1.001", "Балка", "Beam",
                                                                    "Лист 3 алюм.", "Sheet 3 Al"]]))
    assert not window.en_list_label.isVisibleTo(window)
    _run(qtbot, window, [tmp_path])
    assert window.en_list_label.isVisibleTo(window)
    assert window.en_list_label.text() == "Англійський виробничий список: List_EN.xlsx"
    assert window.open_en_list_btn.isEnabled() and window.open_en_list_btn.text() == "Відкрити список"
    opened = []
    monkeypatch.setattr(window_mod.QDesktopServices, "openUrl", lambda u: opened.append(u.toLocalFile()))
    window.open_en_list_btn.click()
    assert [Path(u) for u in opened] == [tmp_path / "EN" / "List_EN.xlsx"]


def test_en_list_failed_and_formula_explained(qtbot, window, tmp_path):
    from dxf_translate.pipeline import JobResult
    res = JobResult(out_dir=tmp_path / "EN", order_dir=tmp_path, warnings=[
        "en_list_failed: PermissionError: [Errno 13] Permission denied: 'List_EN.xlsx'",
        "en_list_formula: formula in F4 (=G3) refers to dropped column Матеріал"])
    window.show_result(res)
    assert window.en_list_label.isVisibleTo(window)
    assert window.en_list_label.text() == texts.EN_LIST_FAILED
    assert texts.EN_LIST_FAILED == "Не вдалося записати англійський список (файл відкритий у Excel?)"
    assert not window.open_en_list_btn.isVisibleTo(window)
    log = window.log.toPlainText()
    assert texts.EN_LIST_FAILED in log and texts.EN_LIST_FORMULA in log


def test_bad_translation_file_error_in_ukrainian(qtbot, window, tmp_path, monkeypatch):
    make_sheet(tmp_path / "a.dxf")
    bad = tmp_path / "old.xlsx"
    import openpyxl
    wb = openpyxl.Workbook(); wb.active.append(["Позначення", "Назва", "Матеріал"]); wb.save(bad)
    calls = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a: calls.append(a))
    window.set_translations(bad)
    _run(qtbot, window, [tmp_path])
    assert calls and calls[0][2].startswith(texts.NOT_TRANSLATION_FILE)


def test_worker_passes_translations(qtbot, monkeypatch, tmp_path):
    from dxf_translate.gui import worker as worker_mod
    seen = {}
    monkeypatch.setattr(worker_mod, "run_job", lambda paths, **k: seen.update(k) or "res")
    w = worker_mod.JobWorker([tmp_path], tmp_path / "t.xlsx")
    with qtbot.waitSignal(w.finished, timeout=T):
        w.run()
    assert seen["translations"] == tmp_path / "t.xlsx"


def test_new_translation_file_resets_result_panel(qtbot, window, tmp_path):
    make_sheet(tmp_path / "a.dxf", name="Невідома деталь")
    window.set_translations(_translations(tmp_path / "List.xlsx", []))
    _run(qtbot, window, [tmp_path])
    assert window.en_list_label.isVisibleTo(window) and window.missing_table.rowCount() == 1
    window.set_translations(_translations(tmp_path / "Other.xlsx", []))
    assert window.result is None and window.missing_table.rowCount() == 0
    assert not window.en_list_label.isVisibleTo(window)
    assert not window.open_en_list_btn.isVisibleTo(window)
    assert not window.missing_box.isVisibleTo(window) and window.counts_label.text() == ""
    assert not window.save_btn.isEnabled() and not window.open_dir_btn.isEnabled()
    assert window.last_paths == [tmp_path]          # the DXF input is kept


def test_same_translation_file_keeps_result(qtbot, window, tmp_path):
    make_sheet(tmp_path / "a.dxf")
    t = _translations(tmp_path / "List.xlsx", [])
    window.set_translations(t)
    _run(qtbot, window, [tmp_path])
    window.set_translations(t)
    assert window.result is not None and window.en_list_label.isVisibleTo(window)
