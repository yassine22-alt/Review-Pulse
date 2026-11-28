"""How a sheet was read is said from what the reading wrote down, so a reading made without the model cannot pass for one."""

from types import SimpleNamespace

from reviewpulse.pipeline import reader_of


def sheet(mode="vector", *warnings):
    return SimpleNamespace(sheet=SimpleNamespace(mode=mode, warnings=list(warnings)))


def test_each_way_of_reading_is_named():
    assert reader_of(sheet()) == {"kind": "rules", "model": None}
    assert reader_of(sheet("vector", "learned primitive classifier applied (second pass)",
                           "trained drawing model: 0123456789ab")) == {"kind": "trained", "model": "0123456789ab"}
    assert reader_of(sheet("vector", "learned primitive classifier found no walls where the rules did (x)"))["kind"] == "fallback"
    assert reader_of(sheet("raster", "learned primitive classifier applied (second pass)"))["kind"] == "scan"


def test_no_model_file_means_no_version(tmp_path, monkeypatch):
    from reviewpulse.perception.learned.classifier import version

    monkeypatch.setenv("REVIEWPULSE_PRIMITIVE_MODEL", str(tmp_path))
    assert version() is None
    (tmp_path / "model.txt").write_text("one", encoding="utf-8")
    first = version()
    (tmp_path / "model.txt").write_text("another", encoding="utf-8")
    assert first and version() != first
