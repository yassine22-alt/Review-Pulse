"""Generate a gallery of variant demo plans, each showing a different part of ReviewPulse, with the answer written next to it.

    python scripts/make_demo_plans.py [output folder]        default: demo_plans

For every scenario it writes the plan as DXF and PDF, the exact truth (JSON), and one line in README.md saying what the
scenario shows and which findings ReviewPulse should report. Upload any plan together with docs/requirements_example.md
(or docs/requirements_example_fr.md for the French version of the same document).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from reviewpulse.synth.make_plan import make_plan
from reviewpulse.synth.random_plan import random_plan
from reviewpulse.synth.scenarios import SCENARIOS


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    lines = ["# Demo plans", "",
             "Each plan exists as DXF and PDF. Upload one with `docs/requirements_example.md` (or the French version) "
             "and compare with the expected findings.", "",
             "| Scenario | What it shows | Planted errors the older engine must also report |", "|---|---|---|"]
    for name, kind, kw, shows in SCENARIOS:
        folder = out / name
        folder.mkdir(exist_ok=True)
        paths = make_plan(folder, png=False, **kw) if kind == "make" else random_plan(folder, **kw)
        truth = json.loads(Path(paths["truth"]).read_text(encoding="utf-8"))
        expected = sorted({e["rule"] for e in truth.get("expected_findings", [])})
        lines.append(f"| `{name}` | {shows} | {', '.join(expected) or 'none'} |")
        print(f"{name}: {Path(paths['dxf']).name}, {Path(paths['pdf']).name}")
    (out / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n{len(SCENARIOS)} scenarios in {out.resolve()}  (see README.md there)")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "demo_plans"))
