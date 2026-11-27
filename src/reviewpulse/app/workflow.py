"""What a reviewer does to a project beyond the rules: set a clause aside as deferred or not applicable, accept, edit or drop a
correction item, sign off a discipline for a cycle. Each is stored under the project (``review/``) and each is written to a
plain audit trail: who, what, when. A name is required for every change; nothing here runs a model.

    <project>/review/clause_states.json   {clause: {state, by, at, note}}
    <project>/review/edits.json           {item key: {action, wording, original, by, at, events}}
    <project>/review/signoffs.json        [{reviewer, cycle, discipline, result, note, at}], every sign off ever made
    <project>/review/audit.jsonl          one JSON object per line
"""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

from ..report import reviewer_states as rs
from .store import Store, now, replace

_LOCKS: dict[str, threading.RLock] = {}
_GUARD = threading.Lock()
EDIT_ACTIONS = ("accept", "edit", "drop", "reset")


def _lock(pid: str) -> threading.RLock:
    with _GUARD:
        return _LOCKS.setdefault(pid, threading.RLock())


def _dir(store: Store, pid: str) -> Path:
    d = store.dir(pid) / "review"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return default


def _write(path: Path, data) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    replace(tmp, path)


def need_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise ValueError("a reviewer name is required")
    return name


# -- audit trail -------------------------------------------------------------------------------------------------------
def log(store: Store, pid: str, who: str, what: str, detail: dict | None = None) -> dict:
    """Append one line: who did what, when. ``detail`` carries the ids and values needed to understand it later."""
    entry = {"at": now(), "who": need_name(who), "what": what, "detail": detail or {}}
    with _lock(pid):
        with (_dir(store, pid) / "audit.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def audit(store: Store, pid: str) -> list[dict]:
    f = _dir(store, pid) / "audit.jsonl"
    if not f.exists():
        return []
    out = []
    for line in f.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue                                       # a half written last line must not hide the rest
    return out


# -- clause states -----------------------------------------------------------------------------------------------------
def clause_states(store: Store, pid: str) -> dict:
    return _read(_dir(store, pid) / "clause_states.json", {})


_HASHES: dict[tuple, str] = {}        # (file, size, time) -> its digest: a drawing set is large and read once


def _file_digest(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    st = path.stat()
    key = (str(path), st.st_size, st.st_mtime_ns)
    if key not in _HASHES:
        _HASHES[key] = hashlib.sha256(path.read_bytes()).hexdigest()
    return _HASHES[key]


def _words_digest(text: str) -> str:
    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()


def basis(store: Store, pid: str, clause_text: str | None) -> dict:
    """What a decision rests on: the drawings file and the words of the requirement, as they are now."""
    plan = _file_digest(store.plan_path(store.get(pid)))
    return {**({"plan": plan} if plan else {}), **({"clause": _words_digest(clause_text)} if clause_text else {})}


def decisions(store: Store, pid: str, clause_texts: dict[str, str]) -> dict:
    """Every decision, with ``stale`` saying why one no longer holds: made on other drawings, or on other words. A deferral
    speaks of a submittal, not of the drawings, so it holds as long as the words do."""
    out, plan = {}, None
    for clause, st in clause_states(store, pid).items():
        was, why = st.get("basis") or {}, []
        if "clause" in was:
            text = clause_texts.get(clause)
            if text is None or _words_digest(text) != was["clause"]:
                why.append("the requirement's words changed")
        if "plan" in was and st.get("state") != "deferred":
            plan = _file_digest(store.plan_path(store.get(pid))) if plan is None else plan
            if plan != was["plan"]:
                why.append("the drawings were replaced")
        out[clause] = {**st, "stale": " and ".join(why) or None}
    return out


def holding(store: Store, pid: str, clause_texts: dict[str, str]) -> dict:
    """The decisions that still hold. Only these count: a pass never rests on drawings or words that are gone."""
    return {k: v for k, v in decisions(store, pid, clause_texts).items() if not v["stale"]}


PART_MARKS = ("seen", "missing")


def _ticked(parts, offered: list[str]) -> list[dict]:
    """What a reviewer ticked, kept only for parts the tool showed: a record never holds a part nobody was asked about."""
    out, left = [], list(offered)
    for p in parts or []:
        if p.get("mark") not in PART_MARKS:
            raise ValueError(f"a part is marked {' or '.join(PART_MARKS)}")
        if p.get("text") not in left:
            raise ValueError("that part is not one the requirement was cut into")
        left.remove(p["text"])
        out.append({"text": p["text"], "mark": p["mark"]})
    return out


def set_clause_state(store: Store, pid: str, clause: str, state: str, reviewer: str, note: str = "",
                     evidence: dict | None = None, clause_text: str | None = None, parts: list[dict] | None = None,
                     offered: list[str] | None = None) -> dict:
    """A reviewer decides a clause by hand (``reviewer_decisions`` in reviewer_states.yaml), or ``reset`` takes it back.
    ``evidence``: where on the plans {sheet, box, text}; the caller has checked that the place exists."""
    who = need_name(reviewer)
    allowed = list(rs.config()["reviewer_decisions"])
    if state != "reset" and state not in allowed:
        raise ValueError(f"unknown state {state!r}; a reviewer may set {', '.join(allowed)}, or reset")
    if not (clause or "").strip():
        raise ValueError("a clause is required")
    needs = (rs.config()["reviewer_decisions"].get(state) or {}).get("needs")
    if needs == "note" and not _is_text(note):
        raise ValueError("write the comment to the applicant")
    if needs == "evidence" and not evidence and not _is_text(note):
        raise ValueError("say where the plans show it: pick a note or a sheet, or write what you relied on")
    ticked = _ticked(parts, offered or []) if state != "reset" else []
    if state == "shown" and any(p["mark"] == "missing" for p in ticked):
        raise ValueError("a requirement with a missing part cannot be recorded as shown on the plans")
    with _lock(pid):
        states = clause_states(store, pid)
        if state == "reset":
            states.pop(clause, None)
        else:
            states[clause] = {"state": state, "by": who, "at": now(), "note": (note or "").strip(),
                              "basis": basis(store, pid, clause_text),
                              **({"evidence": evidence} if evidence else {}), **({"parts": ticked} if ticked else {})}
        _write(_dir(store, pid) / "clause_states.json", states)
        log(store, pid, who, f"clause {clause} set to {state}", {"clause": clause, "state": state, "note": (note or "").strip(),
                                                              **({"evidence": evidence} if evidence else {})})
    return states.get(clause) or {"state": "reset"}


# -- correction item edits ---------------------------------------------------------------------------------------------
def item_edits(store: Store, pid: str) -> dict:
    return _read(_dir(store, pid) / "edits.json", {})


def set_item(store: Store, pid: str, key: str, action: str, reviewer: str, wording: str | None = None, original: str = "") -> dict:
    """accept, edit (new wording), drop, or reset one correction item. ``events`` counts how many times the reviewer changed
    this item by hand (edit or drop): the edit burden of docs/REVIEWER_WORKFLOW.md section 6."""
    who = need_name(reviewer)
    if action not in EDIT_ACTIONS:
        raise ValueError(f"unknown action {action!r}; use {', '.join(EDIT_ACTIONS)}")
    if action == "edit" and not _is_text(wording):
        raise ValueError("the new wording is empty")
    with _lock(pid):
        edits = item_edits(store, pid)
        prev = edits.get(key, {})
        events = prev.get("events", 0)
        if action == "reset":
            edits.pop(key, None)
        else:
            events += action in ("edit", "drop")
            edits[key] = {"action": action, "by": who, "at": now(), "events": events,
                          "original": prev.get("original") or original,
                          **({"wording": " ".join(wording.split())} if action == "edit" else {})}
        _write(_dir(store, pid) / "edits.json", edits)
        log(store, pid, who, f"correction item {key}: {action}", {"item": key, "action": action,
                                                                    **({"wording": " ".join(wording.split())} if action == "edit" else {})})
    return edits.get(key, {"action": "pending"})


def _is_text(x) -> bool:
    return isinstance(x, str) and bool(x.strip())


# -- sign off ----------------------------------------------------------------------------------------------------------
def signoffs(store: Store, pid: str) -> list[dict]:
    return _read(_dir(store, pid) / "signoffs.json", [])


def sign_off(store: Store, pid: str, reviewer: str, discipline: str, result: str, cycle: int = 1, note: str = "",
             known_disciplines: set[str] | None = None) -> dict:
    """A named reviewer records the result for one discipline in one cycle. Every sign off is kept; the latest per cycle and
    discipline counts. Nothing stops a reviewer from signing a result different from the proposal: the list shows the difference."""
    who = need_name(reviewer)
    if result not in rs.config()["signoff_results"]:
        raise ValueError(f"unknown result {result!r}; use one of {', '.join(rs.config()['signoff_results'])}")
    if known_disciplines is not None and discipline not in known_disciplines:
        raise ValueError(f"unknown discipline {discipline!r}")
    if cycle < 1:
        raise ValueError("the cycle starts at 1")
    entry = {"reviewer": who, "cycle": cycle, "discipline": discipline, "result": result, "note": (note or "").strip(), "at": now()}
    with _lock(pid):
        records = signoffs(store, pid)
        records.append(entry)
        _write(_dir(store, pid) / "signoffs.json", records)
        log(store, pid, who, f"signed off {discipline} for cycle {cycle}: {result}", entry)
    return entry
