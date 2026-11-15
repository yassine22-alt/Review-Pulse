"""Run every page of real plan PDFs through the product's plan analysis and record what it found and what it did not.

    python scripts/real_plan_study.py <plans.pdf ...> [--max-pages 12] [--out reports/real_plans]

Real drawings are not all floor plans (sheets of notes, sections, site plans, schedules) and the product must say so rather
than invent rooms. For each page this records: whether the analysis ran, how long it took, what it found (rooms, doors,
windows, stairs, text labels), whether the page was recognised as a plan, the scale, the product's own completeness
statement, and the error when it failed. A page render is saved next to the record so a person can check by eye.
Nothing here is tuned to a document; the real drawings are never committed (data/real_plans/ is ignored).
"""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path

import pymupdf
from fastapi.testclient import TestClient

from reviewpulse.app.api import create_app


def wait(c, pid, job, limit=600):
    t0 = time.time()
    while time.time() - t0 < limit:
        rec = c.get(f"/api/projects/{pid}/jobs/{job['id']}").json()
        if rec["status"] in ("done", "failed"):
            return rec
        time.sleep(0.5)
    return {"status": "timeout"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdfs", nargs="+")
    ap.add_argument("--max-pages", type=int, default=12)
    ap.add_argument("--out", default="reports/real_plans")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    with tempfile.TemporaryDirectory() as tmp, TestClient(create_app(Path(tmp) / "data", llm=lambda: None, workers=1)) as c:
        for pdf in map(Path, args.pdfs):
            doc = pymupdf.open(pdf)
            pages = list(range(min(len(doc), args.max_pages)))
            for n in pages:
                single = Path(tmp) / f"{pdf.stem}_p{n + 1}.pdf"
                one = pymupdf.open()
                one.insert_pdf(doc, from_page=n, to_page=n)
                one.save(single)
                pix = doc[n].get_pixmap(dpi=60)
                pix.save(out / f"{pdf.stem}_p{n + 1}.png")
                pid = c.post("/api/projects", json={"name": single.stem}).json()["id"]
                t0 = time.time()
                row = {"file": pdf.name, "page": n + 1, "drawings": len(doc[n].get_drawings()),
                       "images": len(doc[n].get_images()), "chars": len(doc[n].get_text())}
                try:
                    with open(single, "rb") as f:
                        job = c.post(f"/api/projects/{pid}/plan", files={"file": (single.name, f)}).json()
                    rec = wait(c, pid, job)
                    row["status"] = rec["status"]
                    row["error"] = (rec.get("error") or "")[:300] if rec["status"] != "done" else None
                    if rec["status"] == "done":
                        row["result"] = rec.get("result")
                        row["triage"] = c.get(f"/api/projects/{pid}/view").json().get("triage")
                        files = sorted(c.app.state.store.run_dir(pid).glob("building_*.json"))
                        if files:                          # what the plan reader found, by kind
                            model = json.loads(files[0].read_text(encoding="utf-8"))
                            row["found"] = {k: len(v) for k, v in model.items() if isinstance(v, list) and v}
                except Exception as e:  # noqa: BLE001 - the study records every failure
                    row["status"], row["error"] = "crashed", f"{type(e).__name__}: {e}"[:300]
                row["seconds"] = round(time.time() - t0, 1)
                rows.append(row)
                print(f"{pdf.name[:28]:<28} p{n + 1:<3} {row['status']:<8} {row['seconds']:>6}s  "
                      f"{(row.get('error') or '')[:80]}", flush=True)
    (out / "results.json").write_text(json.dumps(rows, indent=1, default=str), encoding="utf-8")
    ok = sum(r["status"] == "done" for r in rows)
    print(f"\n{ok} of {len(rows)} pages analysed without failing; details in {out / 'results.json'}")


if __name__ == "__main__":
    main()
