"""Evaluation pack: run real drawings through ReviewPulse and write a page that anyone can read and judge.

    python scripts/review_pack.py [--out reports/review_pack] [--set sheets.json] [--only text,text]

For every sheet in the set the pack runs the plan analysis the application runs (same code, no special mode), then writes one
self-contained folder: index.html, a pair of images per sheet (the original page and what was found), and metrics.json.

The pack is annotation free. It does not compare against a hand-made answer; it compares the result with what the drawing
prints about itself (its scale, the areas it states for rooms). Each sheet gets a plain verdict with the reasons, so a reader
sees where the tool can be trusted and where it cannot. The pack states its own limits at the end.

A set file is a JSON list of {"name", "pdf", "pages": [1-based page numbers], "source": "where the file is from"}.
The real drawings are third party documents used for local testing: they are never committed (data/real_plans and reports
are git ignored). The generated pack contains images of them, so share it only where that is allowed.
"""

from __future__ import annotations

import argparse
import datetime
import html
import json
import subprocess
import tempfile
import time
from pathlib import Path

import pymupdf

from reviewpulse import pipeline

DEFAULT_SET = [
    {"name": "Complex first floor, US permit set (feet and inches)", "pdf": "data/real_plans/chief_architect_austin.pdf",
     "pages": [5], "source": "Chief Architect sample permit set, public download"},
    {"name": "Clean small house plan, US recovery sample set", "pdf": "data/real_plans/rebuildflorida_floorplans.pdf",
     "pages": [3], "source": "Rebuild Florida sample plans, public download"},
    {"name": "Apartment plans, German, text drawn as outlines", "pdf": "data/real_plans/de_beispielgrundrisse_3raum.pdf",
     "pages": [1, 2, 3], "source": "housing cooperative sample floor plans, public download"},
    {"name": "Building permit plans, German, hatched walls", "pdf": "data/real_plans/de_baugesuch_cleebronn.pdf",
     "pages": [3, 4], "source": "municipal council record of a permit application, public download"},
]


def sheet_metrics(building: dict, scale_rep: dict, seconds: float) -> dict:
    rooms, els, edges = building["rooms"], building["elements"], building["edges"]
    sheet = building["sheet"]
    with_area = [r for r in rooms if r.get("stated_area_m2") and r.get("area_m2")]
    ratios = sorted(round(r["area_m2"] / r["stated_area_m2"], 2) for r in with_area)
    counts = {c: sum(1 for e in els if e["cls"] == c) for c in ("wall", "door", "window", "opening", "stair")}
    warnings = sheet.get("warnings") or []
    ocr = [w for w in warnings if w.startswith("text_as_outlines:") and "words read" in w]
    return {
        "scale_method": sheet["scale"]["method"], "scale_confidence": sheet["scale"]["confidence"],
        "metres_per_unit": sheet["scale"]["metres_per_unit"], "scale_notes": scale_rep.get("notes", [])[:3],
        "rooms": len(rooms), "rooms_inferred": sum(1 for r in rooms if r["prov"]["evidence"].get("boundary")),
        "rooms_with_printed_area": len(with_area),
        "within25": sum(0.75 <= x <= 1.25 for x in ratios), "within50": sum(0.5 <= x <= 1.5 for x in ratios), "ratios": ratios,
        "largest_room_m2": max((r["area_m2"] for r in rooms if r.get("area_m2")), default=None),
        "labelled_rooms": sum(1 for r in rooms if r.get("label")),
        **{f"n_{k}": v for k, v in counts.items()},
        "door_edges": sum(1 for e in edges if e["kind"] == "door"),
        "exit_edges": sum(1 for e in edges if e["b"] == "EXIT"),
        "ocr_words": int(ocr[0].split(":")[1].split()[0]) if ocr else 0,
        "warnings": [w[:200] for w in warnings][:8], "seconds": round(seconds, 1),
    }


def verdict(m: dict) -> tuple[str, str, list[str]]:
    """(label, colour, plain reasons). Deliberately strict: a sheet is only 'readable' when the evidence supports it."""
    if m["scale_method"] == "none":
        return "not usable", "red", ["The scale could not be found, so nothing can be measured in metres."]
    if m["rooms"] == 0:
        return "not usable", "red", ["No rooms were found on this sheet."]
    caveats = []
    if m["scale_method"] in ("title_block", "symbol_prior", "stated_areas"):
        how = {"title_block": "written on the sheet", "symbol_prior": "estimated from door sizes",
               "stated_areas": "derived from the room areas the drawing prints"}[m["scale_method"]]
        caveats.append(f"The scale is {how}; it was not confirmed by measured dimensions.")
    if m["rooms_inferred"]:
        caveats.append(f"{m['rooms_inferred']} room boundaries are inferred from room names, not from drawn walls.")
    n = m["rooms_with_printed_area"]
    if n >= 3 and m["within25"] / n < 0.7:
        caveats.append(f"Only {m['within25']} of {n} rooms agree with their printed area within 25%.")
    if n == 0:
        caveats.append("The drawing prints no room areas, so the measured room sizes could not be cross-checked.")
    if m["n_door"] + m["n_opening"] == 0:
        caveats.append("No doors were found, so routes between rooms cannot be checked.")
    if m["largest_room_m2"] and m["largest_room_m2"] > 250:
        caveats.append(f"A room of {m['largest_room_m2']:.0f} m2 was found; spaces were probably merged.")
    if caveats:
        return "readable with caveats", "amber", caveats
    return "readable", "green", ["Scale, room sizes and doors are consistent with what the drawing prints."]


def run_sheet(pdf: Path, page: int, out: Path, key: str) -> dict:
    doc = pymupdf.open(pdf)
    with tempfile.TemporaryDirectory() as tmp:
        one = pymupdf.open()
        one.insert_pdf(doc, from_page=page - 1, to_page=page - 1)
        single = Path(tmp) / f"{key}.pdf"
        one.save(single)
        t0 = time.time()
        rd = pipeline.inspect(single, Path(tmp) / "runs", run_id="r")
        pipeline.extract(rd)
        pipeline.build(rd)
        seconds = time.time() - t0
        b = json.loads(next(Path(rd).glob("building_*.json")).read_text(encoding="utf-8"))
        sc = json.loads(next(Path(rd).glob("scale_report_*.json")).read_text(encoding="utf-8"))
        overlay = next(Path(rd).glob("rooms_*.png"), None)
        if overlay:
            (out / f"{key}_found.png").write_bytes(overlay.read_bytes())
    doc[page - 1].get_pixmap(dpi=70).save(out / f"{key}_page.png")
    m = sheet_metrics(b, sc, seconds)
    m["verdict"], m["colour"], m["reasons"] = verdict(m)
    return m


def version_line() -> str:
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=10).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True,
                                    timeout=10).stdout.strip())
    except Exception:  # noqa: BLE001 - a pack can be made outside a repository
        commit, dirty = "", False
    return f"{datetime.date.today().isoformat()}, code version {commit or 'unknown'}{' plus local changes' if dirty else ''}"


CSS = """:root{--bg:#f6f7f9;--fg:#1b1f24;--card:#fff;--line:#d9dde3;--mut:#5b6570}
@media(prefers-color-scheme:dark){:root{--bg:#14171a;--fg:#e8eaed;--card:#1d2125;--line:#363b41;--mut:#a0a8b0}}
body{font:15px/1.55 system-ui,Segoe UI,sans-serif;margin:0;background:var(--bg);color:var(--fg)}
main{max-width:1180px;margin:0 auto;padding:24px 16px 72px}h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;margin:0 0 6px}
h3{font-size:16px;margin:22px 0 4px}.card{background:var(--card);border:1px solid var(--line);border-radius:10px;margin:20px 0;padding:16px}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:12px 0}.pair figure{margin:0}
.pair img{width:100%;border:1px solid var(--line);border-radius:6px;background:#fff}
figcaption,.small{color:var(--mut);font-size:13px}.pill{display:inline-block;padding:2px 10px;border-radius:12px;font-weight:600;
font-size:13px;color:#fff;white-space:nowrap}.green{background:#1e8e3e}.amber{background:#b06000}.red{background:#c5221f}
table{border-collapse:collapse;font-size:14px}td,th{padding:4px 14px 4px 0;text-align:left;vertical-align:top}
th{color:var(--mut);font-weight:600}ul{margin:4px 0 0 18px;padding:0}code{font-size:13px}
@media(max-width:800px){.pair{grid-template-columns:1fr}}"""

INTRO = """<p><b>ReviewPulse</b> reads an architectural or engineering plan and a requirements document, turns the requirements into
rules a person approves, and checks the plan against them. This pack shows only the first half of that chain on real drawings:
<b>can the tool read the plan correctly?</b> If the rooms, doors and scale are wrong, any compliance result built on them is
wrong, so this is the part that has to be trustworthy first.</p>
<p>Each sheet below was run exactly as the application runs it. Nothing was annotated by hand and nothing was tuned for a
particular drawing. Where the drawing prints facts about itself (its scale, the area of each room) the result is compared with
them. Where it does not, the pack says so.</p>"""

HOW_TO_READ = """<h3>How to read this pack</h3>
<ul>
<li><b>Verdict.</b> <span class='pill green'>readable</span> the evidence supports the result;
<span class='pill amber'>readable with caveats</span> usable, but the reasons listed must be kept in mind;
<span class='pill red'>not usable</span> the tool cannot read this sheet reliably, and it says so instead of guessing.</li>
<li><b>Images.</b> Left, the original page. Right, what was found: coloured rooms with their names and measured areas, green
doors, red openings and windows, dark wall and fixture shapes.</li>
<li><b>Printed areas.</b> A drawing that prints each room's area gives an independent check. The table lists measured area divided
by printed area per room: 1.00 is exact, and a tight group of values means the rooms agree with each other even if the scale is
slightly off.</li>
</ul>"""

METHOD = """<h2>Method</h2>
<ul>
<li><b>Input.</b> One page of a vector PDF at a time. Text drawn as outlines is read by OCR (RapidOCR, PaddleOCR or EasyOCR,
whichever is installed).</li>
<li><b>Scale.</b> In order of trust: dimension text paired with its dimension line (agreeing pairs only); a scale written on the
sheet (metric or feet and inches, several languages) that agreeing dimensions confirm; a written scale alone; the room areas printed
on the drawing, when several rooms agree closely. A written scale is replaced by the printed areas only when at least five rooms
agree within a 4% spread and imply a scale that differs by more than 6%. Scattered evidence gives no scale rather than a wrong one.</li>
<li><b>Walls, doors, windows.</b> Geometric rules on the drawing primitives (paired faces, filled strips, door swing arcs including
part-open swings, gaps in walls), with a learned classifier as a second pass where a model is available.</li>
<li><b>Rooms.</b> Free space left by the walls. Where several named rooms share one region (a wall was missed, a doorway has no
symbol), the region is divided among the room names by flooding outward from each name, so that boundaries fall at the narrowest
points. The outside of the building competes as one more region. Boundaries made this way are marked as inferred.</li>
<li><b>Verdict.</b> Strict rules on the evidence above: no scale or no rooms is not usable; anything inferred, unconfirmed or
unchecked is a caveat; only a sheet with nothing to caveat is readable.</li>
</ul>"""

LIMITS = """<h2>Limits of this pack</h2>
<ul>
<li>It is a small, varied sample of real drawings, not a benchmark. It shows how the tool behaves on drawings it was not built
around; it does not estimate an overall accuracy.</li>
<li>Agreement with printed areas is partly circular on sheets whose scale came from those same areas. The independent evidence there
is that the rooms agree with each other.</li>
<li>Only vector PDFs are read. Scans and hand sketches are not read by this path.</li>
<li>Printed areas often count differently from a measured polygon (wall centrelines, balconies, niches), so a small gap is normal.</li>
<li>This pack evaluates plan reading, not compliance. A readable sheet is a precondition for checking rules, not a result of
checking them.</li>
</ul>"""


def page(rows: list[dict], sources: dict[str, str]) -> str:
    out = [f"<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
           f"<title>ReviewPulse evaluation pack</title><style>{CSS}</style><main>",
           "<h1>ReviewPulse evaluation pack: reading real drawings</h1>",
           f"<p class=small>Generated {html.escape(version_line())}. {len(rows)} sheet(s).</p>", INTRO, HOW_TO_READ,
           "<h2>Summary</h2><table><tr><th>Sheet<th>Verdict<th>Scale<th>Rooms<th>Doors<th>Printed areas within 25%</tr>"]
    for r in rows:
        m = r["m"]
        n = m["rooms_with_printed_area"]
        agree = f"{m['within25']} of {n}" if n else "none printed"
        out.append(f"<tr><td><a href='#{r['key']}'>{html.escape(r['title'])}</a><td><span class='pill {m['colour']}'>{m['verdict']}</span>"
                   f"<td>{m['scale_method'].replace('_', ' ')}<td>{m['rooms']}<td>{m['n_door']}<td>{agree}</tr>")
    out.append("</table>")
    for r in rows:
        m = r["m"]
        mpu = m["metres_per_unit"]
        unit_text = f"{mpu:.4g} m per sheet unit" if mpu else "unknown"
        out.append(f"<section class=card id='{r['key']}'><h2>{html.escape(r['title'])} "
                   f"<span class='pill {m['colour']}'>{m['verdict']}</span></h2>")
        out.append(f"<p class=small>Source: {html.escape(sources.get(r['key'], ''))}</p>")
        out.append("<ul>" + "".join(f"<li>{html.escape(x)}</li>" for x in m["reasons"]) + "</ul>")
        out.append(f"<div class=pair><figure><img src='{r['key']}_page.png' alt='original page'><figcaption>Original page</figcaption></figure>"
                   f"<figure><img src='{r['key']}_found.png' alt='what was found'><figcaption>What was found</figcaption></figure></div>")
        out.append("<table>"
                   f"<tr><th>Scale<td>{m['scale_method'].replace('_', ' ')} (confidence {m['scale_confidence']}), {unit_text}"
                   f"<tr><th>Rooms<td>{m['rooms']} found, {m['labelled_rooms']} named, {m['rooms_inferred']} with inferred boundaries"
                   f"<tr><th>Openings<td>{m['n_door']} doors, {m['n_window']} windows, {m['n_opening']} openings, {m['n_stair']} stairs; "
                   f"{m['door_edges']} door connections, {m['exit_edges']} routes to the outside"
                   f"<tr><th>Printed areas<td>{m['rooms_with_printed_area']} rooms carry one; measured over printed: {m['ratios'] or 'not available'}"
                   f"<tr><th>Text read by OCR<td>{m['ocr_words']} words"
                   f"<tr><th>Analysis time<td>{m['seconds']} s</table>")
        if m["scale_notes"]:
            out.append("<p class=small><b>Scale notes:</b> " + html.escape(" | ".join(m["scale_notes"])) + "</p>")
        if m["warnings"]:
            out.append("<p class=small><b>Warnings raised by the tool for this sheet:</b></p><ul class=small>"
                       + "".join(f"<li>{html.escape(w)}</li>" for w in m["warnings"]) + "</ul>")
        out.append("</section>")
    out += [f"<section class=card>{METHOD}</section>", f"<section class=card>{LIMITS}</section>",
            "<section class=card><h2>Reproduce</h2><p>From the repository root, with the sheets in <code>data/real_plans/</code>:</p>"
            "<p><code>python scripts/review_pack.py</code></p><p class=small>The set of sheets is the list at the top of "
            "<code>scripts/review_pack.py</code>, or a JSON file passed with <code>--set</code>. Metrics for every sheet are in "
            "<code>metrics.json</code> next to this page.</p></section></main>"]
    return "".join(out)


README = """# ReviewPulse evaluation pack

## What this is

ReviewPulse is a tool that reads an architectural or engineering plan and a requirements document (a building code, a brief,
a client specification), turns the requirements into rules that a person approves, and checks the plan against them.

This folder is an **evaluation pack**. It shows how well the first step, reading the plan, works on real drawings made by other
people, in different countries, units, languages and drawing styles. It does not evaluate the compliance checks themselves: a
plan that is read wrongly gives wrong compliance results, so reading has to be shown to work first.

## How to open it

Open `index.html` in any web browser. It needs no internet connection and no software. Everything it shows is in this folder.

## What is in the folder

| File | What it is |
| --- | --- |
| `index.html` | The report: introduction, how to read it, a summary table, one section per sheet, the method and the limits. |
| `metrics.json` | The same numbers as the report, per sheet, for anyone who wants to process them. |
| `<name>_page.png` | The original page of the drawing, as supplied. |
| `<name>_found.png` | What ReviewPulse found on that page: rooms with names and measured areas, doors, windows, openings. |
| `README.md` | This file. |

## How to read the results

Each sheet gets one of three verdicts, with the reasons written next to it.

- **Readable**: the scale, room sizes and doors agree with what the drawing itself prints.
- **Readable with caveats**: usable, but the listed reasons matter (for example the scale was written on the sheet and not confirmed
  by measured dimensions, or some room boundaries were inferred from room names).
- **Not usable**: the tool could not read the sheet reliably. It says so instead of guessing.

The verdicts are strict on purpose. A tool that reports a number it cannot support is worse than one that reports nothing.

## Where the evidence comes from

No answer key was written by hand. The pack compares the result with what each drawing prints about itself: the scale it states,
the dimensions it carries, and, where present, the floor area printed in each room. Sheets that print none of these are marked as
not cross-checkable.

## Glossary

- **Scale**: how many metres one unit of the drawing stands for. Without it nothing can be measured.
- **Printed area**: the area a drawing writes inside a room (for example "17.36 m2"). It is an independent check on the measured one.
- **Inferred boundary**: a room edge that is not a drawn wall, placed by dividing a space among the room names written in it.
- **OCR**: reading text that is drawn as shapes and not stored as text.

## Where the drawings come from

Each section of the report names its source. The drawings are public documents written by third parties and are used here only to
test the software. They remain the property of their owners. Do not redistribute this folder beyond the purpose of reviewing the
software.

## How to reproduce

From the root of the ReviewPulse repository, with the source PDFs in `data/real_plans/`:

    python scripts/review_pack.py

The list of sheets is at the top of `scripts/review_pack.py`, or any list can be passed as a JSON file with `--set`.
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reports/review_pack")
    ap.add_argument("--set", default=None, help="JSON file: a list of {name, pdf, pages, source}")
    ap.add_argument("--only", default="", help="comma separated substrings of the sheet names to run")
    args = ap.parse_args()
    sets = json.loads(Path(args.set).read_text(encoding="utf-8")) if args.set else DEFAULT_SET
    only = [x.strip().lower() for x in args.only.split(",") if x.strip()]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows, sources = [], {}
    for entry in sets:
        if only and not any(o in entry["name"].lower() for o in only):
            continue
        pdf = Path(entry["pdf"])
        if not pdf.exists() or pdf.stat().st_size == 0:
            print(f"skipped (file missing or empty): {pdf.name}", flush=True)
            continue
        for pg in entry["pages"]:
            key = f"{pdf.stem}_p{pg}"
            title = f"{entry['name']}, page {pg}"
            print(f"running {title} ...", flush=True)
            try:
                m = run_sheet(pdf, pg, out, key)
            except Exception as e:  # noqa: BLE001 - one bad sheet must not lose the pack
                print(f"  failed: {type(e).__name__}: {e}", flush=True)
                continue
            rows.append({"key": key, "title": title, "m": m})
            sources[key] = f"{pdf.name}, page {pg}. {entry.get('source', '')}".strip()
            print(f"  {m['verdict']}: {m['rooms']} rooms, {m['n_door']} doors, scale {m['scale_method']}, {m['seconds']} s", flush=True)
            (out / "metrics.json").write_text(json.dumps({r["key"]: r["m"] for r in rows}, indent=1), encoding="utf-8")
            (out / "index.html").write_text(page(rows, sources), encoding="utf-8")
    (out / "README.md").write_text(README, encoding="utf-8")
    print(f"\npack written: {out / 'index.html'}")


if __name__ == "__main__":
    main()
