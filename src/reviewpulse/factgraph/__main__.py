"""python -m reviewpulse.factgraph <export|schema|show> ..."""

from __future__ import annotations

import argparse
import sys

from ..schema import BuildingModel
from . import io
from .convert import to_catalogue
from .from_building import from_building


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="factgraph")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("export", help="BuildingModel JSON -> fact graph JSON")
    ex.add_argument("building")
    ex.add_argument("out")
    ex.add_argument("--complete", action="store_true", help="declare the inventory reviewed as complete")
    sc = sub.add_parser("schema", help="write the JSON Schema of the format")
    sc.add_argument("out")
    sh = sub.add_parser("show", help="summary of a fact graph file")
    sh.add_argument("file")
    args = ap.parse_args(argv)
    if args.cmd == "export":
        model = BuildingModel.model_validate_json(open(args.building, encoding="utf-8").read())
        print(io.dump(from_building(model, complete=args.complete), args.out))
    elif args.cmd == "schema":
        print(io.write_json_schema(args.out))
    else:
        fg = io.load(args.file)
        print(f"{fg.provenance.sheet} tier {fg.provenance.tier}: {len(fg.nodes)} nodes, {len(fg.edges)} edges")
        for kind in fg.kinds():
            print(f"  {kind}: {sum(n.kind == kind for n in fg.nodes)}")
        print("catalogue:", to_catalogue(fg)["collections"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
