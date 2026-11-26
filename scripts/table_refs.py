"""How many references to a table ("see Table B4") reach a table that was read? No label is needed.

    python scripts/table_refs.py data/real_docs [--json reports/table_refs.json]

For every PDF: the tables the reader named after their caption, the references to a table in the running text, and how many of
those references resolve through the same code the product uses to bring a referenced clause into what the model reads
(`assemble_context`). A reference that does not resolve is listed, so the reason can be read (a table drawn as a picture, a
table of another document, a caption the reader missed).
"""

from __future__ import annotations

import argparse
import json
import re
import time
from collections import Counter
from pathlib import Path

from reviewpulse.interpreter.context import REFERENCE, TABLE_WORDS, assemble_context
from reviewpulse.rules.clauses import split_document


def audit(path: Path) -> dict:
    t0 = time.time()
    full, clauses = split_document(path)
    ids = {c.id for c in clauses}
    named = sorted(c.id for c in clauses if c.kind == "table_header" and re.match(r"Table\s", c.id))
    unnamed = sum(1 for c in clauses if c.kind == "table_header" and not re.match(r"Table\s", c.id))
    refs, missed = 0, Counter()
    resolved_in_context = 0
    for c in clauses:
        if c.kind in ("table_header", "table_row"):
            continue
        targets = {f"Table {m.group(2)}" for m in REFERENCE.finditer(c.text) if m.group(1).lower() in TABLE_WORDS}
        if not targets:
            continue
        bundle = assemble_context(path.name, full, clauses, c.id)
        got = {x.id for x in bundle.clauses}
        for target in targets:
            refs += 1
            if target in ids and target in got:
                resolved_in_context += 1
            else:
                missed[target] += 1
    return {"document": path.name, "seconds": round(time.time() - t0, 1), "clauses": len(clauses), "tables_named": len(named),
            "tables_unnamed": unnamed, "table_rows": sum(1 for c in clauses if c.kind == "table_row"),
            "references": refs, "resolved": resolved_in_context, "unresolved": dict(missed.most_common()), "named": named}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("docs")
    ap.add_argument("--json", default="")
    args = ap.parse_args()
    root = Path(args.docs)
    out = []
    for path in (sorted(root.glob("*.pdf")) if root.is_dir() else [root]):
        r = audit(path)
        out.append(r)
        print(f"{r['document'][:40]:<40} tables named {r['tables_named']:>3}, unnamed {r['tables_unnamed']:>3}, rows {r['table_rows']:>5}; "
              f"references {r['references']:>4}, resolved {r['resolved']:>4}  ({r['seconds']} s)", flush=True)
        if r["unresolved"]:
            print("   unresolved:", r["unresolved"], flush=True)
    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
