"""Run the acceptance suite (reviewpulse.eval.acceptance) and write reports/<date>_acceptance.md.

    python scripts/acceptance.py [--only dxf,png_scan] [--kind vector|raster] [--work runs/acceptance]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> None:
    from reviewpulse.eval.acceptance import CASES, run_case, write_report

    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--kind", default="")
    ap.add_argument("--work", default=str(ROOT / "runs" / "acceptance"))
    a = ap.parse_args()
    only = set(filter(None, a.only.split(",")))
    work = Path(a.work)
    results = []
    for case in CASES:
        if (only and case.name not in only) or (a.kind and case.kind != a.kind):
            continue
        d = work / case.name
        shutil.rmtree(d, ignore_errors=True)
        r = run_case(case, d)
        results.append(r)
        print(json.dumps({k: r.get(k) for k in ("case", "ok", "tiers", "seconds_per_page", "planted_found",
                                                "planted_missed", "problems")}), flush=True)
    out = write_report(results, ROOT / "reports" / f"{dt.date.today()}_acceptance.md")
    print("report:", out)
    sys.exit(0 if all(r.get("ok") for r in results) else 1)


if __name__ == "__main__":
    main()
