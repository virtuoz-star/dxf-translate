"""Local launcher: `uv run main.py [PATH...]` opens the desktop app.

PySide6 lives in the optional `gui` extra, which a plain `uv run` does not install, so when it
is missing this re-runs itself through `uv run --extra gui` (first time: downloads PySide6).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    try:
        import PySide6  # noqa: F401
    except ImportError:
        if os.environ.get("DXF_TRANSLATE_REEXEC"):
            print("PySide6 is still missing after `uv run --extra gui`", file=sys.stderr)
            return 1
        env = {**os.environ, "DXF_TRANSLATE_REEXEC": "1"}
        cmd = ["uv", "run", "--project", str(ROOT), "--extra", "gui",
               "python", str(Path(__file__).resolve()), *sys.argv[1:]]
        return subprocess.call(cmd, env=env)
    from dxf_translate.gui.app import main as gui_main
    return gui_main(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
