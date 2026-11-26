"""Plain data of the table reader. No dependency on a ledger: a ledger can take a Candidate field by field."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Candidate:
    """One value read from one cell of a table of a sheet, with where it came from."""
    value: float | str | None             # the number as written (in `unit`), or the text of a text column
    unit: str | None                      # a symbol of interpreter/units.yaml ("mm", "in", "min", "m2"), None when none is known
    meaning: str                          # what the column means: width, height, fire_rating, area, finish_floor, ...
    entity_kind: str                      # doors, windows, rooms, finishes, fixtures, walls, other
    entity_tag: str | None                # the key of the row: "D12", "W3", "101" (tag_key form)
    sheet: str
    table: str                            # id of the table on the sheet: "<sheet>:T1"
    row: int                              # row of the table, from 0 under the header
    cell_text: str                        # the cell exactly as drawn
    col: int = -1
    header_text: str = ""
    unit_source: str = "none"             # header, cell, column, fire_parser, inferred (a guess from the size of the numbers) or none
    confidence: float = 1.0               # of the header meaning, lowered when the unit was guessed
    value_si: float | None = None         # the value in the coherent SI unit (metres, seconds, square metres) when the unit is known
    entity_tag_raw: str | None = None
    derived_from: str | None = None       # "size" when a width and a height were cut from one "3'-0\" x 6'-8\"" cell
    table_title: str = ""
    bbox: tuple[float, float, float, float] | None = None
    element_id: str | None = None         # the drawn element this row was bound to by its tag, when there is one

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Column:
    index: int
    header: str
    meaning: str | None
    score: float
    via: str                              # words, embedding, content or none
    dim: str
    unit: str | None = None
    unit_source: str = "none"
    x0: float = 0.0
    x1: float = 0.0


@dataclass
class TypedTable:
    id: str
    sheet: str
    kind: str
    kind_source: str                      # title, tag prefix, columns or none
    title: str
    method: str                           # unruled or ruled
    bbox: tuple[float, float, float, float]
    columns: list[Column]
    rows: list[list[str]]
    tags: list[str | None]
    candidates: list[Candidate] = field(default_factory=list)

    @property
    def n_typed(self) -> int:
        return sum(1 for c in self.columns if c.meaning)

    @property
    def n_with_unit(self) -> int:
        return sum(1 for c in self.columns if c.unit)
