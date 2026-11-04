"""J2 - Verdict policy. ``decide`` is the only place a verdict is chosen.

| Situation                                                       | Verdict                     |
|-----------------------------------------------------------------|-----------------------------|
| Required input missing                                          | NOT_EVALUATED               |
| Rule source is guidance                                         | at most WARNING             |
| Not violated                                                    | PASS                        |
| Violated but within the tolerance band                          | WARNING                     |
| Violated beyond the band, tier T1 or every deciding confirmed   | FAIL                        |
| Violated beyond the band, T2/T3 with an unconfirmed element     | WARNING "verify ..."        |
| Metric rule on a model without a verified scale (T3)            | at most WARNING "verify"    |

NFR-05: no FAIL on a metric rule from estimated geometry.
"""

from __future__ import annotations

from dataclasses import dataclass, field

LEN_TOL_ABS_M = 0.010
LEN_TOL_REL = 0.01
AREA_TOL_REL = 0.05
ANGLE_TOL_DEG = 1.0

ORDER = {"PASS": 0, "NOT_EVALUATED": 0, "WARNING": 1, "FAIL": 2}


@dataclass
class Raw:
    subject_ids: list[str]
    violated: bool | None               # None = could not be evaluated for this subject
    beyond_band: bool = True               # violated beyond the tolerance band
    metric: bool = False                   # result depends on measured lengths/areas
    deciding_ids: list[str] = field(default_factory=list)
    detected: str | None = None
    required: str | None = None
    evidence: dict = field(default_factory=dict)
    vars: dict = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    note: str | None = None


@dataclass
class Decision:
    verdict: str
    reason: str | None = None


def length_tol(value_m: float, rel: float = LEN_TOL_REL, abs_m: float = LEN_TOL_ABS_M) -> float:
    return max(abs_m, rel * abs(value_m))


def compare(detected: float, op: str, limit: float, tol: float) -> tuple[bool, bool]:
    """(violated, beyond the tolerance band)."""
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


def decide(raw: Raw, tier: str, *, guidance: bool, max_verdict: str = "FAIL",
           all_confirmed: bool = True, scale_verified: bool = True) -> Decision:
    if raw.missing or raw.violated is None:
        return Decision("NOT_EVALUATED", "missing: " + ", ".join(raw.missing) if raw.missing else raw.note)
    if not raw.violated:
        return Decision("PASS")
    if not raw.beyond_band:
        return Decision("WARNING", "within tolerance band")
    verdict, reason = "FAIL", None
    if guidance:
        verdict, reason = "WARNING", "guidance rule (no requirement document)"
    elif raw.metric and (tier == "T3" or not scale_verified):
        verdict, reason = "WARNING", "verify measurement (scale estimated)"
    elif tier != "T1" and not all_confirmed:
        verdict, reason = "WARNING", "verify connections" if not raw.metric else "verify measurement"
    if ORDER[verdict] > ORDER[max_verdict]:
        verdict = max_verdict
    return Decision(verdict, reason)
