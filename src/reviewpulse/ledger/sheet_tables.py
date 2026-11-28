"""The general sheet table reader (`schedules/`) as a producer of the ledger.

Each cell the reader typed becomes a ledger `Candidate`: the drawn element the row was bound to by its tag is the entity, the
cell text and the table are the source, the unit is the one the reader found. Producers of one family count once, so the table
reader is the family `sheet_table`; when the fact graph's own schedule family agrees, trust rises, and when it disagrees the
ledger reports a conflict with both sources.

Only the meanings listed in `FACT_OF_MEANING` are offered by default. A width read from a schedule is not offered for the fact
`width_m`, which the fact graph measures from geometry: a schedule width and a drawn width differ by the frame, and that is not a
conflict worth refusing a verdict for. A caller can widen `facts` when it knows better.
"""

from __future__ import annotations

from ..schedules import bind_to_elements, read_sheet_tables
from ..schedules.model import Candidate as TableCandidate
from .candidate import Candidate
from .request import FactRequest

# meaning of a table column -> (fact name of the fact graph, unit of the fact)
FACT_OF_MEANING = {"fire_rating": ("fire_rating_min", "min")}
TABLE_SCORE = 0.85          # a stated cell with a typed header: above the ledger's acceptance threshold on its own


class SheetTableProducer:
    name, family = "sheet_table", "sheet_table"

    def __init__(self, candidates: list[TableCandidate], *, facts: dict[str, tuple[str, str]] | None = None):
        self.facts = facts if facts is not None else FACT_OF_MEANING
        self.candidates = [c for c in candidates if c.element_id and c.meaning in self.facts]

    def _fits(self, c: TableCandidate, request: FactRequest) -> bool:
        fact, _unit = self.facts[c.meaning]
        return fact == request.fact and (request.entity is None or c.element_id == request.entity)

    def holds(self, request: FactRequest) -> float:
        return TABLE_SCORE if any(self._fits(c, request) for c in self.candidates) else 0.0

    def answer(self, request: FactRequest) -> list[Candidate]:
        out = []
        for c in self.candidates:
            if not self._fits(c, request) or not isinstance(c.value, int | float) or isinstance(c.value, bool):
                continue
            fact, unit = self.facts[c.meaning]
            out.append(Candidate(
                entity=c.element_id, fact=fact, value=float(c.value), unit=c.unit or unit, kind="stated",
                source=f"{c.sheet} {c.table} row {c.row} cell '{c.cell_text}' (column '{c.header_text}')", sheet=c.sheet,
                words=c.cell_text, producer=self.name, family=self.family, score=TABLE_SCORE * min(1.0, max(c.confidence, 0.0))))
        return out


def sheet_table_producer(sheet, elements, **kw) -> SheetTableProducer | None:
    """Read the tables of a sheet and bind their rows to the drawn elements by tag; None when there is nothing to offer."""
    tables = read_sheet_tables(sheet)
    cands = [c for t in tables for c in t.candidates]
    bind_to_elements(cands, elements)
    producer = SheetTableProducer(cands, **kw)
    return producer if producer.candidates else None
