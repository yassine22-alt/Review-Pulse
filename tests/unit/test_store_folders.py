"""A project keeps working when its empty folders vanish (seen on a real run: a long analysis in the temp folder)."""

import shutil

from reviewpulse.app.store import PROJECT_FOLDERS, Store


def _drop_empty(store, pid):
    for sub in PROJECT_FOLDERS:
        folder = store.dir(pid) / sub
        if folder.exists() and not any(folder.iterdir()):
            folder.rmdir()
    shutil.rmtree(store.dir(pid) / "inputs" / "req", ignore_errors=True)


def test_upload_after_folders_vanished_since_the_project_was_read(tmp_path):
    store = Store(tmp_path)
    p = store.create("demo")
    _drop_empty(store, p.id)
    path = store.put_input(p, "requirements", "rules.txt", b"1. Doors are 0.80 m wide.")
    assert path.read_bytes().startswith(b"1.")


def test_reading_a_project_restores_every_folder(tmp_path):
    store = Store(tmp_path)
    pid = store.create("demo").id
    _drop_empty(store, pid)
    store.get(pid)
    assert all((store.dir(pid) / sub).is_dir() for sub in PROJECT_FOLDERS)
