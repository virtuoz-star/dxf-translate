"""GUI message mapping (plain strings, no Qt needed)."""
from dxf_translate.gui import texts


def test_explain_known_failures():
    assert texts.explain("PermissionError: [Errno 13] Permission denied: 'a_EN.pdf'") == texts.FILE_IN_USE
    assert texts.explain("/o/t.xlsx: cannot read translation file: BadZipFile: x") == texts.TRANSLATIONS_UNREADABLE
    assert texts.explain("/o/old.xlsx: not a translation file: missing column header(s) "
                         "['Name'] (need ...)") == texts.NOT_TRANSLATION_FILE
    assert texts.explain("en_list_failed: PermissionError: [Errno 13] x") == texts.EN_LIST_FAILED
    assert texts.explain("en_list_formula: formula in F4 (=G3) refers to dropped column "
                         "Матеріал") == texts.EN_LIST_FORMULA
    assert texts.explain("review failed: RuntimeError: x") == texts.REVIEW_FAILED
    assert texts.explain("output name collision: a and b") == texts.NAME_COLLISION
    assert texts.explain("UnsupportedSheet: Unsupported sheet size 300x297") == texts.UNSUPPORTED_SHEET
    assert texts.explain("x.dxf: !! title block: Part No. not found") == texts.TITLE_BLOCK
    assert texts.explain("something else") is None
