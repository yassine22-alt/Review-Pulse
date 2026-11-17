"""Does the same requirement document give the same clauses whatever file it arrives in?

A metamorphic test: the clauses read from a reference document are written back out as the same document in other formats (plain
text, Word, Excel, csv, web page, a scan of a printed page), and each variant is read again. A clause of the reference is
recovered when a clause of the variant matches its wording (normalised, similarity at least 0.9). No label is needed: the reference
is the document itself.

  recall      share of the reference clauses found in the variant
  precision   share of the variant's clauses that are a reference clause (the others are noise or merged text)

Usage: python scripts/format_robustness.py [--docs a.md b.pdf ...] [--no-scan]
"""

from __future__ import annotations

import difflib
import os
import re
import sys
import tempfile
import warnings
from pathlib import Path

sys.path.insert(0, os.environ.get("SPLIT_SRC") or str(Path(__file__).resolve().parents[1] / "src"))
from reviewpulse.rules.clauses import BULLET_LEAD, split_document  # noqa: E402

warnings.filterwarnings("ignore")


def norm(t: str) -> str:
    t = re.sub(r"^[\s\-*•–▪●○□☐]+", "", t)
    t = re.sub(r"\(?\b[a-z0-9]{1,3}[.)]\s", "", t, count=1) if re.match(r"^\(?[a-z0-9]{1,3}[.)]\s", t) else t
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def similar(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def reference_clauses(path: Path) -> list[str]:
    _, cl = split_document(path)
    out = []
    for c in cl:
        if c.kind in ("heading", "table_header", "definition"):
            continue
        t = " ".join(c.text.split())
        if len(t) >= 25:
            out.append(t)
    return out


def write_txt(items, out: Path):
    out.write_text("\n".join("- " + t for t in items) + "\n", encoding="utf-8")


def write_txt_numbered(items, out: Path):
    out.write_text("\n\n".join(f"{i + 1}. {BULLET_LEAD.sub('', t, count=1)}" for i, t in enumerate(items)) + "\n", encoding="utf-8")


def write_docx(items, out: Path):
    import docx

    d = docx.Document()
    d.add_heading("Requirements", 1)
    for t in items:
        d.add_paragraph(t, style="List Bullet")
    d.save(str(out))


def write_xlsx(items, out: Path):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Item", "Requirement", "Reviewer note"])
    for i, t in enumerate(items, 1):
        ws.append([i, t, ""])
    wb.save(str(out))


def write_xlsx_checks(items, out: Path):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    for t in items:
        ws.append(["", t, "yes / no / n.a."])
    wb.save(str(out))


def write_csv(items, out: Path):
    import csv

    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Code", "Requirement"])
        for i, t in enumerate(items, 1):
            w.writerow([f"R{i}", t])


def write_html(items, out: Path):
    import html

    body = "".join(f"<li>{html.escape(t)}</li>" for t in items)
    out.write_text(f"<!doctype html><html><head><title>x</title><style>li{{color:red}}</style></head><body><h1>Checklist</h1>"
                   f"<ul>{body}</ul></body></html>", encoding="utf-8")


def write_scan(items, out: Path):
    """A printed page photographed: the text is drawn on a raster image (no text layer) and put into a PDF."""
    import pymupdf

    doc = pymupdf.open()
    per_page, pages = 18, []
    for k in range(0, len(items), per_page):
        page = doc.new_page(width=595, height=842)
        y = 60
        for t in items[k:k + per_page]:
            r = page.insert_textbox(pymupdf.Rect(50, y, 545, y + 120), "- " + t, fontsize=10, fontname="helv")
            lines = max(1, int(len(t) * 5.0 / 495) + 1)
            y += 14 * lines + 8
        pages.append(page)
    raster = pymupdf.open()
    for page in doc:
        pix = page.get_pixmap(dpi=300)
        p = raster.new_page(width=page.rect.width, height=page.rect.height)
        p.insert_image(p.rect, stream=pix.tobytes("png"))
    raster.save(str(out))


WRITERS = {"txt_bullets": ("txt", write_txt), "txt_numbered": ("txt", write_txt_numbered), "docx": ("docx", write_docx),
           "xlsx_table": ("xlsx", write_xlsx), "xlsx_checklist": ("xlsx", write_xlsx_checks), "csv": ("csv", write_csv),
           "html": ("html", write_html), "scan_pdf": ("pdf", write_scan)}


def score(ref: list[str], got: list[str]) -> tuple[float, float, int]:
    nref = [norm(r) for r in ref]
    ngot = [norm(g) for g in got if len(norm(g)) >= 15]
    found = sum(1 for r in nref if any(similar(r, g) >= 0.9 or (len(g) > 40 and g in r and len(g) >= 0.9 * len(r)) for g in ngot))
    good = sum(1 for g in ngot if any(similar(r, g) >= 0.9 for r in nref))
    return found / max(1, len(nref)), good / max(1, len(ngot)), len(ngot)


def main():
    args = sys.argv[1:]
    docs = [Path(a) for a in args if not a.startswith("--")] or [
        Path("data/real_docs/us_allentown_irc_checklist.md"), Path("data/real_docs/us_bloomfield_residential_checklist.pdf"),
        Path("data/real_docs/us_stpete_residential_checklist.pdf"), Path("data/real_docs/fr_caue_maisons.pdf")]
    skip = {"scan_pdf"} if "--no-scan" in args else set()
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for doc in docs:
            ref = reference_clauses(doc)
            for name, (ext, writer) in WRITERS.items():
                if name in skip:
                    continue
                f = Path(tmp) / f"{doc.stem}_{name}.{ext}"
                try:
                    writer(ref, f)
                    _, got_cl = split_document(f)
                    got = [" ".join(c.text.split()) for c in got_cl if c.kind not in ("heading", "table_header")]
                    rec, prec, n = score(ref, got)
                    rows.append((doc.name, name, len(ref), n, rec, prec))
                except Exception as exc:  # noqa: BLE001
                    rows.append((doc.name, name, len(ref), 0, 0.0, f"ERROR {type(exc).__name__}: {str(exc)[:80]}"))
    print("document | variant | reference clauses | variant clauses | recall | precision")
    for r in rows:
        print(f"{r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]:.2f} | {r[5] if isinstance(r[5], str) else format(r[5], '.2f')}")
    ok = [r for r in rows if not isinstance(r[5], str)]
    if ok:
        print(f"MEAN recall {sum(r[4] for r in ok) / len(ok):.3f}  precision {sum(r[5] for r in ok) / len(ok):.3f}  over {len(ok)} variants")


if __name__ == "__main__":
    main()
