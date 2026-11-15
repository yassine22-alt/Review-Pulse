"""The generated contract docs match the code (scripts/gen_docs.py --check)."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_generated_docs_are_current():
    spec = importlib.util.spec_from_file_location("gen_docs", ROOT / "scripts" / "gen_docs.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    stale = [p.name for p, text in gen.outputs().items()
             if not p.exists() or p.read_text(encoding="utf-8") != text]
    assert not stale, f"out of date, run python scripts/gen_docs.py: {stale}"
