"""Projects on disk. One folder per project, plain JSON and YAML only, so a project can be inspected,
copied or re-run with the CLI (``rp check <project>/run``).

    <data>/projects/<id>/
        project.json          name, inputs, settings
        inputs/plan/<file>    uploaded drawing (one current plan)
        inputs/req/<file>     uploaded requirement document
        run/                  pipeline run folder (sheet_*.json, building_*.json, findings.json, reports)
        drafts/               clauses.json, <doc>.drafts.yaml, review.json (curator decisions)
        pack/                 rules approved for this project
        jobs/<job>.json       background job records
"""

from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

PLAN_TYPES = {".pdf", ".dxf", ".dwg", ".svg", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
REQ_TYPES = {".pdf", ".md", ".txt", ".docx"}


def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def safe_name(name: str) -> str:
    """A file name that cannot leave its folder."""
    base = Path(name.replace("\\", "/")).name
    base = re.sub(r"[^\w.\- ]+", "_", base).strip(" .") or "file"
    return base[:120]


def replace(tmp: Path, dst: Path, tries: int = 20) -> None:
    """Atomic rename; Windows refuses it while a reader holds ``dst`` open, so retry briefly."""
    for attempt in range(tries):
        try:
            tmp.replace(dst)
            return
        except PermissionError:
            time.sleep(0.02 * (attempt + 1))
    tmp.replace(dst)


@dataclass
class Project:
    id: str
    name: str
    created: str
    plan: str | None = None             # file name under inputs/plan
    requirements: str | None = None     # file name under inputs/req
    base_pack: str | None = "starter"   # a folder of rules/packs, or None for project rules only
    curator: str = ""
    updated: str = ""
    notes: dict = field(default_factory=dict)


class Store:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        (self.root / "projects").mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    # -- paths ---------------------------------------------------------------
    def dir(self, pid: str) -> Path:
        if not re.fullmatch(r"[a-z0-9]{6,32}", pid or ""):
            raise KeyError(pid)
        return self.root / "projects" / pid

    def run_dir(self, pid: str) -> Path:
        return self.dir(pid) / "run"

    def drafts_dir(self, pid: str) -> Path:
        return self.dir(pid) / "drafts"

    def pack_dir(self, pid: str) -> Path:
        return self.dir(pid) / "pack"

    def plan_path(self, p: Project) -> Path | None:
        return self.dir(p.id) / "inputs" / "plan" / p.plan if p.plan else None

    def req_path(self, p: Project) -> Path | None:
        return self.dir(p.id) / "inputs" / "req" / p.requirements if p.requirements else None

    # -- projects ------------------------------------------------------------
    def create(self, name: str, base_pack: str | None = "starter", curator: str = "") -> Project:
        p = Project(id=uuid.uuid4().hex[:12], name=name.strip() or "Untitled project", created=now(),
                    base_pack=base_pack, curator=curator)
        d = self.dir(p.id)
        for sub in ("inputs/plan", "inputs/req", "drafts", "pack", "jobs"):
            (d / sub).mkdir(parents=True, exist_ok=True)
        self.save(p)
        return p

    def save(self, p: Project) -> Project:
        p.updated = now()
        with self._lock:
            tmp = self.dir(p.id) / "project.json.tmp"
            tmp.write_text(json.dumps(asdict(p), indent=1), encoding="utf-8")
            replace(tmp, self.dir(p.id) / "project.json")
        return p

    def get(self, pid: str) -> Project:
        f = self.dir(pid) / "project.json"
        if not f.exists():
            raise KeyError(pid)
        data = json.loads(f.read_text(encoding="utf-8"))
        known = Project.__dataclass_fields__
        return Project(**{k: v for k, v in data.items() if k in known})

    def list(self) -> list[Project]:
        out = []
        for f in (self.root / "projects").glob("*/project.json"):
            try:
                out.append(self.get(f.parent.name))
            except (KeyError, ValueError, TypeError):
                continue
        return sorted(out, key=lambda p: p.updated or p.created, reverse=True)

    def delete(self, pid: str) -> None:
        shutil.rmtree(self.dir(pid), ignore_errors=True)

    # -- uploads -------------------------------------------------------------
    def put_input(self, p: Project, kind: str, filename: str, data: bytes) -> Path:
        types = PLAN_TYPES if kind == "plan" else REQ_TYPES
        name = safe_name(filename)
        if Path(name).suffix.lower() not in types:
            raise ValueError(f"unsupported {kind} file type {Path(name).suffix or '(none)'}; "
                             f"expected one of {', '.join(sorted(types))}")
        folder = self.dir(p.id) / "inputs" / ("plan" if kind == "plan" else "req")
        for old in folder.iterdir():          # one current file per kind
            old.unlink()
        path = folder / name
        path.write_bytes(data)
        if kind == "plan":
            p.plan = name
            shutil.rmtree(self.run_dir(p.id), ignore_errors=True)
        else:
            p.requirements = name
            for old in self.drafts_dir(p.id).glob("*"):
                old.unlink()
        self.save(p)
        return path
