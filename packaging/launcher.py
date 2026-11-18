"""Frozen-exe entry script (PyInstaller needs a file, not a `module:function`)."""
import sys

from dxf_translate.gui.app import main

sys.exit(main())
