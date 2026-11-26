"""Audit of the clause splitter on real documents, without any label: what an independent reading of the text says about the clauses.

For every document in a folder it counts, with a sentence cutter that is NOT the splitter's own:

  coverage   obligation sentences (a modal word and either a figure or a verb of requirement) that lie inside some clause
  fragments  obligation sentences cut by a clause boundary (they start in one clause and end in another)
  bundles    clauses that hold two or more obligation sentences, or two limits with different units
  ragged     clauses that begin in the middle of a sentence (lower-case start that is not a list item)
  refs       references to another part of the document ("see 4.2", "Section 3", "Table 2") and how many resolve to a clause
  rowctx     table rows and whether each can reach its header

Usage: python scripts/split_audit.py [folder] [--json out.json]
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.environ.get("SPLIT_SRC") or str(Path(__file__).resolve().parents[1] / "src"))
from reviewpulse.rules.clauses import MODALS, split_cached  # noqa: E402

# the audit cuts sentences by itself (not with the splitter's code); a line that starts with a bullet glyph, symbol-font ones included,
# starts a sentence
GLYPHS = "•▪▫●○◦■□☐☑☒✓✔✗✘➢➤►▶‣⁃◆◇■-◿☐-☒-"
SENT = re.compile(rf"(?<=[.!?;:])\s+(?=[A-ZÀ-Ý0-9“\"(])|\n\s*\n|\n(?=\s*(?:[-*–{GLYPHS}]\s*|\(?[a-z0-9]{{1,3}}\)\s|\d+(?:\.\d+)*[.)]?\s))")
NUM = re.compile(r"\d+(?:[.,]\d+)?\s*(?:mm|cm|m|ft|feet|in|inch(?:es)?|sq\.?\s*ft|s\.f\.|m2|m²|%|°|degrees?|hours?|h|min|lbs?|kg)\b", re.I)
REF = re.compile(r"\b(?:see|refer(?:s|red)? to|in accordance with|according to|as (?:specified|required|described) in|"
                 r"voir|conformément à|gemäß|siehe|véase|ver)\s+(?:also\s+)?((?:Table|Tableau|Section|Sec\.|Article|Art\.|Chapter|Figure|§)?\s*"
                 r"[A-Z]?\d+(?:[.\-]\d+)*(?:\([a-z0-9]+\))*)", re.I)


def sentences(full: str):
    pos = 0
    for m in SENT.finditer(full):
        yield pos, m.start()
        pos = m.end()
    yield pos, len(full)


def obligation(text: str) -> bool:
    return bool(MODALS.search(text)) and (bool(NUM.search(text)) or len(text.split()) >= 6) and len(text) >= 20


def audit(path: Path, cache: Path) -> dict:
    full, clauses = split_cached(path, cache / path.stem)
    body = [c for c in clauses if c.kind != "heading"]
    sents = [(a, b) for a, b in sentences(full) if obligation(full[a:b])]
    covered = fragments = in_tables = 0
    for a, b in sents:
        owners = [c for c in body if c.start < b and c.end > a]
        inside = [c for c in owners if c.start <= a + 3 and c.end >= b - 3]
        if inside:
            covered += 1
        elif len(owners) >= 2:
            fragments += 1
            # rows of a table carry no full stop, so a "sentence" found there runs over several rows: that is how a table is
            # written, not a requirement cut in two. Counted apart so that reading more tables is not mistaken for worse splitting
            in_tables += all(c.kind in ("table_row", "table_header") for c in owners)
    bundles = []
    for c in body:
        if c.kind in ("table_row", "table_header", "definition"):
            continue
        inner = [(a, b) for a, b in sents if a >= c.start - 3 and b <= c.end + 3]
        units = {re.sub(r"[\d.,\s]", "", m).lower() for m in NUM.findall(c.text)}
        if len(inner) >= 2 or len(units) >= 2:
            bundles.append(c.id)
    ragged = [c.id for c in body if c.kind in ("article", "numbered", "paragraph") and c.text[:1].islower()]
    ids = {c.id.lower() for c in clauses}
    refs = resolved = 0
    for c in body:
        for m in REF.finditer(c.text):
            refs += 1
            target = re.sub(r"^(table|tableau|section|sec\.|article|art\.|chapter|figure|§)\s*", "", m.group(1).strip(), flags=re.I).lower()
            if any(target == i or i.endswith(" " + target) or i.startswith(target + " ") or i == "article " + target for i in ids):
                resolved += 1
    rows = [c for c in body if c.kind == "table_row"]
    return {"doc": path.name, "chars": len(full), "clauses": len(body), "obligation_sentences": len(sents), "covered": covered,
            "fragmented": fragments, "fragmented_in_tables": in_tables, "fragmented_in_prose": fragments - in_tables, "bundle_clauses": len(bundles), "ragged_start": len(ragged), "refs": refs,
            "refs_resolved": resolved, "table_rows": len(rows), "rows_with_parent": sum(1 for r in rows if r.parent)}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    folder = Path(args[0]) if args else Path("data/real_docs")
    out = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None
    cache = Path(os.environ.get("SPLIT_CACHE", "reports/split_cache"))
    cache.mkdir(parents=True, exist_ok=True)
    rows = [audit(p, cache) for p in sorted(folder.iterdir()) if p.suffix.lower() in (".pdf", ".md", ".txt", ".docx")]
    cols = ["doc", "clauses", "obligation_sentences", "covered", "fragmented", "fragmented_in_prose", "fragmented_in_tables", "bundle_clauses", "ragged_start", "refs", "refs_resolved"]
    print(" | ".join(cols))
    for r in rows:
        print(" | ".join(str(r[c]) for c in cols))
    tot = {k: sum(r[k] for r in rows) for k in cols[1:]}
    print("TOTAL", tot)
    if out:
        Path(out).write_text(json.dumps(rows, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
