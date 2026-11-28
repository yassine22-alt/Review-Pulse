"""Projects on disk. One folder per project, plain JSON and YAML only, so a project can be inspected,
copied or re-run with the CLI (``rp check <project>/run``).

    <data>/projects/<id>/
        project.json          name, inputs, settings
        inputs/plan/<hash>/<file>  every uploaded drawing, kept unchanged under its content hash
        inputs/req/<file>     uploaded requirement document
        run/                  pipeline run folder (sheet_*.json, building_*.json, findings.json, reports)
        drafts/               clauses.json, <doc>.drafts.yaml, review.json (curator decisions)
        pack/                 rules approved for this project
        jobs/<job>.json       background job records
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import shutil
import threading
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..files import publish, read_whole, replace

__all__ = ["PLAN_TYPES", "PROJECT_FOLDERS", "REQ_TYPES", "Project", "Store", "now", "publish", "read_whole", "replace", "safe_name"]

PLAN_TYPES = {".pdf", ".dxf", ".dwg", ".svg", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
REQ_TYPES = {".pdf", ".md", ".txt", ".docx", ".xlsx", ".xlsm", ".csv", ".tsv", ".html", ".htm", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
PROJECT_FOLDERS = ("inputs/plan", "inputs/req", "drafts", "pack", "jobs")


def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def safe_name(name: str) -> str:
    """A file name that cannot leave its folder."""
    base = Path(name.replace("\\", "/")).name
    base = re.sub(r"[^\w.\- ]+", "_", base).strip(" .") or "file"
    return base[:120]


@dataclass
class Project:
    id: str
    name: str
    created: str
    plan: str | None = None             # file name of the current plan
    plan_version: str | None = None     # its content hash; None: made before versions were kept (the file is under inputs/plan)
    versions: list[dict] = field(default_factory=list)   # every plan ever uploaded, oldest first: {id, name, bytes, at}
    requirements: str | None = None     # file name under inputs/req
    base_pack: str | None = None        # an explicit optional pack; user-supplied requirements are the default
    context_links: dict[str, list[str]] = field(default_factory=dict)
    curator: str = ""
    external_consent: bool = False      # the reviewer allowed clause text (never plans) to go to a hosted model for hard clauses
    inventory_reviewed: bool = False    # a person confirmed every room, door and window was found: passes may be reported
    updated: str = ""
    org: str = ""                       # the organisation that owns the project (empty: made without accounts)
    occupancy: str = ""                 # the building's use, in the office's own words: recorded, it selects no rule
    location: str = ""                  # where the building is: recorded, it selects no rule
    notes: dict = field(default_factory=dict)


def one_line(text: str, limit: int = 160) -> str:
    return " ".join((text or "").split())[:limit]


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
        if not p.plan:
            return None
        folder = self.dir(p.id) / "inputs" / "plan"
        return folder / p.plan_version / p.plan if p.plan_version else folder / p.plan

    def version_dir(self, pid: str, version: str) -> Path:
        """The folder of one uploaded version: the drawing, and what belongs to that round (its comments, its back check)."""
        if not re.fullmatch(r"[0-9a-f]{16}", version or ""):
            raise KeyError(version)
        return self.dir(pid) / "inputs" / "plan" / version

    def version_path(self, p: Project, version: str) -> Path:
        entry = next((v for v in p.versions if v["id"] == version), None)
        if entry is None:
            raise KeyError(version)
        return self.version_dir(p.id, version) / entry["name"]

    def _keep_plan(self, p: Project, name: str, data: bytes) -> Path:
        """Store a drawing under its content hash. Nothing already stored is ever changed or removed; the same bytes sent
        again are the same version."""
        version = hashlib.sha256(data).hexdigest()[:16]
        folder = self.version_dir(p.id, version)
        entry = next((v for v in p.versions if v["id"] == version), None)
        if entry is None:
            folder.mkdir(parents=True, exist_ok=True)
            publish(folder / name, data)
            entry = {"id": version, "name": name, "bytes": len(data), "at": now()}
        else:
            p.versions.remove(entry)                 # an earlier version sent again becomes the current one
        p.versions.append(entry)
        p.plan, p.plan_version = entry["name"], version
        return folder / entry["name"]

    def req_path(self, p: Project) -> Path | None:
        return self.dir(p.id) / "inputs" / "req" / p.requirements if p.requirements else None

    # -- projects ------------------------------------------------------------
    def create(self, name: str, base_pack: str | None = None, curator: str = "", org: str = "", occupancy: str = "",
               location: str = "") -> Project:
        p = Project(id=uuid.uuid4().hex[:12], name=name.strip() or "Untitled project", created=now(),
                    base_pack=base_pack, curator=curator, org=org, occupancy=one_line(occupancy), location=one_line(location))
        self._ensure_folders(p.id)
        self.save(p)
        return p

    def _ensure_folders(self, pid: str) -> None:
        """Empty folders can vanish (temp cleaners, zip copies, git); a project must still work without them."""
        for sub in PROJECT_FOLDERS:
            (self.dir(pid) / sub).mkdir(parents=True, exist_ok=True)

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
        self._ensure_folders(pid)
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
        self._ensure_folders(p.id)             # they may have vanished since the project was read (a long analysis)
        if kind == "plan":
            legacy = self.plan_path(p) if p.plan and not p.plan_version else None
            if legacy is not None and legacy.is_file():        # a plan stored before versions were kept becomes the first one
                self._keep_plan(p, legacy.name, legacy.read_bytes())
                legacy.unlink()
            path = self._keep_plan(p, name, data)
            shutil.rmtree(self.run_dir(p.id), ignore_errors=True)
        else:
            folder = self.dir(p.id) / "inputs" / "req"
            for old in folder.iterdir():      # one current requirement document
                old.unlink()
            path = folder / name
            path.write_bytes(data)
            p.requirements = name
            p.context_links = {}
            for old in self.drafts_dir(p.id).glob("*"):
                old.unlink()
        self.save(p)
        return path
