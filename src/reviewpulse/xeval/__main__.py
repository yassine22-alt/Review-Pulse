"""python -m reviewpulse.xeval <setup|synth|scorer|probe|baseline|status> [options]"""

from __future__ import annotations

import argparse
import sys

from . import run
from .progress import Tracker
from .synth import read_corpus


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="xeval")
    ap.add_argument("command", choices=["setup", "synth", "scorer", "probe", "baseline", "status", "demand", "verifier", "ablate", "stress"])
    ap.add_argument("--n", type=int, default=None)
    ap.add_argument("--model", default="qwen2.5:7b")
    ap.add_argument("--per-family", type=int, default=2)
    ap.add_argument("--csv", default=None, help="sentence CSV with a `content` column (demand)")
    ap.add_argument("--french", action="store_true")
    args = ap.parse_args(argv)
    tr = Tracker()
    if args.command == "status":
        print(tr.console())
        return 0
    if args.command == "setup":
        tr.start("E0", detail="environment")
        tr.finish("E0", {"branch": "extractor-eval", "base": "origin/rule-interpreter"}, detail="ready")
    elif args.command == "synth":
        run.step_synth(tr, args.n or 200)
    elif args.command == "demand":
        from pathlib import Path

        from . import demand

        tr.start("E8", detail="parsing quantities")
        res = demand.run(Path(args.csv), run.OUT_DIR, args.french)
        tr.finish("E8", {"sentences": res["sentences"], "with_quantity": res["with_quantity"],
                         "top": ", ".join(f"{p} {c}" for p, c in res["by_property"][:4]),
                         "measured_today": f"{res['share_measured']:.0%}",
                         "measured_or_partial": f"{res['share_measured_or_partial']:.0%}"},
                  detail=f"{res['sentences']} sentences")
    elif args.command == "ablate":
        run.step_baseline(tr, args.model, args.n or 60, ("rec_verify", "expr", "expr_verify", "flat_cat_verify"), tid="E5",
                          name="ablate")
    elif args.command == "stress":
        run.step_stress(tr, read_corpus(run.CORPUS))
    elif args.command == "verifier":
        run.step_verifier(tr, read_corpus(run.CORPUS))
    elif args.command == "scorer":
        items = read_corpus(run.CORPUS)
        n = args.n or 60
        run.step_scorer_check(tr, items[:: max(1, len(items) // n)][:n])
    elif args.command == "probe":
        run.step_probe(tr, args.model, args.per_family)
    elif args.command == "baseline":
        run.step_baseline(tr, args.model, args.n or 30)
    print(tr.console())
    return 0


if __name__ == "__main__":
    sys.exit(main())
