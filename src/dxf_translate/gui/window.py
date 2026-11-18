"""Main window: drop zone, progress, result panel, missing-translation editor."""
from __future__ import annotations

import gc
from pathlib import Path

from PySide6.QtCore import QThread, QUrl, Qt, Signal, Slot
from PySide6.QtGui import QDesktopServices, QPalette
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QListWidget,
    QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from dxf_translate import __version__
from dxf_translate.glossary import GlossaryError, save_terms
from dxf_translate.gui import texts
from dxf_translate.gui.worker import JobWorker
from dxf_translate.pipeline import JobResult

SECTIONS = {"phrase": "phrases", "note": "notes"}     # `part`/`excel` rows: fix the translation file


def is_translation_file(p: Path) -> bool:
    return p.suffix.lower() == ".xlsx" and not p.name.startswith("~$")


class MainWindow(QMainWindow):
    job_done = Signal()                 # emitted on the UI thread after a job ends (ok or error)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(texts.WINDOW_TITLE)
        self.resize(960, 760)
        self.last_paths: list[Path] = []
        self.translations: Path | None = None   # kept until the window closes (reused on rerun)
        self.result: JobResult | None = None
        self.worker: JobWorker | None = None
        self._thread: QThread | None = None
        self._gc_paused = False
        self._build()
        self.setAcceptDrops(True)
        self._refresh_controls()

    # ---- layout -------------------------------------------------------------------
    def _build(self) -> None:
        root = QWidget()
        lay = QVBoxLayout(root)

        self.drop_label = QLabel(texts.DROP_HINT)
        self.drop_label.setAlignment(Qt.AlignCenter)
        self.drop_label.setFrameShape(QFrame.StyledPanel)
        self.drop_label.setMinimumHeight(110)
        self.drop_label.setStyleSheet(
            "QLabel { border: 2px dashed palette(mid); border-radius: 8px; font-size: 15px; }")
        lay.addWidget(self.drop_label)

        row = QHBoxLayout()
        self.choose_btn = QPushButton(texts.CHOOSE_FILES)
        self.choose_btn.clicked.connect(self._choose_files)
        self.folder_btn = QPushButton(texts.CHOOSE_FOLDER)
        self.folder_btn.clicked.connect(self._choose_folder)
        self.version_label = QLabel(texts.VERSION.format(version=__version__))
        self.version_label.setForegroundRole(QPalette.PlaceholderText)
        row.addWidget(self.choose_btn)
        row.addWidget(self.folder_btn)
        row.addStretch(1)
        row.addWidget(self.version_label)
        lay.addLayout(row)

        self.translations_box = QGroupBox(texts.TRANSLATIONS_TITLE)
        tl = QHBoxLayout(self.translations_box)
        self.translations_label = QLabel(texts.NO_TRANSLATIONS)
        self.translations_label.setWordWrap(True)
        self.translations_label.setMinimumHeight(40)
        self.translations_label.setStyleSheet(
            "QLabel { border: 2px dashed palette(mid); border-radius: 6px; padding: 4px 8px; }")
        self.choose_translations_btn = QPushButton(texts.CHOOSE_TRANSLATIONS)
        self.choose_translations_btn.clicked.connect(self._choose_translations)
        self.clear_translations_btn = QPushButton(texts.CLEAR_TRANSLATIONS)
        self.clear_translations_btn.setToolTip(texts.CLEAR_TRANSLATIONS_TIP)
        self.clear_translations_btn.setFixedWidth(32)
        self.clear_translations_btn.clicked.connect(lambda: self.set_translations(None))
        tl.addWidget(self.translations_label, 1)
        tl.addWidget(self.choose_translations_btn)
        tl.addWidget(self.clear_translations_btn)
        lay.addWidget(self.translations_box)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        lay.addWidget(self.progress)

        self.counts_label = QLabel("")
        self.counts_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        lay.addWidget(self.counts_label)

        self.excel_warning = QLabel(texts.NO_EXCEL)
        self.excel_warning.setWordWrap(True)
        self.excel_warning.setStyleSheet(
            "QLabel { background: #fff3cd; color: #664d03; border: 1px solid #e0c36c;"
            " border-radius: 4px; padding: 6px; }")
        self.excel_warning.hide()
        lay.addWidget(self.excel_warning)

        row = QHBoxLayout()
        self.en_list_label = QLabel("")
        self.open_en_list_btn = QPushButton(texts.OPEN_EN_LIST)
        self.open_en_list_btn.clicked.connect(self._open_en_list)
        row.addWidget(self.en_list_label)
        row.addWidget(self.open_en_list_btn)
        row.addStretch(1)
        self.en_list_label.hide()
        self.open_en_list_btn.hide()
        lay.addLayout(row)

        self.failures_box = QGroupBox(texts.FAILURES)
        fl = QVBoxLayout(self.failures_box)
        self.failures_list = QListWidget()
        self.failures_list.setMaximumHeight(90)
        fl.addWidget(self.failures_list)
        self.failures_box.hide()
        lay.addWidget(self.failures_box)

        self.overlaps_box = QGroupBox(texts.OVERLAPS)
        ol = QVBoxLayout(self.overlaps_box)
        self.overlap_hint = QLabel(texts.OVERLAP_HINT)
        self.overlap_hint.setStyleSheet("color: #b02a37; font-weight: bold;")
        self.overlaps_list = QListWidget()
        self.overlaps_list.setMaximumHeight(110)
        ol.addWidget(self.overlap_hint)
        ol.addWidget(self.overlaps_list)
        self.overlaps_box.hide()
        lay.addWidget(self.overlaps_box)

        self.missing_box = QGroupBox(texts.MISSING)
        ml = QVBoxLayout(self.missing_box)
        self.missing_table = QTableWidget(0, len(texts.MISSING_HEADERS))
        self.missing_table.setHorizontalHeaderLabels(texts.MISSING_HEADERS)
        hh = self.missing_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.Interactive)
        hh.setSectionResizeMode(3, QHeaderView.Stretch)
        self.missing_table.verticalHeader().hide()
        self.save_btn = QPushButton(texts.SAVE_RERUN)
        self.save_btn.clicked.connect(self.save_and_rerun)
        ml.addWidget(self.missing_table)
        ml.addWidget(self.save_btn, alignment=Qt.AlignRight)
        self.missing_box.hide()
        lay.addWidget(self.missing_box, 3)

        row = QHBoxLayout()
        self.open_dir_btn = QPushButton(texts.OPEN_DIR)
        self.open_dir_btn.clicked.connect(self._open_dir)
        self.open_review_btn = QPushButton(texts.OPEN_REVIEW)
        self.open_review_btn.clicked.connect(self._open_review)
        row.addWidget(self.open_dir_btn)
        row.addWidget(self.open_review_btn)
        row.addStretch(1)
        lay.addLayout(row)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(120)
        lay.addWidget(self.log, 1)             # takes the free space when no table is shown

        self.setCentralWidget(root)

    # ---- drag & drop ----------------------------------------------------------------
    def dragEnterEvent(self, ev) -> None:
        if not self.busy and any(u.isLocalFile() for u in ev.mimeData().urls()):
            ev.acceptProposedAction()
        else:
            ev.ignore()

    def dragMoveEvent(self, ev) -> None:
        self.dragEnterEvent(ev)

    def dropEvent(self, ev) -> None:
        urls = ev.mimeData().urls()
        ev.acceptProposedAction()
        self.handle_urls(urls)

    def handle_urls(self, urls: list[QUrl]) -> None:
        self.handle_paths([Path(u.toLocalFile()) for u in urls if u.isLocalFile()])

    def handle_paths(self, paths: list[Path]) -> None:
        """A dropped / chosen `.xlsx` becomes the translation file; everything else is the DXF
        input. A drop of only a translation file just selects it (no job starts)."""
        xlsx = [p for p in paths if p.is_file() and is_translation_file(p)]
        rest = [p for p in paths if p not in xlsx]
        if len(xlsx) > 1:
            QMessageBox.warning(self, texts.INFO_TITLE, texts.SEVERAL_TRANSLATIONS)
            return
        if xlsx:
            self.set_translations(xlsx[0])
        if rest:
            self.start(rest)

    def set_translations(self, path: Path | None) -> None:
        if self.busy:
            return
        new = Path(path) if path else None
        if new != self.translations and self.result is not None:
            self.clear_result()            # the shown result belongs to the previous file
        self.translations = new
        if self.translations:
            self.translations_label.setText(self.translations.name)
            self.translations_label.setToolTip(str(self.translations))
            self.log.appendPlainText(texts.LOG_TRANSLATIONS.format(path=self.translations))
        else:
            self.translations_label.setText(texts.NO_TRANSLATIONS)
            self.translations_label.setToolTip("")
        self._refresh_controls()

    def _choose_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, texts.CHOOSE_FILES_TITLE, "", texts.FILE_FILTER)
        if files:
            self.handle_paths([Path(f) for f in files])

    def _choose_translations(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, texts.CHOOSE_TRANSLATIONS_TITLE, "",
                                           texts.TRANSLATIONS_FILTER)
        if f:
            self.set_translations(Path(f))

    def _choose_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, texts.CHOOSE_FOLDER_TITLE)
        if d:
            self.start([Path(d)])

    # ---- job ------------------------------------------------------------------------
    @property
    def busy(self) -> bool:
        return self._thread is not None

    def start(self, paths: list[Path]) -> None:
        if self.busy:
            return
        self.last_paths = [Path(p) for p in paths]
        self.log.appendPlainText(texts.LOG_START.format(paths=", ".join(map(str, self.last_paths))))
        self.progress.setRange(0, 0)              # indeterminate until the first sheet is done
        # The cyclic GC must never run on the worker thread: it could finalize Qt wrappers
        # there and crash in their C++ destructors. Collect now on the UI thread and pause
        # automatic collection until the job ends (re-enabled in _end_job, UI thread).
        gc.collect()
        self._gc_paused = gc.isenabled()
        gc.disable()
        self._thread = QThread(self)
        self.worker = JobWorker(self.last_paths, self.translations)
        self.worker.moveToThread(self._thread)
        self._thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self._refresh_controls()
        self._thread.start()

    def wait_idle(self) -> None:
        """Block until a running job's thread has stopped (used on close and in tests)."""
        self._end_job()

    def _end_job(self) -> None:
        """Stop the worker thread and release worker + thread on the UI thread, then resume GC.
        The worker is Python-owned: dropping the last reference here deletes it on this
        thread once its own thread has finished (no DeferredDelete to a dead event loop)."""
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
            self._thread.deleteLater()        # lives on the UI thread, whose loop runs it
            self._thread = None
            self.worker = None
        if self._gc_paused:
            self._gc_paused = False
            gc.enable()
            gc.collect()

    @Slot(int, int, str)
    def _on_progress(self, done: int, total: int, name: str) -> None:
        self.progress.setRange(0, total)
        self.progress.setValue(done)
        self.log.appendPlainText(texts.LOG_PROGRESS.format(done=done, total=total, name=name))

    @Slot(object)
    def _on_finished(self, res: JobResult) -> None:
        self._end_job()
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.show_result(res)
        self._refresh_controls()
        self.job_done.emit()

    @Slot(str)
    def _on_error(self, msg: str) -> None:
        self._end_job()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.log.appendPlainText(texts.LOG_ERROR.format(msg=msg))
        self._refresh_controls()
        hint = texts.explain(msg)
        shown = f"{hint}\n\n{texts.DETAILS.format(msg=msg)}" if hint else msg
        QMessageBox.critical(self, texts.ERROR_TITLE, shown)
        self.job_done.emit()

    def closeEvent(self, ev) -> None:
        self.wait_idle()
        super().closeEvent(ev)

    # ---- result panel -----------------------------------------------------------------
    def show_result(self, res: JobResult) -> None:
        self.result = res
        self.counts_label.setText(texts.COUNTS.format(
            ok=len(res.sheets), failed=len(res.failed), overlaps=len(res.overlaps)))
        self.excel_warning.setVisible("no_excel" in res.warnings)
        en_failed = any(w.startswith("en_list_failed:") for w in res.warnings)
        if res.en_list:
            self.en_list_label.setText(texts.EN_LIST.format(name=res.en_list.name))
            self.en_list_label.setToolTip(str(res.en_list))
        elif en_failed:
            self.en_list_label.setText(texts.EN_LIST_FAILED)
            self.en_list_label.setToolTip("")
        self.en_list_label.setVisible(bool(res.en_list) or en_failed)
        self.open_en_list_btn.setVisible(bool(res.en_list))

        self.failures_list.clear()
        for name, msg in res.failed:
            self.failures_list.addItem(f"{name}: {texts.explain(msg) or msg}")
            self.failures_list.item(self.failures_list.count() - 1).setToolTip(msg)
        self.failures_box.setVisible(bool(res.failed))

        self.overlaps_list.clear()
        for o in res.overlaps:
            self.overlaps_list.addItem(texts.OVERLAP_ITEM.format(
                file=o.file, text=o.text[:60], x=o.x_mm, y=o.y_mm, lines=o.lines))
        self.overlaps_box.setVisible(bool(res.overlaps))
        self.overlap_hint.setVisible(bool(res.overlaps))

        t = self.missing_table
        t.setRowCount(0)
        for m in res.missing:
            r = t.rowCount()
            t.insertRow(r)
            src = QTableWidgetItem(m.text)
            src.setData(Qt.UserRole, (m.text, m.kind))
            kind = QTableWidgetItem(texts.KINDS.get(m.kind, m.kind))
            shown_files = m.files or ([res.translations.path.name]
                                      if m.kind == "excel" and res.translations else [])
            files = QTableWidgetItem(", ".join(shown_files))
            for it in (src, kind, files):
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                it.setToolTip(it.text())
            if m.kind in SECTIONS:
                en = QTableWidgetItem("")
            else:
                if m.kind == "excel":
                    col, _, pn = m.hint.partition(" · ")
                    en = QTableWidgetItem(texts.EXCEL_HINT.format(col=col, pn=pn))
                else:
                    en = QTableWidgetItem(texts.PART_FIX_EXCEL)
                en.setFlags(Qt.ItemIsEnabled)
                en.setToolTip(en.text())
                en.setForeground(self.palette().color(QPalette.PlaceholderText))
            for c, it in enumerate((src, kind, files, en)):
                t.setItem(r, c, it)
        self.missing_box.setVisible(bool(res.missing))

        for s in res.sheets:
            for line in s.report:
                self.log.appendPlainText(line)
        for name, msg in res.failed:                 # technical text stays in the log
            self.log.appendPlainText(f"{name}: {msg}")
        for w in res.warnings:
            if w != "no_excel":
                self.log.appendPlainText(w)
                hint = texts.explain(w)
                if hint:
                    self.log.appendPlainText(f"   → {hint}")
        self.log.appendPlainText(texts.LOG_DONE.format(out=res.out_dir))
        self._refresh_controls()

    def clear_result(self) -> None:
        """Hide the result panel (counts, EN list, failures, overlaps, missing table)."""
        self.result = None
        self.counts_label.setText("")
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        for w in (self.excel_warning, self.en_list_label, self.open_en_list_btn,
                  self.failures_box, self.overlaps_box, self.missing_box):
            w.hide()
        self.failures_list.clear()
        self.overlaps_list.clear()
        self.missing_table.setRowCount(0)
        self._refresh_controls()

    def _refresh_controls(self) -> None:
        idle = not self.busy
        self.setAcceptDrops(idle)
        self.drop_label.setText(texts.DROP_HINT if idle else texts.DROP_BUSY)
        self.choose_btn.setEnabled(idle)
        self.folder_btn.setEnabled(idle)
        self.choose_translations_btn.setEnabled(idle)
        self.clear_translations_btn.setEnabled(idle and self.translations is not None)
        res = self.result
        self.open_en_list_btn.setEnabled(idle and bool(res and res.en_list and res.en_list.is_file()))
        editable = bool(res and any(m.kind in SECTIONS for m in res.missing))
        self.save_btn.setEnabled(idle and editable and bool(self.last_paths))
        self.open_dir_btn.setEnabled(idle and bool(res) and res.out_dir.is_dir())
        self.open_review_btn.setEnabled(idle and bool(res and res.review and res.review.is_file()))

    # ---- actions ------------------------------------------------------------------------
    def collect_terms(self) -> dict[str, dict[str, str]]:
        terms: dict[str, dict[str, str]] = {}
        t = self.missing_table
        for r in range(t.rowCount()):
            text, kind = t.item(r, 0).data(Qt.UserRole)
            en = t.item(r, 3).text().strip()
            if kind in SECTIONS and en:
                terms.setdefault(SECTIONS[kind], {})[text] = en
        return terms

    def save_and_rerun(self) -> None:
        if self.busy or self.result is None:
            return
        terms = self.collect_terms()
        if not terms:
            QMessageBox.information(self, texts.INFO_TITLE, texts.NOTHING_TO_SAVE)
            return
        order_dir = self.result.order_dir or self.result.out_dir.parent
        path = Path(order_dir) / "glossary.yaml"
        try:
            save_terms(path, terms)
        except (GlossaryError, OSError) as exc:
            QMessageBox.critical(self, texts.ERROR_TITLE, str(exc))
            return
        except Exception as exc:              # noqa: BLE001 - never leave the user with nothing
            QMessageBox.critical(self, texts.ERROR_TITLE, f"{type(exc).__name__}: {exc}")
            return
        n = sum(len(v) for v in terms.values())
        self.log.appendPlainText(texts.LOG_SAVED.format(n=n, path=path))
        self.start(self.last_paths)

    def _open(self, path: Path) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _open_dir(self) -> None:
        if self.result:
            self._open(self.result.out_dir)

    def _open_en_list(self) -> None:
        if self.result and self.result.en_list:
            self._open(self.result.en_list)

    def _open_review(self) -> None:
        if self.result and self.result.review:
            self._open(self.result.review)
