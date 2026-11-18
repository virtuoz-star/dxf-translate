"""All user-facing strings of the desktop app (Ukrainian)."""

APP_NAME = "DXF Translate"
WINDOW_TITLE = "DXF Translate — переклад креслень UA → EN"
VERSION = "v{version}"

DROP_HINT = "Перетягніть сюди файли DXF / Excel або папку замовлення"
DROP_BUSY = "Виконується переклад…"
CHOOSE_FILES = "Обрати файли…"
CHOOSE_FOLDER = "Обрати папку…"
CHOOSE_FILES_TITLE = "Оберіть файли DXF та Excel"
CHOOSE_FOLDER_TITLE = "Оберіть папку замовлення"
FILE_FILTER = "Креслення та Excel (*.dxf *.DXF *.xlsx *.XLSX);;Усі файли (*)"

LOG_START = "Початок: {paths}"
LOG_PROGRESS = "Оброблено {done}/{total}: {name}"
LOG_DONE = "Готово. Результати: {out}"
LOG_ERROR = "Помилка: {msg}"
LOG_SAVED = "Збережено перекладів: {n} → {path}"

COUNTS = "Перекладено: {ok}   ·   Помилки: {failed}   ·   Накладання: {overlaps}"
NO_EXCEL = ("Увага: файли Excel (виробничі списки UA та EN) не знайдено — "
            "назви та матеріали перекладаються лише за глосарієм.")
FAILURES = "Помилки"
OVERLAPS = "Накладання тексту на лінії"
OVERLAP_ITEM = "{file}: «{text}» ({x:.0f}, {y:.0f} мм) — перетинає ліній: {lines}"
OVERLAP_HINT = "Виправте в Claude Code або вручну"
MISSING = "Відсутні переклади"
MISSING_HEADERS = ["Український текст", "Тип", "Файли", "English"]
KINDS = {"phrase": "фраза", "note": "примітка", "part": "деталь (Excel)"}
PART_FIX_EXCEL = "Виправте у файлі Excel"

SAVE_RERUN = "Зберегти та перезапустити"
OPEN_DIR = "Відкрити папку з результатами"
OPEN_REVIEW = "Відкрити сторінку перевірки"

ERROR_TITLE = "Помилка"
INFO_TITLE = "Інформація"
NO_DXF = "Не знайдено жодного файлу DXF."
NOTHING_TO_SAVE = "Введіть переклад англійською хоча б в одну клітинку стовпця «English»."

# per-file failures / errors: technical text stays in the log, the user sees this
FILE_IN_USE = ("Файл відкритий в іншій програмі (наприклад, PDF в Acrobat) — "
               "закрийте його та перезапустіть")
EXCEL_AMBIGUOUS = ("Знайдено кілька файлів Excel: потрібен рівно один український та один "
                   "англійський виробничий список. Залиште лише їх і перезапустіть")
EXCEL_UNREADABLE = "Не вдалося прочитати файл Excel — перевірте, що він не пошкоджений і не відкритий"
NAME_COLLISION = ("Кілька креслень з однаковою назвою в різних папках — результати перезаписали б "
                  "одне одного. Перейменуйте одне з них або перекладіть папки окремо")
UNSUPPORTED_SHEET = "Непідтримуваний формат аркуша (підтримуються лише A3 та A4)"
BROKEN_DXF = "Файл DXF пошкоджений або не є кресленням SolidWorks"
REVIEW_FAILED = "Не вдалося створити сторінку перевірки (переклад виконано)"
TITLE_BLOCK = "Не знайдено дані в основному написі (Part No. / назва / матеріал) — перевірте креслення"
GLOSSARY_BAD = "Помилка у файлі glossary.yaml"
DETAILS = "Подробиці: {msg}"

_EXPLAIN = (
    (("PermissionError", "Permission denied", "WinError 32", "being used by another process"),
     FILE_IN_USE),
    (("ambiguous Excel",), EXCEL_AMBIGUOUS),
    (("cannot read Excel",), EXCEL_UNREADABLE),
    (("output name collision",), NAME_COLLISION),
    (("Unsupported sheet size", "UnsupportedSheet"), UNSUPPORTED_SHEET),
    (("DXFStructureError", "DXFError", "Not a DXF file"), BROKEN_DXF),
    (("review failed",), REVIEW_FAILED),
    (("!! title block:",), TITLE_BLOCK),
    (("glossary.yaml",), GLOSSARY_BAD),
)


def explain(msg: str) -> str | None:
    """Ukrainian explanation of a known technical failure message, else None."""
    for needles, text in _EXPLAIN:
        if any(n in msg for n in needles):
            return text
    return None
