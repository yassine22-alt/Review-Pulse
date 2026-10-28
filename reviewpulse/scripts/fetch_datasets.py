"""Fetch public datasets into data/raw/<name>/ (decision D14).

    python scripts/fetch_datasets.py floorplancad resplan      # selected datasets
    python scripts/fetch_datasets.py --all                      # everything reachable
    python scripts/fetch_datasets.py --list

Each download is resumable, its sha256 is recorded in data/checksums.json on first fetch and
verified on later fetches, archives are extracted next to themselves, and data/LICENSES.md is
updated with source, licence, date and checksum. Raw data never goes into git.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
CHECKSUMS = ROOT / "data" / "checksums.json"
LICENSES = ROOT / "data" / "LICENSES.md"

DATASETS = {
    "floorplancad": dict(
        files=[("FloorPlanCAD.zip", "gdrive:1wsOQxIXjsqYzMlUpPNRjyQiMnwgVbtJG")],
        licence="annotations CC BY-NC 4.0; drawings not owned by the authors (non-commercial)",
        source="https://floorplancad.github.io/ (single-zip mirror from the VecFormer README)",
        note="vector SVG + PNG per drawing, per-primitive semantic labels"),
    "resplan": dict(
        files=[("ResPlan.zip", "https://raw.githubusercontent.com/m-agour/ResPlan/main/ResPlan.zip"),
               ("resplan_utils.py", "https://raw.githubusercontent.com/m-agour/ResPlan/main/resplan_utils.py"),
               ("split.json", "https://raw.githubusercontent.com/m-agour/ResPlan/main/split.json"),
               ("LICENSE", "https://raw.githubusercontent.com/m-agour/ResPlan/main/LICENSE")],
        licence="data CC BY 4.0, code MIT", source="https://github.com/m-agour/ResPlan",
        note="vector plans with walls, doors, windows, rooms and room graph"),
    "fptxt": dict(
        files=[("FP-TXT.zip", "https://zenodo.org/records/7921780/files/FP-TXT.zip?download=1")],
        licence="annotations MIT (images from CubiCasa5K / CVC-FP keep their own licences)",
        source="https://zenodo.org/records/7921780", note="text boxes; replicator.py needs cubicasa5k + cvcfp"),
    "cubicasa5k": dict(
        files=[("cubicasa5k.zip", "https://zenodo.org/records/2613548/files/cubicasa5k.zip?download=1")],
        licence="CC BY-NC 4.0 (non-commercial; check the repository LICENSE)",
        source="https://zenodo.org/records/2613548", note="5,000 raster plans with SVG ground truth (5.5 GB)"),
    "cvcfp": dict(
        files=[("CVC-FP.zip", "http://dag.cvc.uab.es/DATASETS/CVC-FP.zip")],
        licence="research use (see the dataset page)",
        source="http://dag.cvc.uab.es/dataset/cvc-fp-database-for-structural-floor-plan-analysis/",
        note="122 scanned plans with SVG ground truth"),
    "archcad": dict(
        files=[("ArchCAD", "hf:jackluoluo/ArchCAD")],
        licence="gated, non-commercial", source="https://huggingface.co/datasets/jackluoluo/ArchCAD",
        note="needs an approved access request and HF_TOKEN in .env"),
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _http(url: str, dest: Path) -> None:
    """Resumable HTTP download with a progress line."""
    part = dest.with_suffix(dest.suffix + ".part")
    have = part.stat().st_size if part.exists() else 0
    req = urllib.request.Request(url, headers={"User-Agent": "reviewpulse-fetch/1.0",
                                               **({"Range": f"bytes={have}-"} if have else {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        total = int(r.headers.get("Content-Length", 0)) + (have if r.status == 206 else 0)
        mode = "ab" if r.status == 206 else "wb"
        done = have if r.status == 206 else 0
        with open(part, mode) as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r  {dest.name}: {done / 1e6:,.0f} / {total / 1e6:,.0f} MB", end="", flush=True)
    print()
    part.replace(dest)


def _gdrive(file_id: str, dest: Path) -> None:
    import gdown

    out = gdown.download(id=file_id, output=str(dest), quiet=False, resume=True)
    if not out:
        raise RuntimeError("Google Drive refused the download (quota or link change); use the "
                           "train/test links on floorplancad.github.io instead")


def _hf(repo: str, dest: Path) -> None:
    import os

    token = os.environ.get("HF_TOKEN")
    if not token and (ROOT / ".env").exists():
        for ln in (ROOT / ".env").read_text().splitlines():
            if ln.startswith("HF_TOKEN="):
                token = ln.split("=", 1)[1].strip()
    if not token:
        raise RuntimeError("gated dataset: request access on its Hugging Face page, then put HF_TOKEN=... in .env")
    from huggingface_hub import snapshot_download

    snapshot_download(repo_id=repo, repo_type="dataset", local_dir=str(dest), token=token)


def fetch(name: str) -> dict:
    spec = DATASETS[name]
    out = RAW / name
    out.mkdir(parents=True, exist_ok=True)
    sums = json.loads(CHECKSUMS.read_text()) if CHECKSUMS.exists() else {}
    record = {"files": {}}
    for fname, url in spec["files"]:
        dest = out / fname
        if not dest.exists():
            print(f"[{name}] downloading {fname}")
            if url.startswith("gdrive:"):
                _gdrive(url[7:], dest)
            elif url.startswith("hf:"):
                _hf(url[3:], dest)
                continue
            else:
                _http(url, dest)
        digest = _sha256(dest)
        key = f"{name}/{fname}"
        if key in sums and sums[key] != digest:
            raise RuntimeError(f"checksum mismatch for {key}: expected {sums[key]}, got {digest}")
        sums[key] = digest
        record["files"][fname] = digest
        if dest.suffix == ".zip" and not (out / (dest.stem + ".extracted")).exists():
            print(f"[{name}] extracting {fname}")
            with zipfile.ZipFile(dest) as z:
                z.extractall(out)
            (out / (dest.stem + ".extracted")).write_text(dt.date.today().isoformat())
    CHECKSUMS.parent.mkdir(parents=True, exist_ok=True)
    CHECKSUMS.write_text(json.dumps(sums, indent=1, sort_keys=True))
    _log_licence(name, spec, record)
    return record


def _log_licence(name: str, spec: dict, record: dict) -> None:
    """Keep one up-to-date row per dataset in data/LICENSES.md (table under '## Fetched')."""
    header = "## Fetched\n\n| Dataset | Licence | Source | Fetched | sha256 (first file) |\n|---|---|---|---|---|\n"
    text = LICENSES.read_text(encoding="utf-8") if LICENSES.exists() else "# Data licences\n\n"
    if "## Fetched" not in text:
        text = text.rstrip() + "\n\n" + header
    first = next(iter(record["files"].values()), "")
    row = f"| {name} | {spec['licence']} | {spec['source']} | {dt.date.today().isoformat()} | `{first[:16]}...` |"
    lines = [ln for ln in text.splitlines() if not ln.startswith(f"| {name} |")]
    text = "\n".join(lines).rstrip() + "\n" + row + "\n"
    LICENSES.write_text(text, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list:
        for k, v in DATASETS.items():
            print(f"{k:13s} {v['licence']:60.60s} {v['note']}")
        return 0
    names = list(DATASETS) if a.all else a.names
    failed = []
    for n in names:
        if n not in DATASETS:
            print(f"unknown dataset {n}; --list shows them")
            return 2
        try:
            rec = fetch(n)
            print(f"[{n}] ok: {', '.join(rec['files'])}")
        except Exception as e:  # noqa: BLE001 - report and continue with the others
            print(f"[{n}] FAILED: {e}")
            failed.append(n)
    if failed:
        print("not fetched:", ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
