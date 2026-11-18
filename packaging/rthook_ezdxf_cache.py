"""PyInstaller runtime hook: runs before any app import in the frozen exe.

At import, ezdxf loads (or builds by scanning every system font folder, then writes) a font
cache under $XDG_CACHE_HOME/ezdxf or ~/.cache/ezdxf. The app measures and renders with its
bundled fonts only (dxf_translate.fonts.setup clears that cache anyway), so point ezdxf at a
pre-seeded, empty cache inside the bundle's temp dir: no system-font scan, no writes into the
user's profile, nothing that can fail on a locked-down machine.
"""
import json
import os
import sys
import tempfile


def _seed() -> None:
    base = getattr(sys, "_MEIPASS", None) or tempfile.mkdtemp(prefix="dxf-translate-")
    home = os.path.join(base, "_ezdxf_cache")
    try:
        os.makedirs(os.path.join(home, "ezdxf"), exist_ok=True)
        with open(os.path.join(home, "ezdxf", "font_manager_cache.json"), "w") as f:
            json.dump({"version": 2, "font-faces": []}, f)  # ezdxf CURRENT_CACHE_VERSION
    except OSError:
        return                       # ezdxf falls back to its own (logged, non-fatal) path
    os.environ["XDG_CACHE_HOME"] = home


_seed()
