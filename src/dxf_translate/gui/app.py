"""Entry point `dxf-translate-gui [PATH...]` (paths given on the command line start a job).

`--selftest` builds the window without showing it, translates a generated sheet in a temp
dir and exits 0/1 (CI uses it to prove the frozen exe works, Qt plugins included).
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from dxf_translate import _selftest
from dxf_translate.gui import texts
from dxf_translate.gui.window import MainWindow


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName(texts.APP_NAME)
    w = MainWindow()
    if "--selftest" in argv[1:]:
        w.deleteLater()
        return _selftest.main()
    w.show()
    paths = [Path(a) for a in argv[1:]]
    if paths:
        w.start(paths)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
