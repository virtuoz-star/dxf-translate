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
