"""The same requirements written in the different ways documents are really written, to measure how well the reader of a
document survives style. No annotation is needed: the requirements are known because we wrote them, and what a style must
not do is lose one, merge two, or cut a table from its header.

`render(items, style)` returns document text. `measure(items, style)` returns, for that style,
  recall      share of requirements whose sentence is wholly inside one clause
  merged      clauses that hold more than one requirement
  context     share of table-based requirements whose clause reaches its table header and the definitions
"""

from __future__ import annotations

from dataclasses import dataclass

from ..interpreter.context import assemble_context
from ..rules.clauses import split_text

STYLES = ("numbered", "legal", "codes", "prose", "bullets", "table", "french_articles", "mixed")


@dataclass(frozen=True)
class Req:
    text: str                 # one complete requirement sentence
    table_row: str | None = None   # when a table could carry it: "Room type | Minimum area" cells


ITEMS = [
    Req("Every corridor shall be at least 1.2 m wide."),
    Req("Every bedroom shall have a window."),
    Req("The travel distance to the nearest exit shall not exceed 30 m."),
    Req("Doors on an escape route shall open in the direction of escape."),
    Req("A bedroom shall have a floor area of at least 9 m2.", table_row="Bedroom | 9 m2"),
    Req("A living room shall have a floor area of at least 14 m2.", table_row="Living room | 14 m2"),
    Req("A kitchen shall have a floor area of at least 6 m2.", table_row="Kitchen | 6 m2"),
    Req("Stairs shall have a riser height of at most 190 mm."),
]
DEFINITION = 'In this document, "habitable room" means a bedroom, a living room or a kitchen.'


def render(items: list[Req], style: str, definition: str = DEFINITION) -> str:
    plain = [r for r in items if not (style == "table" and r.table_row)]
    rows = [r for r in items if style == "table" and r.table_row]
    out: list[str] = []
    if style == "numbered":
        out += ["1 Definitions", definition, "", "2 Requirements"]
        out += [f"2.{i} {r.text}" for i, r in enumerate(items, 1)]
    elif style == "legal":
        out += ["PART I - DEFINITIONS", "", f'Rule 1. Meaning of terms\n(1) {definition}', "", "PART II - REQUIREMENTS"]
        for i, r in enumerate(items, 2):
            out += [f"Rule {i}. Requirement", f"(1) {r.text}"]
    elif style == "codes":
        out += [f"DEF-001 {definition}"] + [f"REQ-{i:03d} {r.text}" for i, r in enumerate(items, 1)]
    elif style == "prose":
        out += ["Design brief.", "", definition, ""]
        for k in range(0, len(items), 3):
            out += [" ".join(r.text for r in items[k:k + 3]), ""]
    elif style == "bullets":
        out += ["Requirements", "", definition, ""] + [f"- {r.text}" for r in items]
    elif style == "table":
        out += ["1 Definitions", definition, "", "2 Requirements"]
        out += [f"2.{i} {r.text}" for i, r in enumerate(plain, 1)]
        out += ["", "Table 1 | Room type | Minimum area"] + [f" | {r.table_row}" for r in rows]
    elif style == "french_articles":
        out += [f"Article {i} : {r.text}" for i, r in enumerate(items, 1)]
    elif style == "mixed":
        out += ["PART I", "", definition, "", "1. General", f"1.1 {items[0].text}", f"1.2 {items[1].text}", "", "Annex A",
                "The following also applies. " + " ".join(r.text for r in items[2:5]), "",
                f"- {items[5].text}", f"- {items[6].text}", f"({chr(97)}) {items[7].text}"]
    else:
        raise ValueError(style)
    return "\n".join(out) + "\n"


def measure(items: list[Req], style: str) -> dict:
    text = render(items, style)
    clauses = split_text(text)
    rows = [c for c in clauses if c.kind == "table_row"]

    def held(r: Req) -> bool:
        if any(r.text in c.text for c in clauses):
            return True
        return style == "table" and r.table_row is not None and any(r.table_row in c.text for c in rows)

    merged = sum(1 for c in clauses if sum(r.text in c.text for r in items) > 1)
    ctx_ok = 0
    for c in rows:
        reached = assemble_context("d", text, clauses, c.id).clauses
        ctx_ok += c.parent in {x.id for x in reached}           # a row reaches the header that names its columns
    return {"style": style, "requirements": len(items), "clauses": len(clauses),
            "recall": round(sum(held(r) for r in items) / len(items), 3), "merged": merged,
            "context": round(ctx_ok / len(rows), 3) if rows else None}
