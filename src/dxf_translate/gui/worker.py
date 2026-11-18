"""Runs `run_job` off the UI thread and reports back through Qt signals."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from dxf_translate.glossary import GlossaryError
from dxf_translate.gui import texts
from dxf_translate.pipeline import run_job


class JobWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(object)          # JobResult
    error = Signal(str)                # user-facing message, never a traceback

    def __init__(self, paths: list[Path]) -> None:
        super().__init__()
        self.paths = list(paths)

    @Slot()
    def run(self) -> None:
        try:
            res = run_job(self.paths, progress=lambda d, t, n: self.progress.emit(d, t, n))
        except GlossaryError as exc:
            self.error.emit(str(exc))
        except ValueError as exc:
            self.error.emit(texts.NO_DXF if str(exc) == "no DXF files" else str(exc))
        except Exception as exc:          # noqa: BLE001 - surface anything else as a message
            self.error.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.finished.emit(res)
