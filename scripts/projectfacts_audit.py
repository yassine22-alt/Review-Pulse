"""Audit of the project facts reader, no labels.

    python scripts/projectfacts_audit.py real [--dir data/real_plans]     every field found, with its source, to be read by a person
    python scripts/projectfacts_audit.py planted [--n 40]                 generated cover sheets: recall, precision, metamorphic
    python scripts/projectfacts_audit.py checklist                        conditional checklist lines against what the real sets state

Run with PYTHONPATH=src PYTHONIOENCODING=utf-8 REVIEWPULSE_LABEL_LLM=0. Words only unless REVIEWPULSE_EMBED is on and bge-m3 is
served (never run here without a GPU decision). Pages are read for their text only, so a large drawing is fast.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from reviewpulse.drawingset.pagedata import Line, PageData, canonicalize  # noqa: E402
from reviewpulse.projectfacts import default_embedder, load_spec, read_project_facts  # noqa: E402
from reviewpulse.projectfacts.planted import LEVELS, make_cover  # noqa: E402


def text_pages(path: Path) -> list[PageData]:
    """The text lines of every page (as `from_pdf` reads them), without the vector drawing."""
    import pymupdf

    doc = pymupdf.open(str(path))
    out = []
    for pno, page in enumerate(doc):
        m = page.rotation_matrix
        pg = PageData(pno, page.rect.width, page.rect.height)
        for b in page.get_text("dict")["blocks"]:
            if b.get("type") != 0:
                continue
            for ln in b["lines"]:
                txt = "".join(s["text"] for s in ln["spans"]).strip()
                if not txt:
                    continue
                r = pymupdf.Rect(ln["bbox"]) * m
                d = pymupdf.Point(ln["dir"]) * pymupdf.Matrix(m.a, m.b, m.c, m.d, 0, 0)
                pg.lines.append(Line(txt, r.x0, r.y0, r.x1, r.y1, max(s["size"] for s in ln["spans"]), round(d.x, 3), round(d.y, 3)))
        pg.has_text_layer = bool(pg.lines)
        out.append(canonicalize(pg))
    return out


def run_real(args) -> dict:
    res = {}
    for f in sorted(Path(args.dir).glob("*.pdf")):
        t0 = time.time()
        try:
            pages = text_pages(f)
        except Exception as exc:  # noqa: BLE001 - an empty or broken file is reported, not hidden
            print(f"== {f.name}: cannot open ({type(exc).__name__})")
            res[f.name] = {"error": type(exc).__name__}
            continue
        pf = read_project_facts(pages, embedder=default_embedder())
        found = [c for c in pf.candidates if c.value is not None]
        stated_unknown = [c for c in pf.candidates if c.value is None and c.score > 0]
        print(f"== {f.name}: {len(pages)} sheets, {sum(len(p.lines) for p in pages)} lines, arm {pf.arm}, {time.time() - t0:.1f}s")
        for c in found:
            print(f"   FOUND   {c.fact:20s} {c.entity:14s} {c.value!r:34} {c.unit:3s} score {c.score:.2f} | {c.source[:130]}")
        for c in stated_unknown:
            print(f"   UNSTATED {c.fact:19s} | {c.source[:150]}")
        print(f"   unknown ({len(pf.unknown)}): {', '.join(sorted(pf.unknown))}")
        if args.derive and f.stat().st_size < 5_000_000:
            from reviewpulse.drawingset import build_from_pdf
            from reviewpulse.projectfacts import storeys_from_plans

            ds = build_from_pdf(f)
            sc = storeys_from_plans(ds)
            print("   DERIVED " + (f"number_of_storeys {sc.value} | {sc.source[:140]}" if sc else "number_of_storeys: no plan view sits on a level"))
        res[f.name] = {"found": [{"fact": c.fact, "entity": c.entity, "value": c.value, "unit": c.unit, "score": c.score, "source": c.source}
                                for c in found], "unstated": [c.fact for c in stated_unknown], "unknown": sorted(pf.unknown),
                       "sheets": len(pages)}
    return res


GOOD_BOOL = {True, False}


def score_page(pf, truth, drop=()):
    """(correct, wrong, missed) for the building fields and the level areas of a planted page."""
    got = {}
    for c in pf.candidates:
        if c.value is not None and c.entity == "building":
            got[c.fact] = c.value
    ok = bad = miss = 0
    for k, v in truth.values.items():
        if k in drop:
            continue
        if k not in got:
            miss += 1
        elif (abs(got[k] - v) <= 0.006 * abs(v) if isinstance(v, float) else got[k] == v):
            ok += 1
        else:
            bad += 1
    extra = [k for k in got if k not in truth.values and k not in drop]
    lv = {c.entity: c.value for c in pf.candidates if c.fact == "floor_area" and c.value is not None}
    return ok, bad, miss, len(extra), lv


def run_planted(args) -> dict:
    out = {}
    emb = default_embedder()
    for arm, embedder in (("words", None),) + ((("words+embedding", emb),) if emb is not None else ()):
        tot = Counter()
        by_lang = {}
        for lang in ("en", "fr", "de"):
            c = Counter()
            for layout in ("colon", "cells", "stacked"):
                for ruled in (False, True):
                    for unit_in in ("cell", "header"):
                        for imperial in (False, True) if lang == "en" else (False,):
                            for seed in range(args.n):
                                pg, truth = make_cover(lang, layout=layout, ruled=ruled, unit_in=unit_in, imperial=imperial, seed=seed,
                                                       storeys=1 + seed % 4, sprinklered=bool(seed % 2),
                                                       use="office" if seed % 3 == 0 else "single_family_dwelling",
                                                       construction="masonry" if seed % 5 == 0 else "wood_frame",
                                                       height_m=6.0 + seed % 7, area_m2=100.0 + 10 * seed)
                                pf = read_project_facts([pg], embedder=embedder)
                                ok, bad, miss, extra, lv = score_page(pf, truth)
                                c["ok"] += ok
                                c["wrong"] += bad
                                c["missed"] += miss
                                c["extra"] += extra
                                c["pages"] += 1
                                names = LEVELS[lang]
                                want = {f"level:{n}": a for n, a in zip(names, (95.0, 80.0, 15.0), strict=True)}
                                c["level_total"] += 3
                                c["level_ok"] += sum(1 for v in lv.values() if any(abs(v - w) <= 0.006 * w for w in want.values()))
                                c["level_extra"] += max(0, len(lv) - 3)
            by_lang[lang] = dict(c)
            tot.update(c)
        planted = tot["ok"] + tot["wrong"] + tot["missed"]
        out[arm] = {"by_language": by_lang, "recall": tot["ok"] / planted, "precision": tot["ok"] / max(1, tot["ok"] + tot["wrong"] + tot["extra"]),
                    "level_recall": tot["level_ok"] / tot["level_total"], "total": dict(tot)}
        print(f"[{arm}] pages {tot['pages']}  recall {out[arm]['recall']:.4f}  precision {out[arm]['precision']:.4f}  "
              f"level areas {out[arm]['level_recall']:.4f}  wrong {tot['wrong']} extra {tot['extra']} missed {tot['missed']}")
        for lang, c in by_lang.items():
            print(f"   {lang}: ok {c['ok']} wrong {c['wrong']} missed {c['missed']} extra {c['extra']} levels {c['level_ok']}/{c['level_total']}")
    # metamorphic: change the stated storeys or sprinkler value, the output must change (and nothing else may)
    n = fail = 0
    for lang in ("en", "fr", "de"):
        for layout in ("colon", "cells", "stacked"):
            for seed in range(args.n):
                base = dict(layout=layout, seed=seed, storeys=2, sprinklered=False)
                a = read_project_facts([make_cover(lang, **base)[0]]).stated()
                for key, alt in (("storeys", 3), ("sprinklered", True)):
                    b = read_project_facts([make_cover(lang, **{**base, key: alt})[0]]).stated()
                    n += 1
                    name = "number_of_storeys" if key == "storeys" else "sprinklered"
                    changed = {k for k in set(a) | set(b) if a.get(k) != b.get(k)}
                    if changed != {name}:
                        fail += 1
    out["metamorphic"] = {"cases": n, "failed": fail}
    print(f"metamorphic: {n} cases, {fail} failed")
    # labels the cue lists do not hold: the words arm cannot read them, which is what the embedding arm is for
    held = [("Levels above grade", "3", "number_of_storeys", 3), ("Storeys above ground", "3", "number_of_storeys", 3),
            ("Fire suppression system", "Yes", "sprinklered", True), ("Automatic fire extinguishing", "No", "sprinklered", False),
            ("Intended occupancy of premises", "Office", "building_class", "office"), ("Structural system", "Masonry", "construction_type", "masonry"),
            ("Anzahl der Stockwerke", "2", "number_of_storeys", 2), ("Niveaux hors sol", "2", "number_of_storeys", 2),
            ("Eaves to ridge height", "9.5 m", "building_height", 9.5), ("Floor space in total", "210 m2", "gross_floor_area", 210.0),
            ("Governing regulations", "2018 IBC", "code_edition", "2018 IBC"), ("Authority", "City of Springfield", "jurisdiction", "City of Springfield")]
    hits = {}
    for arm, embedder in (("words", None),) + ((("words+embedding", emb),) if emb is not None else ()):
        n_ok = 0
        for lab, val, fld, want in held:
            pg = PageData(0, 1000.0, 800.0)
            s = f"{lab}: {val}"
            pg.lines.append(Line(s, 50, 100, 50 + 7 * len(s), 110, 10))
            got = read_project_facts([pg], embedder=embedder).stated().get(fld)
            n_ok += got == want or (isinstance(want, float) and isinstance(got, float) and abs(got - want) < 0.02)
        hits[arm] = f"{n_ok}/{len(held)}"
    out["held_out_labels"] = hits
    print(f"held-out labels read (not in the cue lists): {hits}")
    # sheets that state nothing but carry the cue words inside sentences: every field must stay unknown
    notes = ["ALL WORK SHALL BE DONE IN ACCORDANCE WITH INTERNATIONAL BUILDING CODES AND LOCAL CODES", "INSTALL SPRINKLER HEADS PER MANUFACTURER",
             "AREA SHALL BE 1 3/4 INCH TIGHT FITTING SOLID CORE DOOR", "PROVIDE A FIRE ALARM WHERE REQUIRED BY CODE", "Use of this drawing without consent is prohibited",
             "Die Gemeinde prueft den Antrag", "Les etages sont reportes sur le plan", "Number of stories to be confirmed by the owner in writing before permit"]
    spurious = 0
    for _k in range(args.n):
        pg = PageData(0, 1200.0, 900.0)
        for i, s in enumerate(notes):
            pg.lines.append(Line(s, 60, 100 + 30 * i, 60 + 7 * len(s), 110 + 30 * i, 10))
        spurious += sum(1 for c in read_project_facts([pg]).candidates if c.value is not None)
    out["silent"] = {"values_read_on_sentence_only_sheets": spurious}
    print(f"sentence-only sheets: {spurious} values read")
    return out


def run_checklist(args) -> dict:
    sys.path.insert(0, str(ROOT / "scripts"))
    from reviewpulse.rules.clauses import split_document

    labels = json.loads((ROOT / "benchmarks" / "checklist_labels.json").read_text(encoding="utf-8"))
    spec = load_spec()
    # which project fact a clause's condition words point to: the cue words of the field file and a few trigger words of a condition
    triggers = {"sprinklered": ["sprinkler"], "number_of_storeys": ["stories", "storeys", "story", "storey", "floors", "basement"],
                "building_class": ["townhouse", "town house", "dwelling unit", "one- and two-family", "occupancy", "group r", "apartment", "residential"],
                "building_height": ["height of the building", "building height"], "work_type": ["new construction", "addition", "alteration", "existing"],
                "code_edition": ["code edition", "irc", "ibc", "per code", "adopted"], "occupant_load": ["occupant"]}
    cond = re.compile(r"\b(if|where|when|unless|whenever|provided that|in case|for)\b|\b(wenn|sofern|falls|si |lorsque|quand)\b", re.I)
    rows = []
    for doc, items in labels.items():
        path = ROOT / "data" / "real_docs" / doc
        if not path.exists():
            continue
        _, clauses = split_document(path)
        by_id = {c.id: c for c in clauses}
        default = items.get("_default")
        for cid, spec_item in items.items():
            if cid == "_default":
                continue
            cl = by_id.get(cid)
            if cl is None:
                continue
            lab = spec_item.get("label")
            rows.append((doc, cid, lab, cl.text))
        if default:
            for cl in clauses:
                if cl.kind != "heading" and cl.id not in items:
                    rows.append((doc, cl.id, default.get("label"), cl.text))
    sel = []
    for doc, cid, lab, text in rows:
        low = text.lower()
        fields = [k for k, ws in triggers.items() if any(w in low for w in ws)]
        needs = lab == "needs_fact"
        conditional = bool(cond.search(text)) and bool(fields)
        if needs or conditional:
            sel.append({"doc": doc, "id": cid, "label": lab, "conditional_on": fields, "text": text[:240].replace("\n", " ")})
    print(f"needs_fact lines: {sum(1 for s in sel if s['label'] == 'needs_fact')}; lines with a condition word and a project field word: "
          f"{sum(1 for s in sel if s['conditional_on'])}")
    cnt = Counter(f for s in sel for f in s["conditional_on"])
    print("project fields the conditions point to:", dict(cnt))
    for s in sel:
        if s["conditional_on"]:
            print(f"   {s['doc'][:18]:18s} {s['id']:12s} [{s['label']}] -> {s['conditional_on']} | {s['text'][:170]}")
    return {"selected": sel, "fields": dict(cnt), "spec_fields": list(spec.fields)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["real", "planted", "checklist"])
    ap.add_argument("--dir", default=str(ROOT / "data" / "real_plans"))
    ap.add_argument("--derive", action="store_true", help="also build the drawing set and count the levels of its plan views")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    res = {"real": run_real, "planted": run_planted, "checklist": run_checklist}[a.mode](a)
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
