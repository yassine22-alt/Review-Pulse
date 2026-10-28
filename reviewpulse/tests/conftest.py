import os
import sys
from pathlib import Path

import pytest

# unit/golden tests are hermetic: the LLM label fallback is exercised by tests/acceptance with a stub
os.environ.setdefault("REVIEWPULSE_LABEL_LLM", "0")
# ...and do not depend on whether a trained primitive model is installed (data/models is not in git):
# the rules pass is the default here; tests of the learned pass ask for it explicitly
os.environ.setdefault("REVIEWPULSE_LEARNED", "0")
sys.path.insert(0, str(Path(__file__).parent / "fixtures"))


def pytest_addoption(parser):
    parser.addoption("--snapshot-update", action="store_true", default=False,
                     help="rewrite tests/golden/snapshots/*.json from the current pipeline (review the diff)")


@pytest.fixture(scope="session")
def pack():
    from reviewpulse.cli import DEFAULT_PACK
    from reviewpulse.rules.schema import load_pack

    return load_pack(DEFAULT_PACK)


@pytest.fixture(scope="session")
def synth_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("synth")
