# PyInstaller spec: one-file, windowed `dxf-translate` desktop app.
#   uv run pyinstaller packaging/dxf-translate.spec   ->  dist/dxf-translate(.exe)
#   dist/dxf-translate --selftest                     ->  exit 0 when the bundle works
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
PKG = ROOT / "src" / "dxf_translate"

# Package-relative paths, so fonts.FONT_DIR (Path(__file__).parent / "fonts") and
# importlib.resources("dxf_translate/data/glossary.yaml") resolve under sys._MEIPASS.
datas = [(str(p), "dxf_translate/fonts") for p in sorted((PKG / "fonts").iterdir()) if p.is_file()]
datas += [(str(PKG / "data" / "glossary.yaml"), "dxf_translate/data")]

hiddenimports = (
    collect_submodules("ezdxf.acc")             # optional C accelerators, imported conditionally
    + collect_submodules("ezdxf.addons.drawing", filter=lambda m: not any(
        x in m for x in ("qtviewer", "pyqt", "matplotlib")))
    + ["PIL.Image", "PIL.ImageDraw", "pymupdf", "fitz", "openpyxl", "yaml"]
)

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    datas=datas,
    hiddenimports=hiddenimports,
    runtime_hooks=[str(ROOT / "packaging" / "rthook_ezdxf_cache.py")],
    excludes=["tkinter", "matplotlib", "PyQt5", "PyQt6", "pytest", "IPython"],
    noarchive=False,
)
# pymupdf ships ~40 MB of ONNX layout models (pymupdf4llm); PDF writing never uses them.
a.datas = [d for d in a.datas if not d[0].replace("\\", "/").startswith("pymupdf/layout/resources/onnx/")]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="dxf-translate",
    console=False,                              # windowed: no console window on Windows
    upx=False,
    strip=False,
    debug=False,
)
