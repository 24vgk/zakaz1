
import csv
import io
from io import StringIO, BytesIO
from typing import Iterable, Iterator, Dict, Any
import datetime as dt

try:
    from openpyxl import load_workbook
except Exception:
    load_workbook = None

def detect_delimiter(sample: str) -> str:
    return ";" if ";" in sample and sample.count(";") >= sample.count(",") else ","

def _parse_due_date(value: str | None):
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    # формат YYYY-MM-DD
    return dt.datetime.strptime(value, "%Y-%m-%d").date()


def _to_date(value):
    if not value:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    s = str(value).strip()
    if not s:
        return None
    # пробуем YYYY-MM-DD
    try:
        return dt.datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None

def parse_problems_csv(data: bytes) -> Iterator[dict]:
    """
    Ожидаемый CSV-хедер:
    list_code,number,title,assignee,due_date
    """
    text = data.decode("utf-8-sig")
    f = io.StringIO(text)
    reader = csv.DictReader(f)
    for row in reader:
        if not row.get("list_code") or not row.get("number"):
            continue
        list_code = row["list_code"].strip()
        number = int(row["number"])
        title = (row.get("title") or "").strip()
        assignee_raw = (row.get("assignee") or "").strip()
        assignee = int(assignee_raw) if assignee_raw else None
        due_date = _parse_due_date(row.get("due_date"))

        yield {
            "list_code": list_code,
            "number": number,
            "title": title,
            "assignee": assignee,
            "due_date": due_date,
        }


def parse_problems_xlsx(data: bytes) -> Iterator[dict]:
    """
    Ожидаемый формат файла (твоя таблица):
    id | title | assignee | due_date

    Где:
      id        – номер проблемы (int, может быть 101, 102 и т.п.)
      title     – текст описания
      assignee  – Telegram ID исполнителя (int)
      due_date  – дата (Excel-дата или текст YYYY-MM-DD)

    Возвращает dict'ы:
      {
        "number": int,
        "title": str,
        "assignee": int | None,
        "due_date": date | None,
      }
    """
    buf = io.BytesIO(data)
    wb = load_workbook(buf, data_only=True)
    ws = wb.active

    # читаем шапку
    header = [str(c.value).strip() if c.value is not None else "" for c in ws[1]]

    def col_idx(name: str) -> int:
        try:
            return header.index(name)
        except ValueError:
            raise ValueError(f"В XLSX не найдена колонка '{name}'")

    idx_id = col_idx("id")
    idx_title = col_idx("title")
    idx_assignee = col_idx("assignee")
    idx_due = col_idx("due_date")

    for row in ws.iter_rows(min_row=2):
        id_cell = row[idx_id].value
        title_cell = row[idx_title].value
        assignee_cell = row[idx_assignee].value
        due_cell = row[idx_due].value

        if id_cell is None and title_cell is None:
            continue

        try:
            number = int(id_cell)
        except (TypeError, ValueError):
            # пропускаем строки без корректного id
            continue

        title = str(title_cell).strip() if title_cell is not None else ""

        assignee = None
        if assignee_cell is not None and str(assignee_cell).strip():
            try:
                assignee = int(str(assignee_cell).strip())
            except ValueError:
                assignee = None

        due_date = _to_date(due_cell)

        yield {
            "number": number,
            "title": title,
            "assignee": assignee,
            "due_date": due_date,
        }
