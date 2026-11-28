"""R12b - sheet tables, any columns (step 3 of docs/PLAN_general_reviewpulse.md).

  tables = read_pdf_tables("set.pdf")            every table of every page, each column typed by the meaning of its header
  tables = read_sheet_tables(sheet)              the same from a Sheet (PDF or DXF text layer)
  cands = [c for t in tables for c in t.candidates]     typed Candidates: value, unit, entity tag, sheet, table, row, cell text
  bind_to_elements(cands, model.elements)        rows bind to drawn elements by tag
  door_fire_rows(tables)                          the door fire rating of the door schedule, as a special case
"""

from .binding import bind_to_elements, bind_to_tags
from .door_fire import door_fire_candidates, door_fire_rows
from .model import Candidate, Column, TypedTable
from .reader import (
    read_page_tables,
    read_pdf_tables,
    read_sheet_tables,
    read_tables,
    words_from_page,
    words_from_sheet,
)
from .vocab import canonical_unit, header_unit, match_header

__all__ = ["Candidate", "Column", "TypedTable", "bind_to_elements", "bind_to_tags", "canonical_unit", "door_fire_candidates",
           "door_fire_rows", "header_unit", "match_header", "read_page_tables", "read_pdf_tables", "read_sheet_tables",
           "read_tables", "words_from_page", "words_from_sheet"]
