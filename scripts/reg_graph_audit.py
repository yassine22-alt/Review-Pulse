"""Audit of the regulation graph (src/reviewpulse/regs), without any label on the real documents.

    python scripts/reg_graph_audit.py [data/real_docs] [--out reports/reg_graph] [--sample 60] [--seed 7]

Parts
  real       per document: nodes, edges by type, how many references resolve (exactly, approximately, to another document, not at all),
             the same references counted by the splitter audit and by the table reference audit, a simpler baseline (regex on
             "Section N" only), exceptions found by kind, defined terms and how many clauses use them
  synthetic  documents in English, French, German and Spanish with a known structure: precision and recall per edge type, the
             graph against the baseline, two wordings (the second chosen before the cue file was checked against it)
  meta       the same structure written with other numbers and in another order, and a real text with its numbers shifted: the
             edges must follow
  sample     a random sample of edges with their words, to be read by hand (the grades are written in docs/progress/M19)

The split of each real document comes from the split cache (the splitter is not run again when the cache holds it).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import random
import re
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from reviewpulse.regs import build_graph, load_cues, resolve_context  # noqa: E402
from reviewpulse.regs import synthetic as S  # noqa: E402
from reviewpulse.rules.clauses import split_cached, split_text  # noqa: E402

REF_STATUS_OK = ("resolved",)
REF_STATUS_APPROX = ("first_of_many", "partial", "group", "anchor")
CACHE_DEFAULT = "reports/m14_split_cache2"


# ------------------------------------------------------------------------------------------------------------- baseline
SECTION_ONLY = re.compile(r"\bSection\s+(\d+(?:\.\d+)*)\b")


def baseline_section_refs(full: str, clauses: list) -> tuple[int, int, set[tuple[str, str]]]:
    """The simpler method: regex on "Section N" only, resolved when some clause id or first number equals N."""
    labels: dict[str, str] = {}
    for c in clauses:
        labels.setdefault(c.id.lower(), c.id)
        m = re.match(r"\s*(\d+(?:\.\d+)*)[.)\s\t]", c.text)
        if m:
            labels.setdefault(m.group(1), c.id)
    n = ok = 0
    pairs: set[tuple[str, str]] = set()
    for c in clauses:
        for m in SECTION_ONLY.finditer(c.text):
            n += 1
            tgt = labels.get(m.group(1))
            if tgt and tgt != c.id:
                ok += 1
                pairs.add((c.id, tgt))
    return n, ok, pairs


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------------------------------------------------- real documents
def real_doc(path: Path, cache: Path, split_audit) -> tuple[dict, object]:
    full, clauses = split_cached(path, cache / path.stem)
    t0 = time.time()
    g = build_graph(full, clauses)
    secs = time.time() - t0
    refs = [e for e in g.edges if e.origin == "ref"]
    by_status = Counter(e.status for e in refs)
    exact, approx = by_status["resolved"], sum(by_status[s] for s in REF_STATUS_APPROX)
    unres, ext = by_status["unresolved"], by_status["external"]
    in_doc = exact + approx + unres
    tab = [e for e in refs if e.type == "table_of"]
    tab_ok = [e for e in tab if e.provider and g.nodes[e.provider].ntype == "table"]
    exc = Counter()
    for e in g.edges:
        if e.type == "exception_of" and e.provider:
            exc["referenced (cue + cited clause)" if e.origin == "ref" else
                "clause or paragraph that begins 'Exception'" if g.nodes[e.provider].clause == e.consumer and e.reason.startswith("paragraph")
                else "clause that begins 'Exception' (attached to the one before)" if e.reason.startswith("clause begins")
                else "same sentence (cue word, no citation)"] += 1
    terms = g.terms
    term_edges = [e for e in g.edges if e.origin == "term"]
    used = {e.provider for e in term_edges}
    def_nodes = [n for ns in terms.values() for n in ns]
    consumers = {e.consumer for e in term_edges}
    body = [c for c in clauses if c.kind not in ("table_row", "table_header")]
    cited_defs = [e for e in refs if e.type == "definition_of"]
    out = {
        "doc": path.name, "clauses": len(clauses), "nodes": len(g.nodes), "seconds": round(secs, 2),
        "edges": g.stats(), "references": len(refs), "exact": exact, "approx": approx, "approx_by": {s: by_status[s] for s in REF_STATUS_APPROX},
        "unresolved": unres, "external": ext, "resolution_in_document": round((exact + approx) / in_doc, 3) if in_doc else None,
        "resolution_exact_only": round(exact / in_doc, 3) if in_doc else None,
        "tables_cited": len(tab), "tables_cited_resolved_to_table": len(tab_ok),
        "exceptions": dict(exc), "terms": len(def_nodes), "terms_used": len(used), "clauses_using_a_term": len(consumers),
        "body_clauses": len(body), "defined_in_refs": len(cited_defs),
        "defined_in_refs_resolved": sum(1 for e in cited_defs if e.provider),
    }
    # the audits that already exist, on the same cached split (the table reference audit takes minutes on a long document:
    # its answer is kept next to the report and reused while the document and the split are the same)
    key = f"{path.name}:{len(full)}:{len(clauses)}"
    memo_file = Path(os.environ.get("REG_GRAPH_MEMO", "reports/reg_graph/compare_cache.json"))
    memo = json.loads(memo_file.read_text(encoding="utf-8")) if memo_file.is_file() else {}
    if key in memo:
        out.update(memo[key])
        compared = True
    else:
        compared = False
    if split_audit is not None and not compared:
        try:
            a = split_audit.audit(path, cache)
            out["split_audit_refs"], out["split_audit_resolved"] = a["refs"], a["refs_resolved"]
        except Exception as ex:                                           # noqa: BLE001
            out["split_audit_error"] = repr(ex)
    if not compared:
        out.update(compare_with_table_refs(path, full, clauses))
        memo[key] = {k: out[k] for k in ("split_audit_refs", "split_audit_resolved", "table_refs_audit", "table_refs_audit_resolved") if k in out}
        memo_file.parent.mkdir(parents=True, exist_ok=True)
        memo_file.write_text(json.dumps(memo, indent=1), encoding="utf-8")
    out.update(overlap_with_existing(full, clauses, g, split_audit))
    n, ok, _ = baseline_section_refs(full, clauses)
    out["baseline_section_refs"], out["baseline_section_resolved"] = n, ok
    out["_unresolved_list"] = [(e.consumer, e.quote[:60], e.reason[:80], full[max(0, e.start - 60):e.end + 40].replace("\n", " "))
                               for e in refs if e.status == "unresolved"]
    out["_external_list"] = [(e.consumer, e.quote[:40], e.reason[:60]) for e in refs if e.status == "external"][:15]
    return out, g


def overlap_with_existing(full: str, clauses: list, g, split_audit) -> dict:
    """The references the two earlier audits counted, looked up in the graph: how many does it also find, and how many of those resolve."""
    out: dict = {}
    by_clause: dict[str, list] = {}
    for e in g.edges:
        if e.origin == "ref" and e.evidence_clause:
            by_clause.setdefault(e.evidence_clause, []).append(e)
    if split_audit is not None and hasattr(split_audit, "REF"):
        n = found = resolved = 0
        for c in clauses:
            if c.kind in ("heading", "table_row", "table_header"):
                continue
            for m in split_audit.REF.finditer(c.text):
                n += 1
                a, b = c.start + m.start(1), c.start + m.end(1)
                hit = [e for e in by_clause.get(c.id, []) if e.start < b and e.end > a]
                found += bool(hit)
                resolved += any(e.provider for e in hit)
        out["split_audit_refs_in_graph"], out["split_audit_refs_resolved_in_graph"] = found, resolved
        out["split_audit_refs_checked"] = n
    try:
        from reviewpulse.interpreter.context import REFERENCE, TABLE_WORDS
        n = found = resolved = 0
        for c in clauses:
            if c.kind in ("table_header", "table_row"):
                continue
            for m in REFERENCE.finditer(c.text):
                if m.group(1).lower() not in TABLE_WORDS:
                    continue
                n += 1
                a, b = c.start + m.start(), c.start + m.end()
                hit = [e for e in by_clause.get(c.id, []) if e.start < b and e.end > a and e.type == "table_of"]
                found += bool(hit)
                resolved += any(e.provider and g.nodes[e.provider].ntype == "table" for e in hit)
        out["table_refs_in_graph"], out["table_refs_resolved_to_table_in_graph"], out["table_refs_checked"] = found, resolved, n
    except Exception as ex:                                               # noqa: BLE001
        out["table_overlap_error"] = repr(ex)[:100]
    return out


def compare_with_table_refs(path: Path, full: str, clauses: list) -> dict:
    """The count of table_refs.py (references to a table that reach the table through assemble_context), on the cached split."""
    out: dict = {}
    try:
        from reviewpulse.interpreter.context import REFERENCE, TABLE_WORDS, assemble_context
        n = ok = 0
        ids = {c.id for c in clauses}
        for c in clauses:
            if c.kind in ("table_header", "table_row"):
                continue
            targets = {f"Table {m.group(2)}" for m in REFERENCE.finditer(c.text) if m.group(1).lower() in TABLE_WORDS}
            if not targets:
                continue
            got = {x.id for x in assemble_context(path.name, full, clauses, c.id).clauses}
            for t in targets:
                n += 1
                ok += t in ids and t in got
        out["table_refs_audit"], out["table_refs_audit_resolved"] = n, ok
    except Exception as ex:                                               # noqa: BLE001
        out["table_refs_error"] = repr(ex)[:120]
    return out


# ------------------------------------------------------------------------------------------------------------- synthetic
def prf(gold: set, got: set) -> dict:
    tp = len(gold & got)
    return {"gold": len(gold), "got": len(got), "tp": tp, "precision": round(tp / len(got), 3) if got else None,
            "recall": round(tp / len(gold), 3) if gold else None}


def run_synth(lang: str, seed: int, held_out: bool, extra: dict | None = None) -> tuple[set, set, set, str, list]:
    cl = S.build(6, 5, seed=seed)
    text = S.render(cl, lang, held_out=held_out)
    clauses = split_text(text)
    g = build_graph(text, clauses, load_cues(extra=extra))
    return S.gold(cl), S.edges_by_marker(g), {(a, b) for a, b, _ in S.edges_by_marker(g)}, text, clauses


def baseline_edges(text: str, clauses: list) -> set[tuple[str, str, str]]:
    """The baseline's edges as (consumer marker, provider marker, 'reference')."""
    mk = {c.id: (re.search(r"\bK\d\d\b", c.text) or [None])[0] for c in clauses}
    _, _, pairs = baseline_section_refs(text, clauses)
    return {(mk[a], mk[b], "reference") for a, b in pairs if mk.get(a) and mk.get(b)}


def synthetic_report(seeds=range(5), extra_held: dict | None = None) -> dict:
    res: dict = {}
    for lang in ("en", "fr", "de", "es"):
        for held in (False, True):
            tot_g: set = set()
            tot_o: set = set()
            tot_b: set = set()
            per_type: dict[str, list] = {}
            for seed in seeds:
                gold, got, _, text, clauses = run_synth(lang, seed, held, extra_held if held else None)
                tag = f"{seed}:"
                tot_g |= {(tag + a, tag + b, t) for a, b, t in gold}
                tot_o |= {(tag + a, tag + b, t) for a, b, t in got}
                bl = baseline_edges(text, clauses)
                tot_b |= {(tag + a, tag + b, t) for a, b, t in bl}
            types = sorted({t for _, _, t in tot_g})
            row = {"generic": prf(tot_g, tot_o), "baseline_typed": prf(tot_g, tot_b),
                   "baseline_untyped": prf({(a, b) for a, b, _ in tot_g}, {(a, b) for a, b, _ in tot_b}),
                   "generic_untyped": prf({(a, b) for a, b, _ in tot_g}, {(a, b) for a, b, _ in tot_o})}
            for t in types:
                per_type[t] = prf({x for x in tot_g if x[2] == t}, {x for x in tot_o if x[2] == t})
            row["by_type"] = per_type
            res[f"{lang}{'_heldout' if held else ''}"] = row
    return res


# ------------------------------------------------------------------------------------------------------------- metamorphic
def meta_report() -> dict:
    out = {}
    for lang in ("en", "fr", "de", "es"):
        cl = S.build(6, 5, seed=3)
        base_text = S.render(cl, lang)
        g0 = build_graph(base_text, split_text(base_text))
        e0 = S.edges_by_marker(g0)
        variants = {}
        # other numbers: every section number moves by 40 and the part words rotate
        lab = {k: f"{int(v.split('.')[0]) + 40}.{v.split('.')[1]}" for k, v in S.labels_default(cl).items()}
        variants["renumbered"] = S.render(cl, lang, labels=lab, kw_shift=1)
        # another order: sections written in reverse, numbered by their new position
        order = [c.k for s in range(6, 0, -1) for c in cl if c.section == s]
        lab2 = {}
        for i, sec in enumerate(range(6, 0, -1), 1):
            for j, c in enumerate([c for c in cl if c.section == sec], 1):
                lab2[c.k] = f"{i}.{j}"
        variants["moved"] = S.render(cl, lang, labels=lab2, order=order)
        # both
        lab3 = {k: f"{int(v.split('.')[0]) + 70}.{v.split('.')[1]}" for k, v in lab2.items()}
        variants["moved_and_renumbered"] = S.render(cl, lang, labels=lab3, order=order, kw_shift=2)
        for name, text in variants.items():
            g = build_graph(text, split_text(text))
            e = S.edges_by_marker(g)
            out[f"{lang}_{name}"] = {"same_edges": e == e0, "edges": len(e), "lost": sorted(e0 - e)[:5], "new": sorted(e - e0)[:5]}
    return out


def shift_numbers(text: str) -> str:
    """Move the first component of EVERY dotted number of a real text by a constant (3.79 becomes 503.79, 206.2.8 becomes 706.2.8),
    in headings, references and lists alike, except where a unit follows ("2.5 m"), and the whole-section references ("Section 7").
    It is a bijection on labels, so the graph of the
    shifted text must be the graph of the text."""
    unit = r"(?!\d|\s?(?:m|mm|cm|km|%|°|ft|in|s|min|kg|N|kN|Pa|lux|dB)(?![A-Za-z]))"
    t = re.sub(rf"(?<![\d.\-/])(\d{{1,3}})((?:\.\d+)+){unit}", lambda m: f"{int(m.group(1)) + 500}{m.group(2)}", text)
    # a whole section named by its number ("Section 7") moves with the clauses numbered 7.x
    return re.sub(r"(?i)(sections?)(\s+)(\d{1,3})(?![\d.])", lambda m: f"{m.group(1)}{m.group(2)}{int(m.group(3)) + 500}", t)


def meta_real(path: Path, cache: Path, limit: int = 120000) -> dict:
    full, _ = split_cached(path, cache / path.stem)
    text = full[:limit]
    c0 = split_text(text)
    g0 = build_graph(text, c0)
    shifted = shift_numbers(text)
    c1 = split_text(shifted)
    g1 = build_graph(shifted, c1)

    def key(g, clauses):
        idx = {c.id: i for i, c in enumerate(clauses)}
        return {(idx[e.consumer], idx[g.nodes[e.provider].clause], e.type) for e in g.edges if e.provider and e.origin != "term"
                and g.nodes[e.provider].clause in idx and e.consumer in idx and g.nodes[e.provider].ntype == "clause"}
    k0, k1 = key(g0, c0), key(g1, c1)
    return {"doc": path.name, "chars": len(text), "clauses_before": len(c0), "clauses_after": len(c1), "edges_before": len(k0),
            "edges_after": len(k1), "common": len(k0 & k1), "lost": len(k0 - k1), "new": len(k1 - k0),
            "text_changed": shifted != text}


# ------------------------------------------------------------------------------------------------------------- sample
def write_sample(graphs: dict, n: int, seed: int, out: Path) -> None:
    rng = random.Random(seed)
    pool = []
    for doc, g in graphs.items():
        for e in g.edges:
            if e.provider:
                pool.append((doc, g, e))
    groups = {"reference/table/condition (cited label)": [x for x in pool if x[2].origin == "ref" and x[2].type in ("reference", "table_of", "condition_from") and x[2].provider],
              "exception": [x for x in pool if x[2].type == "exception_of" and x[2].provider],
              "definition": [x for x in pool if x[2].origin == "term" or (x[2].type == "definition_of" and x[2].origin == "ref")]}
    lines = []
    for name, items in groups.items():
        lines.append(f"\n==== {name}: {len(items)} edges, sample {min(n, len(items))} (spread over the documents that have any)\n")
        per_doc: dict[str, list] = {}
        for x in items:
            per_doc.setdefault(x[0], []).append(x)
        picked: list = []
        share = max(1, -(-n // max(1, len(per_doc))))
        for doc_items in per_doc.values():
            picked += rng.sample(doc_items, min(share, len(doc_items)))
        rng.shuffle(picked)
        for i, (doc, g, e) in enumerate(picked[:n], 1):
            node = g.nodes[e.provider]
            lines.append(f"[{i}] {doc} | {e.type} | status {e.status} | cue '{e.cue}'")
            lines.append(f"    WORDS  ...{g.text[max(0, e.start - 110):e.start].replace(chr(10), ' ')}[[{g.text[e.start:e.end][:120].replace(chr(10), ' ')}]]{g.text[e.end:e.end + 60].replace(chr(10), ' ')}...")
            lines.append(f"    FROM   clause {e.consumer}")
            lines.append(f"    TO     {e.provider} ({node.ntype}) : {g.text[node.start:node.end][:150].replace(chr(10), ' ')}")
            lines.append(f"    REASON {e.reason[:140]}")
    out.write_text("\n".join(lines), encoding="utf-8")


# ------------------------------------------------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("docs", nargs="?", default="data/real_docs")
    ap.add_argument("--out", default="reports/reg_graph")
    ap.add_argument("--sample", type=int, default=20)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--no-meta-real", action="store_true")
    args = ap.parse_args()
    cache = Path(os.environ.get("SPLIT_CACHE", CACHE_DEFAULT))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    try:
        sa = load_script("split_audit")
    except Exception:                                                     # noqa: BLE001
        sa = None
    rows, graphs = [], {}
    for p in sorted(Path(args.docs).iterdir()):
        if p.suffix.lower() not in (".pdf", ".md", ".txt", ".docx"):
            continue
        r, g = real_doc(p, cache, sa)
        rows.append(r)
        graphs[p.name] = g
        print(f"{p.name:<40} edges {r['edges']['edges']:>5} refs {r['references']:>4} exact {r['exact']:>4} approx {r['approx']:>3} "
              f"unres {r['unresolved']:>3} ext {r['external']:>3} | terms {r['terms']:>3} | splitaudit {r.get('split_audit_resolved')}/{r.get('split_audit_refs')} "
              f"tablerefs {r.get('table_refs_audit_resolved')}/{r.get('table_refs_audit')} baseline {r['baseline_section_resolved']}/{r['baseline_section_refs']}", flush=True)
    syn = synthetic_report()
    extra = {"exception_cues": ["con excepcion de"]}
    syn_after = synthetic_report(extra_held=extra)
    meta = meta_report()
    real_meta = []
    if not args.no_meta_real:
        for name in ("ada_2010.pdf", "uk_adb_vol1_2019.pdf"):
            p = Path(args.docs) / name
            if p.is_file():
                real_meta.append(meta_real(p, cache))
    write_sample(graphs, args.sample, args.seed, out / "sample_for_hand_reading.txt")
    # three worked contexts
    ctx_examples = {}
    for doc, g in graphs.items():
        best = max((c.id for c in g.clauses if c.kind not in ("table_row", "table_header")),
                   key=lambda cid: len(g.by_consumer.get(cid, [])), default=None)
        if best:
            ctx_examples[doc] = resolve_context(g, best).to_dict()
    result = {"real": rows, "synthetic": syn, "synthetic_after_adding_one_phrase": syn_after, "meta_synthetic": meta, "meta_real": real_meta}
    (out / "reg_graph_audit.json").write_text(json.dumps(result, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    (out / "context_examples.json").write_text(json.dumps(ctx_examples, indent=1, ensure_ascii=False)[:300000], encoding="utf-8")
    print("\nSYNTHETIC (generic vs baseline), 5 seeds x 6 sections x 5 clauses")
    for k, v in syn.items():
        print(f"{k:<12} generic P {v['generic']['precision']} R {v['generic']['recall']} | untyped baseline P {v['baseline_untyped']['precision']} "
              f"R {v['baseline_untyped']['recall']} | generic untyped R {v['generic_untyped']['recall']}")
    print("after adding one Spanish phrase to the cue list (held out wording):",
          {k: (v['generic']['precision'], v['generic']['recall']) for k, v in syn_after.items() if k.endswith('heldout')})
    print("\nMETAMORPHIC", {k: v["same_edges"] for k, v in meta.items()})
    print("META REAL", real_meta)


if __name__ == "__main__":
    main()
