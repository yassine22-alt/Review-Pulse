"""K-P1: the brief (programme) against the plan, on a generated plan with exact truth.

The brief is written from the generator's truth (areas rounded down to 0.5 m2, as briefs state
round numbers), in every format a client may send; then mismatches are planted in the brief."""

import json
import math
from pathlib import Path

import pytest

from reviewpulse.engine.run import run
from reviewpulse.eval.cli import _model_from
from reviewpulse.rules.programme import attach_programme, read_programme


@pytest.fixture(scope="module")
def plan(tmp_path_factory):
    from reviewpulse.synth.make_plan import make_plan

    d = tmp_path_factory.mktemp("prog")
    p = make_plan(d, seed=41, png=False, name="prog41")
    truth = json.loads(Path(p["truth"]).read_text(encoding="utf-8"))
    rooms = [r for r in truth["rooms"] if r["type"] not in ("corridor", "entry")]
    return p, rooms, d


def write_brief(path: Path, rows: list[tuple[str, int, float]], header=("Pièce", "Nb", "Surface (m²)")):
    suf = path.suffix
    if suf == ".csv":
        lines = [";".join(header)] + [f"{a};{n};{str(s).replace('.', ',')}" for a, n, s in rows] + ["Total;;"]
        path.write_text("\n".join(lines), encoding="utf-8")
    elif suf == ".md":
        lines = ["Programme des logements", "", "| " + " | ".join(header) + " |", "|---|---|---|"]
        lines += [f"| {a} | {n} | {s} |" for a, n, s in rows]
        path.write_text("\n".join(lines), encoding="utf-8")
    elif suf == ".xlsx":
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Housing brief, block B"])
        ws.append(list(header))
        for r in rows:
            ws.append(list(r))
        wb.save(path)
    elif suf == ".docx":
        import docx

        doc = docx.Document()
        doc.add_paragraph("Programme")
        t = doc.add_table(rows=1, cols=3)
        for c, h in zip(t.rows[0].cells, header):
            c.text = h
        for a, n, s in rows:
            cells = t.add_row().cells
            cells[0].text, cells[1].text, cells[2].text = a, str(n), str(s)
        doc.save(str(path))
    return path


def brief_rows(rooms):
    # at least 0.25 m2 below the true area: a brief set exactly at the drawn area sits inside the
    # measurement tolerance band, where the rule rightly answers WARNING
    return [(r["label"], 1, math.floor((r["area_m2"] - 0.25) * 2) / 2) for r in rooms]


@pytest.mark.parametrize("fmt,header", [(".csv", ("Pièce", "Nb", "Surface (m²)")),
                                        (".xlsx", ("Room", "Qty", "Area (m2)")),
                                        (".docx", ("Local", "Nombre", "Surface habitable")),
                                        (".md", ("Designation", "Count", "Area"))])
def test_every_format_reads_the_same_brief(plan, fmt, header):
    _p, rooms, d = plan
    rows = brief_rows(rooms)
    got = read_programme(write_brief(d / f"brief{fmt}", rows, header))
    assert [(r["label"], r["count"], r["area_m2"]) for r in got] == [(a, n, float(s)) for a, n, s in rows]
    assert all(r["type"] for r in got)


def _k_p1(pack, model):
    return [f for f in run(model, pack) if f.rule_id == "K-P1"]


def test_brief_matching_the_plan_passes(plan, pack):
    p, rooms, d = plan
    m = attach_programme(_model_from(p["dxf"]), write_brief(d / "ok.csv", brief_rows(rooms)))
    f = _k_p1(pack, m)
    assert f and all(x.verdict == "PASS" for x in f), [(x.verdict, x.message) for x in f]


def test_missing_room_and_small_room_fail(plan, pack):
    p, rooms, d = plan
    rows = brief_rows(rooms)
    living = next(i for i, r in enumerate(rooms) if r["type"] == "living")
    a, n, s = rows[living]
    rows[living] = (a, n, s + 3.0)                       # the brief asks 3 m2 more than drawn
    rows.append(("Chambre 9", 1, 9.0))                   # and one bedroom more than the plan has
    m = attach_programme(_model_from(p["dxf"]), write_brief(d / "bad.csv", rows))
    bad = [x for x in _k_p1(pack, m) if x.verdict == "FAIL"]
    assert any("bedroom" in x.message and "in the brief" in x.message for x in bad)
    assert any(x.subject_ids == [next(r.id for r in m.rooms if r.type == "living")] for x in bad)
    assert len(bad) == 2


def test_shortfall_with_an_unlabelled_room_is_not_evaluated(plan, pack):
    p, rooms, d = plan
    rows = brief_rows(rooms) + [("Chambre 9", 1, 9.0)]
    m = attach_programme(_model_from(p["dxf"]), write_brief(d / "short.csv", rows))
    m.rooms[0].type = None                              # a room whose label was not read
    f = _k_p1(pack, m)
    assert not any(x.verdict == "FAIL" and "bedroom" in x.message for x in f)
    assert any(x.verdict == "NOT_EVALUATED" for x in f)


def test_without_a_brief_the_rule_says_what_is_missing(plan, pack):
    p, _rooms, _d = plan
    f = _k_p1(pack, _model_from(p["dxf"]))
    assert [x.verdict for x in f] == ["NOT_EVALUATED"] and "programme" in f[0].message
