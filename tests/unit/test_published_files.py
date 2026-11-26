"""Files the app rewrites while requests read them are never seen half written."""

import threading
import time

from reviewpulse.app.store import publish, read_whole
from reviewpulse.schema import load_findings, save_findings


def test_a_reader_sees_one_whole_version_while_the_file_is_rewritten(tmp_path):
    path = tmp_path / "backdrop_0.png"
    versions = [b"a" * 200_000, b"b" * 700_000]
    publish(path, versions[0])
    stop, bad = threading.Event(), []

    def read():
        while not stop.is_set():
            got = read_whole(path)
            if got not in versions:
                bad.append(len(got))
            time.sleep(0.002)                      # as requests do, not a loop that never lets go of the file

    readers = [threading.Thread(target=read) for _ in range(3)]
    for r in readers:
        r.start()
    try:
        for k in range(60):
            publish(path, versions[k % 2])
    finally:
        stop.set()
        for r in readers:
            r.join()
    assert bad == []
    assert [p.name for p in tmp_path.iterdir()] == ["backdrop_0.png"]          # no temporary file is left


def test_findings_are_replaced_whole(tmp_path):
    path = tmp_path / "findings.json"
    save_findings([], path)
    save_findings([], path)
    assert load_findings(path) == [] and [p.name for p in tmp_path.iterdir()] == ["findings.json"]
