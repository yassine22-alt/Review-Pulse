"""Evidence-aware decisions with conservative legacy labels. See docs/verdict-policy.md."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..outcomes import EvidenceIssue, IssueCode, Outcome

LEN_TOL_ABS_M = 0.010
LEN_TOL_REL = 0.01
AREA_TOL_REL = 0.05
ANGLE_TOL_DEG = 1.0
ORDER = {"PASS": 0, "NOT_EVALUATED": 0, "WARNING": 1, "FAIL": 2}
ESTIMATED_SCALE_RELATIVE_UNCERTAINTY = 0.25  # Placeholder bound, not calibrated.


def length_tol(value_m: float, rel: float = LEN_TOL_REL, abs_m: float = LEN_TOL_ABS_M) -> float:
    return max(abs_m, rel * abs(value_m))


def compare(detected: float, op: str, limit: float, tol: float) -> tuple[bool, bool]:
    """Return violation and violation beyond the separate regulatory review band."""
    if op == ">=":
        return detected < limit, detected < limit - tol
    if op == ">":
        return detected <= limit, detected <= limit - tol
    if op == "<=":
        return detected > limit, detected > limit + tol
    if op == "<":
        return detected >= limit, detected >= limit + tol
    if op == "==":
        return abs(detected - limit) > 0, abs(detected - limit) > tol
    if op == "!=":
        return abs(detected - limit) <= tol, abs(detected - limit) <= tol
    raise ValueError(f"unknown operator {op}")


@dataclass
class Measurement:
    value: float
    op: str
    limit: float
    tolerance: float = 0.0
    scale_power: int = 1

    def interval(self, verified: bool, relative: float) -> tuple[float, float]:
        if not math.isfinite(relative) or not 0 <= relative < 1:
            raise ValueError("relative scale uncertainty must be finite and in [0, 1)")
        if not all(math.isfinite(x) for x in (self.value, self.limit, self.tolerance)):
            raise ValueError("measurement inputs must be finite")
        if self.scale_power not in (1, 2) or self.tolerance < 0:
            raise ValueError("invalid measurement scale power or tolerance")
        if verified:
            return self.value, self.value
        bounds = [self.value * (1 - relative) ** self.scale_power,
                  self.value * (1 + relative) ** self.scale_power]
        return min(bounds), max(bounds)

    def outcome(self, lo: float, hi: float) -> Outcome:
        if self.op in (">=", ">"):
            if not compare(lo, self.op, self.limit, self.tolerance)[0]:
                return "SATISFIED"
            if compare(hi, self.op, self.limit, self.tolerance)[1]:
                return "VIOLATED"
        elif self.op in ("<=", "<"):
            if not compare(hi, self.op, self.limit, self.tolerance)[0]:
                return "SATISFIED"
            if compare(lo, self.op, self.limit, self.tolerance)[1]:
                return "VIOLATED"
        elif self.op == "==":
            if lo == hi == self.limit:
                return "SATISFIED"
            if hi < self.limit - self.tolerance or lo > self.limit + self.tolerance:
                return "VIOLATED"
        elif self.op == "!=":
            if hi < self.limit - self.tolerance or lo > self.limit + self.tolerance:
                return "SATISFIED"
            if lo == hi == self.limit:
                return "VIOLATED"
        else:
            raise ValueError(f"unknown operator {self.op}")
        return "UNRESOLVED"


@dataclass
class Raw:
    subject_ids: list[str]
    violated: bool | None
    beyond_band: bool = True
    metric: bool = False
    deciding_ids: list[str] = field(default_factory=list)
    detected: str | None = None
    required: str | None = None
    evidence: dict = field(default_factory=dict)
    vars: dict = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    note: str | None = None
    measurement: Measurement | None = None
    evidence_issues: list[EvidenceIssue] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)


@dataclass
class Decision:
    verdict: str
    reason: str | None = None
    outcome: Outcome = "UNRESOLVED"
    evidence_issues: list[EvidenceIssue] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    interval: tuple[float, float] | None = None


def decide(raw: Raw, tier: str, *, guidance: bool, max_verdict: str = "FAIL",
           all_confirmed: bool = True, scale_verified: bool = True,
           relative_uncertainty: float = ESTIMATED_SCALE_RELATIVE_UNCERTAINTY) -> Decision:
    issues = list(raw.evidence_issues)
    dependencies = set(raw.dependencies)
    interval = None
    if raw.metric:
        dependencies.add("scale")
    if raw.missing or raw.violated is None:
        dependencies.update(raw.missing)
        detail = ", ".join(raw.missing) or raw.note or "required input unavailable"
        issues.append(EvidenceIssue(code=IssueCode.MISSING_INPUT, detail=detail))
        return Decision("NOT_EVALUATED", detail, evidence_issues=issues, dependencies=sorted(dependencies))
    outcome: Outcome = "VIOLATED" if raw.violated else "SATISFIED"
    uncertain_scale = raw.metric and (tier == "T3" or not scale_verified)
    if raw.metric:
        if uncertain_scale:
            issues.append(EvidenceIssue(code=IssueCode.UNCERTAIN_SCALE, detail="scale is unverified; bounds are provisional"))
        if raw.measurement:
            interval = raw.measurement.interval(not uncertain_scale, relative_uncertainty)
            outcome = raw.measurement.outcome(*interval)
        elif uncertain_scale:
            outcome = "UNRESOLVED"
    if not raw.beyond_band and raw.violated and not raw.measurement:
        outcome = "UNRESOLVED"
    if outcome == "UNRESOLVED" and not uncertain_scale and not raw.beyond_band:
        issues.append(EvidenceIssue(code=IssueCode.TOLERANCE_BAND, detail="within regulatory review tolerance"))
    if tier != "T1" and not all_confirmed:
        issues.append(EvidenceIssue(code=IssueCode.UNVERIFIED_GEOMETRY if raw.metric else IssueCode.MISSING_CONNECTION,
                                    detail="deciding geometry or connections need confirmation"))
        outcome = "UNRESOLVED"
    if raw.evidence_issues:
        outcome = "UNRESOLVED"
    verdict = {"SATISFIED": "PASS", "VIOLATED": "FAIL", "UNRESOLVED": "WARNING"}[outcome]
    if guidance and verdict == "FAIL":
        verdict = "WARNING"
    if ORDER[verdict] > ORDER[max_verdict]:
        verdict = max_verdict
    reason = "; ".join(i.detail for i in issues) or ("guidance rule" if guidance else None)
    return Decision(verdict, reason, outcome, issues, sorted(dependencies), interval)
