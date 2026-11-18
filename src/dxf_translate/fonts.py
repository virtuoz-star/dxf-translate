"""Bundled fonts: one font for both text measuring and PDF rendering."""
from __future__ import annotations

from pathlib import Path

from ezdxf.fonts import fonts as _ezfonts

FONT_DIR: Path = Path(__file__).parent / "fonts"
FONT_NAME = "OpenGostTypeA-Regular.ttf"

_ready = False


def setup() -> str:
    """Point ezdxf's font manager at FONT_DIR (once); return the font name to use."""
    global _ready
    if not _ready:
        _ezfonts.font_manager.build([str(FONT_DIR)])
        _ready = True
    return FONT_NAME


def text_width(text: str, height: float) -> float:
    setup()
    return _ezfonts.make_font(FONT_NAME, cap_height=height).text_width(text)
