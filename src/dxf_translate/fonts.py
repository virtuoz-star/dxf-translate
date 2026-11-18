"""Bundled fonts: one font for both text measuring and PDF rendering."""
from __future__ import annotations

from pathlib import Path

from ezdxf.fonts import fonts as _ezfonts
from ezdxf.fonts.font_manager import DEFAULT_FONTS

FONT_DIR: Path = Path(__file__).parent / "fonts"
FONT_NAME = "OpenGostTypeA-Regular.ttf"

_ready = False


def setup() -> str:
    """Restrict ezdxf's font manager to FONT_DIR (once); return the font name to use.

    The manager is cleared first: ezdxf pre-loads the system font cache at import, and a
    same-named or fallback system font must never be used for measuring or rendering,
    so results are identical on every machine (dev box, CI, frozen Windows exe).
    """
    global _ready
    if not _ready:
        fm = _ezfonts.font_manager
        fm.clear()
        fm.build([str(FONT_DIR)], support_dirs=False)
        # ezdxf's fallback is the first of its DEFAULT_FONTS found in the cache; alias
        # the first one to the bundled font so unknown font names resolve to it too.
        fm.add_synonyms({FONT_NAME: DEFAULT_FONTS[0]},
                        reverse=False)
        _ready = True
    return FONT_NAME


def text_width(text: str, height: float) -> float:
    setup()
    return _ezfonts.make_font(FONT_NAME, cap_height=height).text_width(text)
