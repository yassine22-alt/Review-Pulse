"""Audit of the sheet table reader (src/reviewpulse/schedules), with no labels.

  python scripts/sheet_tables_audit.py planted  [--cases 360] [--out file.json]   planted schedules, en/fr/de, general vs name-only baseline
  python scripts/sheet_tables_audit.py meta                                         metamorphic: a changed value, a changed unit
  python scripts/sheet_tables_audit.py real     [--pdf name.pdf ...] [--out file.json]   tables found on the real sets
  python scripts/sheet_tables_audit.py doorfire [--out file.json]                   door fire rating: old reader vs the general path

Run with PYTHONPATH=src, REVIEWPULSE_LABEL_LLM=0. No GPU and no model: headers are matched by words (REVIEWPULSE_EMBED unset).
"""

from __future__ import annotations

import argparse
import collections
import json
import random
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REAL = ROOT / "data" / "real_plans"
BASELINE_SCOPE = {"width", "height", "sill", "fire_rating", "quantity", "type"}


# ---------------------------------------------------------------------------------------------------------- scoring

def _close(a, b) -> bool:
    if isinstance(b, str):
        return isinstance(a, str) and a.strip().lower() == b
    if a is None:
        return False
    return abs(float(a) - float(b)) <= 1e-3 * max(1.0, abs(float(b)))


def general_found(tables) -> dict:
    found = {}
    for t in tables:
        for c in t.candidates:
            if c.entity_tag is None:
                continue
            v = c.value_si if c.value_si is not None and not isinstance(c.value, str) and c.meaning != "quantity" else c.value
            if c.meaning in ("quantity", "power", "voltage"):
                v = c.value
            if isinstance(v, str):
                v = v.strip().lower()
            found[(c.entity_tag, c.meaning)] = v
    return found


def baseline_found(pdf: str) -> dict:
    """The name-only reader that exists today (annotate/schedules.py: a fixed regex per header word)."""
    import pymupdf

    from reviewpulse.annotate.schedules import find_schedules
    from reviewpulse.annotate.text_classify import classify_items
    from reviewpulse.schedules.text_sheet import text_sheet

    sheet = text_sheet(pymupdf.open(pdf)[0], "b")
    classify_items(sheet.texts)
    scheds, _ = find_schedules(sheet)
    found = {}
    names = {"width_m": "width", "height_m": "height", "sill_m": "sill", "fire_rating_min": "fire_rating", "qty": "quantity",
             "type": "type"}
    for s in scheds:
        for row in s["rows"]:
            for k, m in names.items():
                if k in row:
                    v = row[k] * 60.0 if k == "fire_rating_min" else row[k]
                    found[(row["tag"], m)] = v.strip().lower() if isinstance(v, str) else v
    return found


def score(found: dict, truth: dict, scope: set | None = None) -> dict:
    tr = {(k[1], k[2]): v for k, v in truth.items() if scope is None or k[2] in scope}
    ok = sum(1 for k, v in tr.items() if k in found and _close(found[k], v))
    emitted = {k: v for k, v in found.items() if scope is None or k[1] in scope}
    right = sum(1 for k, v in emitted.items() if k in tr and _close(v, tr[k]))
    return {"truth": len(tr), "recall_ok": ok, "emitted": len(emitted), "precision_ok": right}


def pct(a: int, b: int) -> float:
    return round(100.0 * a / b, 1) if b else float("nan")


# ---------------------------------------------------------------------------------------------------------- planted

def cases(n: int, seed: int = 7):
    from reviewpulse.schedules.planted import make_table_spec

    rng = random.Random(seed)
    out = []
    for i in range(n):
        kind = rng.choice(["doors", "doors", "windows", "windows", "rooms", "finishes", "fixtures"])
        lang = rng.choice(["en", "fr", "de"])
        unit = rng.choice(["mm", "mm", "cm", "m"] + (["in"] if lang == "en" else []))
        pool = rng.choice(["vocab", "vocab", "vocab", "wild"]) if kind in ("doors", "windows") else "vocab"
        spec = make_table_spec(kind, lang, rng, n_rows=rng.randint(4, 8), unit=unit, unit_in_cell=rng.random() < 0.3 and unit != "in",
                               pool=pool, ruled=rng.random() < 0.4, size_column=kind in ("doors", "windows") and rng.random() < 0.2,
                               two_line_header=rng.random() < 0.2, drop=rng.choice([0, 0, 1]))
        out.append((i, spec))
    return out


def run_planted(n: int, out: Path | None) -> dict:
    from reviewpulse.schedules import read_pdf_tables
    from reviewpulse.schedules.planted import draw_pdf

    tmp = Path(tempfile.mkdtemp(prefix="planted_"))
    rows = []
    for i, spec in cases(n):
        p = draw_pdf(str(tmp / f"c{i}.pdf"), [spec], seed=i)
        tables = read_pdf_tables(p.path)
        g = score(general_found(tables), p.truth)
        row = {"i": i, "kind": spec["kind"], "lang": spec["lang"], "unit": spec["unit"], "pool": spec["pool"], "ruled": spec["ruled"],
               "unit_in_cell": spec["unit_in_cell"], "size_column": spec["size_column"], "two_line": spec["two_line_header"],
               "n_tables": len(tables), "general": g}
        if spec["kind"] in ("doors", "windows") and spec["lang"] in ("en", "fr", "de"):
            b = score(baseline_found(p.path), p.truth, BASELINE_SCOPE)
            g2 = score(general_found(tables), p.truth, BASELINE_SCOPE)
            row["baseline"], row["general_scope"] = b, g2
        rows.append(row)
    summary = summarise_planted(rows)
    if out:
        out.write_text(json.dumps({"summary": summary, "rows": rows}, indent=1, ensure_ascii=False), encoding="utf-8")
    return summary


def _agg(rows, key="general"):
    t = sum(r[key]["truth"] for r in rows if key in r)
    ok = sum(r[key]["recall_ok"] for r in rows if key in r)
    em = sum(r[key]["emitted"] for r in rows if key in r)
    pr = sum(r[key]["precision_ok"] for r in rows if key in r)
    return {"cases": sum(1 for r in rows if key in r), "truth": t, "recall%": pct(ok, t), "emitted": em, "precision%": pct(pr, em)}


def summarise_planted(rows) -> dict:
    s = {"all_general": _agg(rows)}
    for field in ("kind", "lang", "unit", "pool", "ruled", "unit_in_cell", "size_column", "two_line"):
        for v in sorted({r[field] for r in rows}, key=str):
            s[f"{field}={v}"] = _agg([r for r in rows if r[field] == v])
    door_win = [r for r in rows if "baseline" in r]
    s["doors_windows_baseline"] = _agg(door_win, "baseline")
    s["doors_windows_general_same_scope"] = _agg(door_win, "general_scope")
    for pool in ("vocab", "wild"):
        sub = [r for r in door_win if r["pool"] == pool]
        s[f"doors_windows_{pool}_baseline"] = _agg(sub, "baseline")
        s[f"doors_windows_{pool}_general"] = _agg(sub, "general_scope")
    return s


# ---------------------------------------------------------------------------------------------------------- metamorphic

def run_meta(n: int = 120) -> dict:
    """Change one cell, or one header unit, in the words of a planted schedule: the candidates must change as they should."""
    import copy

    import pymupdf

    from reviewpulse.interpreter.units import convert
    from reviewpulse.schedules.planted import draw_pdf
    from reviewpulse.schedules.reader import read_tables, words_from_page

    tmp = Path(tempfile.mkdtemp(prefix="meta_"))
    res = collections.Counter()
    for i, spec in cases(n, seed=11):
        if spec["kind"] not in ("doors", "windows") or spec["unit"] == "in" or spec["size_column"] or spec["unit_in_cell"]:
            continue
        p = draw_pdf(str(tmp / f"m{i}.pdf"), [spec], seed=i)
        page = pymupdf.open(p.path)[0]
        words = words_from_page(page)
        base = read_tables(words, "s")
        cand0 = {(c.entity_tag, c.meaning): c for t in base for c in t.candidates}
        # 1. change one value of the width column
        wcol = next((c for t in base for c in t.columns if c.meaning == "width"), None)
        wc = [c for c in cand0.values() if c.meaning == "width"]
        if wcol and wc:
            target = wc[len(wc) // 2]
            w2 = copy.deepcopy(words)
            hdr_x = (wcol.x0 + wcol.x1) / 2
            hit = sorted((w for w in w2 if w.text == target.cell_text), key=lambda w: abs((w.x0 + w.x1) / 2 - hdr_x))
            if hit:
                newv = "777"
                hit[0].text = newv
                alt = {(c.entity_tag, c.meaning): c for t in read_tables(w2, "s") for c in t.candidates}
                changed = [k for k in cand0 if k in alt and cand0[k].cell_text != alt[k].cell_text]
                ok = (len(changed) == 1 and alt[changed[0]].value == 777.0) or target.cell_text == "777"
                res["value_change_total"] += 1
                res["value_change_ok"] += int(ok)
        # 2. change the unit in the header: (mm) -> (cm): every value in the column converts differently
        w3 = copy.deepcopy(words)
        n_edit = 0
        for w in w3:
            if w.text.strip("()") == spec["unit"] and w.text.startswith("("):
                w.text = "(cm)" if spec["unit"] != "cm" else "(mm)"
                n_edit += 1
        if n_edit:
            alt = {(c.entity_tag, c.meaning): c for t in read_tables(w3, "s") for c in t.candidates}
            new_unit = "cm" if spec["unit"] != "cm" else "mm"
            for m in ("width", "height", "sill"):
                keys = [k for k in cand0 if k[1] == m and k in alt]
                if not keys:
                    continue
                good = 0
                for k in keys:
                    a, b = cand0[k], alt[k]
                    want = convert(a.value, new_unit, "m")
                    good += int(b.unit == new_unit and a.value == b.value and abs(b.value_si - want) < 1e-9)
                res["unit_change_total"] += len(keys)
                res["unit_change_ok"] += good
    return dict(res)


# ---------------------------------------------------------------------------------------------------------- real

def run_real(names: list[str] | None, out: Path | None, cap_s: float = 90.0) -> dict:
    import pymupdf

    from reviewpulse.schedules.reader import read_page_tables

    files = [REAL / n for n in names] if names else sorted(REAL.glob("*.pdf"))
    report = {}
    for f in files:
        if not f.exists() or f.stat().st_size == 0:
            continue
        doc = pymupdf.open(f)
        stats = collections.Counter()
        kinds = collections.Counter()
        tables_out = []
        slow = []
        t_file = time.time()
        for pi in range(len(doc)):
            t0 = time.time()
            try:
                tabs = read_page_tables(doc[pi], f"p{pi + 1}")
            except Exception as e:  # noqa: BLE001
                stats["page_errors"] += 1
                tabs = []
                slow.append((pi + 1, f"error {type(e).__name__}"))
            if time.time() - t0 > cap_s:
                slow.append((pi + 1, round(time.time() - t0, 1)))
            stats["pages"] += 1
            for t in tabs:
                stats["tables"] += 1
                stats["tables_" + t.method] += 1
                stats["rows"] += len(t.rows)
                stats["columns"] += len(t.columns)
                stats["columns_typed"] += t.n_typed
                stats["columns_with_unit"] += t.n_with_unit
                stats["candidates"] += len(t.candidates)
                kinds[t.kind] += 1
                tables_out.append({"id": t.id, "page": pi + 1, "kind": t.kind, "why": t.kind_source, "title": t.title, "method": t.method,
                                   "columns": [(c.header, c.meaning, c.via, c.unit, c.unit_source) for c in t.columns],
                                   "rows": t.rows[:4], "n_rows": len(t.rows),
                                   "cands": [(c.entity_tag, c.meaning, c.value, c.unit, c.cell_text) for c in t.candidates[:6]]})
        stats["pages_with_tables"] = len({t["page"] for t in tables_out})
        report[f.name] = {"stats": dict(stats), "kinds": dict(kinds), "seconds": round(time.time() - t_file, 1), "slow_pages": slow,
                          "tables": tables_out}
        print(f.name, dict(stats), dict(kinds), round(time.time() - t_file, 1), "s", flush=True)
    if out:
        out.write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    return report


# ---------------------------------------------------------------------------------------------------------- door fire

def run_doorfire(n: int, out: Path | None) -> dict:
    """The door fire rating by the old reader (find_schedules) and by the general path, on planted door schedules whose headers
    the old reader knows (English, French, German vocabulary pool) and on the pages of the real sets."""
    import pymupdf

    from reviewpulse.annotate.schedules import find_schedules
    from reviewpulse.annotate.text_classify import classify_items
    from reviewpulse.schedules import door_fire_rows, read_page_tables, read_pdf_tables
    from reviewpulse.schedules.planted import draw_pdf, make_table_spec
    from reviewpulse.schedules.text_sheet import text_sheet

    rng = random.Random(5)
    tmp = Path(tempfile.mkdtemp(prefix="fire_"))
    res = collections.Counter()
    for i in range(n):
        lang = rng.choice(["en", "fr", "de"])
        spec = make_table_spec("doors", lang, rng, n_rows=rng.randint(4, 8), unit=rng.choice(["mm", "cm"]), ruled=False)
        p = draw_pdf(str(tmp / f"f{i}.pdf"), [spec], seed=i)
        sheet = text_sheet(pymupdf.open(p.path)[0], "o")
        classify_items(sheet.texts)
        old = {r["tag"]: r["fire_rating_min"] for s in find_schedules(sheet)[0] for r in s["rows"] if "fire_rating_min" in r}
        new = door_fire_rows(read_pdf_tables(p.path))
        truth = {k[1]: v / 60.0 for k, v in p.truth.items() if k[2] == "fire_rating"}
        res["planted_tables"] += 1
        res["planted_truth"] += len(truth)
        res["old_right"] += sum(1 for k, v in old.items() if k in truth and abs(truth[k] - v) < 1e-6)
        res["old_wrong"] += sum(1 for k, v in old.items() if not (k in truth and abs(truth[k] - v) < 1e-6))
        res["new_right"] += sum(1 for k, v in new.items() if k in truth and abs(truth[k] - v) < 1e-6)
        res["new_wrong"] += sum(1 for k, v in new.items() if not (k in truth and abs(truth[k] - v) < 1e-6))
        res["old_right_lost_by_new"] += sum(1 for k, v in old.items() if k in truth and abs(truth[k] - v) < 1e-6
                                            and not (k in new and abs(new[k] - v) < 1e-6))
    real = collections.Counter()
    detail = []
    for f in sorted(REAL.glob("*.pdf")):
        if f.stat().st_size == 0:
            continue
        doc = pymupdf.open(f)
        for pi in range(len(doc)):
            page = doc[pi]
            txt = page.get_text().lower()
            if "fire" not in txt and "rating" not in txt:
                continue
            sheet = text_sheet(page, "o")
            classify_items(sheet.texts)
            old = {r["tag"]: r["fire_rating_min"] for s in find_schedules(sheet)[0] for r in s["rows"] if "fire_rating_min" in r}
            new = door_fire_rows(read_page_tables(page, "n"))
            real["pages_checked"] += 1
            real["old_rows"] += len(old)
            real["new_rows"] += len(new)
            real["same"] += sum(1 for k, v in old.items() if k in new and abs(new[k] - v) < 1e-6)
            real["old_only"] += sum(1 for k in old if k not in new)
            real["new_only"] += sum(1 for k in new if k not in old)
            real["differ"] += sum(1 for k, v in old.items() if k in new and abs(new[k] - v) >= 1e-6)
            if old or new:
                detail.append({"file": f.name, "page": pi + 1, "old": old, "new": new})
    result = {"planted": dict(res), "real": dict(real), "detail": detail}
    if out:
        out.write_text(json.dumps(result, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    return result


def main() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["planted", "meta", "real", "doorfire"])
    ap.add_argument("--cases", type=int, default=360)
    ap.add_argument("--pdf", nargs="*")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    if a.mode == "planted":
        res = run_planted(a.cases, a.out)
    elif a.mode == "meta":
        res = run_meta(a.cases)
    elif a.mode == "real":
        res = {k: {"stats": v["stats"], "kinds": v["kinds"]} for k, v in run_real(a.pdf, a.out).items()}
    else:
        r = run_doorfire(a.cases, a.out)
        res = {"planted": r["planted"], "real": r["real"]}
    print(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
