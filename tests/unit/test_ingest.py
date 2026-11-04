import pytest
from typer.testing import CliRunner

from reviewpulse.cli import app
from reviewpulse.ingest.classify import IngestError, decide_mode, detect_type


def test_corrupt_pdf_exits_2_with_one_line(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf at all")
    res = CliRunner().invoke(app, ["inspect", str(bad), "--runs", str(tmp_path / "runs")])
    assert res.exit_code == 2
    assert "error" in res.output.lower()


def test_missing_file(tmp_path):
    with pytest.raises(IngestError):
        detect_type(tmp_path / "nope.dxf")


@pytest.mark.parametrize("paths,cover,mode", [(500, 0.0, "vector"), (10, 0.95, "raster"), (300, 0.6, "mixed"),
                                              (100, 0.1, "mixed")])
def test_mode_rule(paths, cover, mode):
    assert decide_mode(paths, cover) == mode


def test_synthetic_files_are_classified(synth_dir):
    from reviewpulse.ingest.classify import inspect_file
    from reviewpulse.synth.make_plan import make_plan

    p = make_plan(synth_dir, seed=3)
    assert inspect_file(p["pdf"])[0].mode == "vector"
    assert inspect_file(p["dxf"])[0].file_type == "dxf"
    st = inspect_file(p["png"])[0]
    assert st.mode == "raster" and st.dpi


def test_unitless_dxf_warns_and_does_not_crash(tmp_path):
    import ezdxf

    from reviewpulse.ingest.dxf_reader import extract_dxf

    doc = ezdxf.new()
    doc.header["$INSUNITS"] = 0
    doc.modelspace().add_line((0, 0), (1000, 0))
    doc.saveas(tmp_path / "u.dxf")
    s = extract_dxf(tmp_path / "u.dxf", "u")
    assert s.scale.metres_per_unit is None
    assert any("unitless" in w for w in s.warnings)


def test_rotated_mirrored_block_lands_on_analytic_points(tmp_path):
    """R3: INSERT rotated 30 deg, scaled 2, and a mirrored copy."""
    import math

    import ezdxf

    from reviewpulse.ingest.dxf_reader import extract_dxf

    doc = ezdxf.new()
    b = doc.blocks.new("B")
    b.add_line((0, 0), (1, 0))
    b.add_arc((0, 0), 1, 0, 90)
    msp = doc.modelspace()
    msp.add_blockref("B", (10, 10), dxfattribs={"rotation": 30, "xscale": 2, "yscale": 2})
    msp.add_blockref("B", (20, 10), dxfattribs={"xscale": 1, "yscale": -1})
    doc.saveas(tmp_path / "b.dxf")
    s = extract_dxf(tmp_path / "b.dxf", "b")
    line = next(p for p in s.primitives if p.kind == "line" and abs(p.pts[0][0] - 10) < 1e-6)
    assert line.pts[1] == pytest.approx((10 + 2 * math.cos(math.radians(30)), 10 + 2 * math.sin(math.radians(30))))
    mirrored = [p for p in s.primitives if p.kind == "arc" and abs(p.center[0] - 20) < 1e-6][0]
    # mirrored about x: the quarter arc now sweeps from 270 to 360 degrees
    assert mirrored.a0 == pytest.approx(270, abs=1e-6) and mirrored.a1 % 360 == pytest.approx(0, abs=1e-6)
