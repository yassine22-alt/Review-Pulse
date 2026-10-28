"""The brief (programme): the rooms a project must contain, read from the client's own table.

A brief is a table with one row per room or room kind: a name, optionally a count and a required
area. It is read from CSV, XLSX, DOCX, PDF or Markdown; the header row is found by its vocabulary
(French and English), whatever the column order. Room names are typed with the same multilingual
lexicon as plan labels. Rows that are not rooms (totals, notes) are kept out.

The result is attached to the model as a schedule named ``programme`` and checked by the
``programme_rooms`` function (rule K-P1): every required room is on the plan, as many of each type
as asked, each at least its required area.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from ..annotate.text_classify import match_room, normalise
from ..schema import BuildingModel

HEADER = {
    "label": r"^(piece|pieces|local|locaux|espace|espaces|designation|libelle|nom|room|rooms|space|spaces|name|type)$",
    "count": r"^(nb|nbre|nombre|qte|quantite|qty|quantity|count|number)\.?$",
    "area": r"^(surface|surfaces|superficie|sup|surf|area|areas|m2|m²)\.?(\s*(utile|habitable|mini|minimum|min|"
            r"required|requise|cible|target|net))?(\s*\((m2|m²)\))?$",
}
TOTAL = r"^(total|sous total|sous-total|subtotal|sum|somme)\b"


def _cell(v) -> str:
    return "" if v is None else str(v).strip()


def _num(s: str) -> float | None:
    m = re.search(r"\d+(?:[.,]\d+)?", s.replace(" ", "").replace(" ", ""))
    return float(m.group(0).replace(",", ".")) if m else None


def _tables(path: Path) -> list[list[list[str]]]:
    """Every table of the document as rows of cell strings."""
    suf = path.suffix.lower()
    if suf == ".csv":
        text = path.read_text(encoding="utf-8-sig")
        dialect = csv.Sniffer().sniff(text.splitlines()[0], delimiters=",;\t")
        return [[[_cell(c) for c in row] for row in csv.reader(text.splitlines(), dialect)]]
    if suf in (".xlsx", ".xlsm"):
        import openpyxl

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        return [[[_cell(c) for c in row] for row in ws.iter_rows(values_only=True)] for ws in wb.worksheets]
    if suf == ".docx":
        import docx

        return [[[_cell(c.text) for c in row.cells] for row in t.rows] for t in docx.Document(str(path)).tables]
    if suf == ".pdf":
        import pymupdf

        out = []
        with pymupdf.open(path) as doc:
            for page in doc:
                out += [[[_cell(c) for c in row] for row in t.extract()] for t in page.find_tables().tables]
        return out
    if suf in (".md", ".txt"):
        rows = [[_cell(c) for c in ln.strip().strip("|").split("|")]
                for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip().startswith("|")]
        return [[r for r in rows if not all(re.fullmatch(r":?-{2,}:?", c) for c in r if c)]]
    raise ValueError(f"unsupported brief format {suf!r}: use CSV, XLSX, DOCX, PDF or Markdown")


def _header(row: list[str]) -> dict[str, int]:
    cols = {}
    for i, c in enumerate(row):
        t = normalise(c)
        for field, pat in HEADER.items():
            if field not in cols and re.match(pat, t):
                cols[field] = i
                break
    return cols if "label" in cols and len(cols) >= 2 else {}


def rows_from_table(table: list[list[str]]) -> list[dict]:
    for h, row in enumerate(table):
        cols = _header(row)
        if not cols:
            continue
        out = []
        for r in table[h + 1:]:
            label = r[cols["label"]] if cols["label"] < len(r) else ""
            if not label or re.match(TOTAL, normalise(label)):
                continue
            rtype = match_room(label)
            if rtype is None:
                continue                      # notes, headings, non-room lines
            count = _num(r[cols["count"]]) if "count" in cols and cols["count"] < len(r) else None
            area = _num(r[cols["area"]]) if "area" in cols and cols["area"] < len(r) else None
            out.append({"label": label, "type": rtype, "count": int(count) if count else 1, "area_m2": area})
        return out
    return []


def read_programme(path: str | Path) -> list[dict]:
    """Rows ``{label, type, count, area_m2}`` from the first table of the document that has a room
    column and a count or area column."""
    for table in _tables(Path(path)):
        rows = rows_from_table(table)
        if rows:
            return rows
    raise ValueError(f"{path}: no table with a room column and a count or area column")


def attach_programme(model: BuildingModel, path: str | Path) -> BuildingModel:
    model.schedules = [s for s in model.schedules if s.get("name") != "programme"]
    model.schedules.append({"name": "programme", "source": str(path), "rows": read_programme(path)})
    return model
