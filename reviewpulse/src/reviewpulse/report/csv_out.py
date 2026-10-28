"""findings.csv: rule, verdict, severity, subject, message, detected, required, tier, page, x, y."""

from __future__ import annotations

import csv
from pathlib import Path

from ..schema import BuildingModel, Finding
from .anchor import anchor_point


def write_csv(findings: list[Finding], models: list[BuildingModel], out: Path) -> Path:
    by_sheet = {m.sheet.id: m for m in models}
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["finding_id", "rule", "verdict", "severity", "subject", "message", "detected", "required",
                    "tier", "page", "x", "y", "dismissed"])
        for f in findings:
            m = by_sheet.get(f.evidence.get("sheet")) or (models[0] if models else None)
            pt = anchor_point(f, m) if m else None
            w.writerow([f.evidence.get("finding_id", ""), f.rule_id, f.verdict, f.severity, ";".join(f.subject_ids),
                        f.message, f.detected or "", f.required or "", f.tier, m.sheet.page if m else "",
                        f"{pt[0]:.3f}" if pt else "", f"{pt[1]:.3f}" if pt else "",
                        f.evidence.get("dismissed", "")])
    return out
