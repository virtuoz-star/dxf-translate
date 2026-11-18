"""Re-export: the synthetic sheet lives in the package so `--selftest` can use it."""
from dxf_translate._selftest import make_sheet

__all__ = ["make_sheet"]
