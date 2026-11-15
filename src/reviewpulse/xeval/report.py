"""Turn raw run rows into answers: how often, how sure, and WHY it fails, per arm, family, language and split.

Every failed draft gets a cause from its error text. Every valid-but-wrong draft gets a cause from the sentence
check (a dropped category, an ignored number, a wrong direction) or "unexplained" when no check sees it. The
causes ranked by count are the fix list.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

from ..interpreter.schema import Program
from .synth import read_corpus
from .verify import verify

CAUSES = [  # (cause, regex on the error text); first match wins
    ("generation ran away (token cap or timeout)", r"token cap|TimeoutError|timed out"),
    ("model output is not valid JSON", r"JSONDecodeError|Expecting"),
    ("dangling reference (node id that does not exist)", r"unknown node id"),
    ("cycle between nodes", r"cycle through"),
    ("invented fact name", r"unsupported fact|not declared|is not a variable"),
    ("invented collection", r"unsupported collection"),
    ("variable scope (unbound or shadowed)", r"unbound variable|variable shadowing"),
    ("units or types do not fit", r"incompatible types|dimensional arithmetic|requires (?:a )?(?:boolean|number)|"
                                  r"filter requires|must produce a boolean|requires booleans|requires numbers"),
    ("quote not found in the clause", r"quote not found|source quote"),
    ("expression could not be parsed", r"expression:|cannot read the expression|expected '|unexpected"),
    ("form fields missing or wrong type", r"ValidationError|validation error|Field required|Input should"),
    ("rejected by the sentence check", r"verifier:"),
]
WRONG_CAUSES = {"scope_dropped": "a category in the sentence is missing from the rule",
                "number_ignored": "a number in the sentence is not used by the rule",
                "number_not_in_sentence": "the rule uses a number the sentence does not state",
                "direction": "a comparison points the wrong way",
                "scope_invented": "the rule restricts to a category the sentence does not name"}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, centre - half), min(1.0, centre + half)


def cause_of(detail: str) -> str:
    for name, pattern in CAUSES:
        if re.search(pattern, detail or ""):
            return name
    return "other"


def pct(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {k / max(n, 1):.0%} (95% CI {lo:.0%} to {hi:.0%})"


def wrong_cause(row: dict, items: dict) -> str:
    item = items.get(row["item"])
    if not item or "program" not in row:
        return "unknown"
    try:
        issues = verify(Program.model_validate(row["program"]), item.text, item.catalogue, item.lang)
    except Exception:  # noqa: BLE001
        return "unknown"
    for code in ("scope_dropped", "number_ignored", "number_not_in_sentence", "direction"):
        if any(i.code == code for i in issues):
            return WRONG_CAUSES[code]
    return "not visible to any current check (structure or logic differs)"


def build(rows: list[dict], corpus: Path, title: str = "Extractor run") -> str:
    items = {i.id: i for i in read_corpus(corpus)}
    arms = sorted({r["arm"] for r in rows}, key=lambda a: [r["arm"] for r in rows].index(a))
    out = [f"# {title}", "", f"{len(rows)} drafts, {len({r['item'] for r in rows})} items, arms: {', '.join(arms)}", "",
           "## Headline (a draft counts as right only if it behaves like the reference on generated plans)", "",
           "| Arm | Valid | Right | Valid but wrong | (of which differ only on UNRESOLVED vs a verdict) | Rejected or failed | Median time |", "|---|---|---|---|---|---|---|"]
    for arm in arms:
        sub = [r for r in rows if r["arm"] == arm]
        valid = [r for r in sub if r["stage"] == "ok"]
        right = sum(bool(r.get("equivalent")) for r in valid)
        times = sorted(r["seconds"] for r in sub)
        out.append(f"| {arm} | {pct(len(valid), len(sub))} | {pct(right, len(sub))} | "
                   f"{pct(len(valid) - right, len(sub))} | "
                   f"{sum(not r.get('equivalent') and set(r.get('kinds', {})) <= {'resolution_mismatch'} for r in valid)} | "
                   f"{pct(len(sub) - len(valid), len(sub))} | "
                   f"{times[len(times) // 2]:.0f}s |")
    out += ["", "A rule that is valid but wrong is the dangerous case: a reviewer could approve it.", ""]

    out += ["## Why drafts fail (per arm, most common first)", ""]
    for arm in arms:
        failed = [r for r in rows if r["arm"] == arm and r["stage"] != "ok"]
        out.append(f"**{arm}** ({len(failed)} failed)")
        for cause, count in Counter(cause_of(r["detail"]) for r in failed).most_common():
            out.append(f"- {count}: {cause}")
        out.append("")

    out += ["## Why valid drafts are wrong (per arm)", ""]
    for arm in arms:
        wrong = [r for r in rows if r["arm"] == arm and r["stage"] == "ok" and not r.get("equivalent")]
        out.append(f"**{arm}** ({len(wrong)} valid but wrong)")
        for cause, count in Counter(wrong_cause(r, items) for r in wrong).most_common():
            out.append(f"- {count}: {cause}")
        out.append("")

    for label, key in (("rule shape", "family"), ("language", "lang"), ("concepts dev or held out", "split")):
        out += [f"## Right, by {label}", "", "| " + label + " | " + " | ".join(arms) + " |",
                "|---|" + "---|" * len(arms)]
        groups = sorted({r.get(key, "?") for r in rows})
        for g in groups:
            cells = []
            for arm in arms:
                sub = [r for r in rows if r["arm"] == arm and r.get(key, "?") == g]
                cells.append(f"{sum(bool(r.get('equivalent')) for r in sub)}/{len(sub)}" if sub else "-")
            out.append(f"| {g} | " + " | ".join(cells) + " |")
        out.append("")

    out += ["## Examples of valid but wrong drafts", ""]
    shown = 0
    for r in rows:
        if r["stage"] == "ok" and not r.get("equivalent") and shown < 6 and r["item"] in items:
            from .expr_ir import to_text

            item = items[r["item"]]
            out += [f"- **{r['arm']}** on \"{item.text}\"",
                    f"  - rule written: `{to_text(r['program']['requirement'])[:200]}`",
                    f"  - reference:    `{to_text(item.program['requirement'])[:200]}`",
                    f"  - cause: {wrong_cause(r, items)}"]
            shown += 1
    return "\n".join(out) + "\n"


def run(rows_path: Path, corpus: Path, out_path: Path, title: str) -> Path:
    rows = [json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    out_path.write_text(build(rows, corpus, title), encoding="utf-8")
    return out_path


if __name__ == "__main__":
    import sys

    base = Path("reports/extractor_eval")
    name = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    print(run(base / f"{name}_rows.jsonl", base / "corpus.jsonl", base / f"{name}_findings.md", f"Findings: {name}"))
