"""Every source and script file must compile. A module that is imported lazily (one reasoning arm, one backend) can be broken
without any other test noticing until a user reaches it."""

import py_compile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FILES = sorted([*(ROOT / "src").rglob("*.py"), *(ROOT / "scripts").glob("*.py")])


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_the_file_compiles(path, tmp_path):
    py_compile.compile(str(path), cfile=str(tmp_path / "x.pyc"), doraise=True)
