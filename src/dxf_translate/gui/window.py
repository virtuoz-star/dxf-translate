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

SECTIONS = {"phrase": "phrases", "note": "notes"}     # `part` rows are fixed in Excel


class MainWindow(QMainWindow):
    job_done = Signal()                 # emitted on the UI thread after a job ends (ok or error)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(texts.WINDOW_TITLE)
        self.resize(960, 760)
        self.last_paths: list[Path] = []
        self.result: JobResult | None = None
        self.worker: JobWorker | None = None
        self._thread: QThread | None = None
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
        paths = [Path(u.toLocalFile()) for u in urls if u.isLocalFile()]
        if paths:
            self.start(paths)

    def _choose_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, texts.CHOOSE_FILES_TITLE, "", texts.FILE_FILTER)
        if files:
            self.start([Path(f) for f in files])

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
        # Collect pending cyclic garbage here, on the UI thread: if the collector ran inside
        # the worker it could finalize stale Qt wrappers there and crash in their destructors.
        gc.collect()
        self._thread = QThread(self)
        self.worker = JobWorker(self.last_paths)
        self.worker.moveToThread(self._thread)
        self._thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self._refresh_controls()
        self._thread.start()

    def wait_idle(self) -> None:
        """Block until a running job's thread has stopped (used on close and in tests)."""
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()

    def _stop_thread(self) -> None:
        if self._thread is None:
            return
        self._thread.quit()
        self._thread.wait()
        self.worker.deleteLater()
        self._thread.deleteLater()
        self._thread = None

    @Slot(int, int, str)
    def _on_progress(self, done: int, total: int, name: str) -> None:
        self.progress.setRange(0, total)
        self.progress.setValue(done)
        self.log.appendPlainText(texts.LOG_PROGRESS.format(done=done, total=total, name=name))

    @Slot(object)
    def _on_finished(self, res: JobResult) -> None:
        self._stop_thread()
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.show_result(res)
        self._refresh_controls()
        self.job_done.emit()

    @Slot(str)
    def _on_error(self, msg: str) -> None:
        self._stop_thread()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.log.appendPlainText(texts.LOG_ERROR.format(msg=msg))
        self._refresh_controls()
        QMessageBox.critical(self, texts.ERROR_TITLE, msg)
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

        self.failures_list.clear()
        for name, msg in res.failed:
            self.failures_list.addItem(f"{name}: {msg}")
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
            files = QTableWidgetItem(", ".join(m.files))
            for it in (src, kind, files):
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                it.setToolTip(it.text())
            if m.kind in SECTIONS:
                en = QTableWidgetItem("")
            else:
                en = QTableWidgetItem(texts.PART_FIX_EXCEL)
                en.setFlags(Qt.ItemIsEnabled)
                en.setForeground(self.palette().color(QPalette.PlaceholderText))
            for c, it in enumerate((src, kind, files, en)):
                t.setItem(r, c, it)
        self.missing_box.setVisible(bool(res.missing))

        for s in res.sheets:
            for line in s.report:
                self.log.appendPlainText(line)
        for w in res.warnings:
            if w != "no_excel":
                self.log.appendPlainText(w)
        self.log.appendPlainText(texts.LOG_DONE.format(out=res.out_dir))
        self._refresh_controls()

    def _refresh_controls(self) -> None:
        idle = not self.busy
        self.setAcceptDrops(idle)
        self.drop_label.setText(texts.DROP_HINT if idle else texts.DROP_BUSY)
        self.choose_btn.setEnabled(idle)
        self.folder_btn.setEnabled(idle)
        res = self.result
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
        path = Path(self.result.order_dir) / "glossary.yaml"
        try:
            save_terms(path, terms)
        except (GlossaryError, OSError) as exc:
            QMessageBox.critical(self, texts.ERROR_TITLE, str(exc))
            return
        n = sum(len(v) for v in terms.values())
        self.log.appendPlainText(texts.LOG_SAVED.format(n=n, path=path))
        self.start(self.last_paths)

    def _open(self, path: Path) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _open_dir(self) -> None:
        if self.result:
            self._open(self.result.out_dir)

    def _open_review(self) -> None:
        if self.result and self.result.review:
            self._open(self.result.review)
