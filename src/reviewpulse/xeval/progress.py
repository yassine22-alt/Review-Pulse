"""Visible progress for the extractor evaluation: one JSON state file, a console view and PROGRESS.md.

Every experiment step registers itself here, so `python -m reviewpulse.xeval status` always shows
which tasks are done, which one is running (with a counter) and the headline numbers so far.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

OUT_DIR = Path("reports/extractor_eval")

PLAN = [
    ("E0", "Setup", "Worktree on the interpreter branch, environment check, progress tracker"),
    ("E1", "Schema probe", "Does the recursive program schema work on a local 7B model? Compare with a flat node table"),
    ("E2", "Synthetic corpus", "Sample valid programs, render them as EN/FR requirement text (truth by construction)"),
    ("E3", "Behavioral scorer", "Judge a drafted program by running it against generated fact worlds, not by structure"),
    ("E4", "Baseline run", "First real numbers: one-shot drafter on the corpus, three arms"),
    ("E5", "Ablations", "Verified numbers, behavior-cluster voting, bounded repair, model swap"),
    ("E6", "Confidence", "Combine agreement and grounding signals, risk against coverage"),
    ("E7", "Ingestion", "PaddleOCR-VL / MinerU / Docling on rendered synthetic documents"),
    ("E10", "Stress rewrites", "Does the sentence check survive spacing, references, units, distractors, upper case?"),
    ("E9", "Verifier check", "Sentence-versus-rule checks: wrongly blocks correct rules? catches dropped conditions?"),
    ("E8", "Demand analysis", "What real requirement sentences ask to be measured vs what the plan reader supplies"),
]

SYMBOL = {"done": "[x]", "running": "[~]", "pending": "[ ]", "failed": "[!]"}


class Tracker:
    def __init__(self, out_dir: Path | str = OUT_DIR):
        self.dir = Path(out_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "progress.json"
        self.state = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            state = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            state = {"tasks": {}, "log": []}
        for tid, title, desc in PLAN:
            task = state["tasks"].setdefault(
                tid, {"status": "pending", "metrics": {}, "detail": "", "progress": None}
            )
            task["title"], task["desc"] = title, desc
        return state

    def _refresh(self) -> None:
        """Pick up what other processes wrote since we last looked (a long run and a quick check at once)."""
        self.state = self._load()

    def save(self) -> None:
        self.path.write_text(json.dumps(self.state, indent=1, ensure_ascii=False), encoding="utf-8")
        (self.dir / "PROGRESS.md").write_text(self.markdown(), encoding="utf-8")

    def _log(self, tid: str, text: str) -> None:
        self.state["log"].append({"t": time.strftime("%Y-%m-%d %H:%M:%S"), "task": tid, "text": text})
        self.state["log"] = self.state["log"][-200:]

    def start(self, tid: str, total: int | None = None, detail: str = "") -> None:
        self._refresh()
        task = self.state["tasks"][tid]
        task.update(status="running", detail=detail, started=time.time(), progress=[0, total] if total else None)
        self._log(tid, f"started {detail}".strip())
        self.save()

    def step(self, tid: str, done: int, total: int | None = None, detail: str = "") -> None:
        self._refresh()
        task = self.state["tasks"][tid]
        total = total if total is not None else (task["progress"] or [0, None])[1]
        task["progress"] = [done, total]
        if detail:
            task["detail"] = detail
        self.save()

    def finish(self, tid: str, metrics: dict | None = None, detail: str = "", failed: bool = False) -> None:
        self._refresh()
        task = self.state["tasks"][tid]
        task["status"] = "failed" if failed else "done"
        task["finished"] = time.time()
        if metrics:
            task["metrics"].update(metrics)
        if detail:
            task["detail"] = detail
        if task.get("progress") and task["progress"][1]:
            task["progress"][0] = task["progress"][1]
        self._log(tid, f"{'FAILED' if failed else 'done'}: {detail}".strip())
        self.save()

    def note(self, tid: str, text: str) -> None:
        self._refresh()
        self._log(tid, text)
        self.save()

    # -- views ---------------------------------------------------------------------------------
    def render_line(self, tid: str, task: dict) -> str:
        line = f"{SYMBOL[task['status']]} {tid} {task['title']}"
        prog = task.get("progress")
        if prog and prog[1]:
            width = 20
            fill = int(width * prog[0] / prog[1])
            line += f"  [{'#' * fill}{'.' * (width - fill)}] {prog[0]}/{prog[1]}"
        if task.get("detail"):
            line += f"  {task['detail']}"
        return line

    def console(self) -> str:
        rows = [self.render_line(tid, self.state["tasks"][tid]) for tid, *_ in PLAN]
        for tid, *_ in PLAN:
            metrics = self.state["tasks"][tid]["metrics"]
            if metrics:
                rows.append(f"      {tid}: " + ", ".join(f"{k}={v}" for k, v in metrics.items()))
        return "\n".join(rows)

    def markdown(self) -> str:
        lines = ["# Extractor evaluation: progress", "", "| | Step | What | Status |", "|---|---|---|---|"]
        for tid, title, desc in PLAN:
            task = self.state["tasks"][tid]
            prog = task.get("progress")
            counter = f" ({prog[0]}/{prog[1]})" if prog and prog[1] else ""
            lines.append(f"| {SYMBOL[task['status']]} | {tid} {title} | {desc} | {task['status']}{counter} |")
        lines += ["", "## Results so far", ""]
        for tid, title, _ in PLAN:
            metrics = self.state["tasks"][tid]["metrics"]
            if metrics:
                lines.append(f"**{tid} {title}**")
                lines += [f"- {k}: {v}" for k, v in metrics.items()]
                lines.append("")
        lines += ["## Recent log", ""]
        lines += [f"- {e['t']} {e['task']}: {e['text']}" for e in self.state["log"][-15:]]
        return "\n".join(lines) + "\n"
