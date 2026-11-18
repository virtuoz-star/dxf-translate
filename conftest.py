"""pytest-qt aborts the whole run when no Qt binding is installed, so its entry point is
disabled in pyproject (`-p no:pytest-qt`) and it is loaded here only with the `gui` extra."""
import importlib.util

if all(importlib.util.find_spec(m) is not None for m in ("PySide6", "pytestqt")):
    pytest_plugins = ["pytestqt.plugin"]
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")   # GUI tests never need a display
