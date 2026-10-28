"""R14 - Tiers, confidence and confirmation.

T1 exact (vector + exact or consistent scale), T2 calibrated, T3 estimated.
Only T1, or elements a user confirmed, may lead to a FAIL (policy in engine/policy.py).
"""

from __future__ import annotations

from ..schema import BuildingModel, Sheet

TAU_VECTOR = 0.90     # placeholders until >= 200 labelled elements allow conformal calibration
TAU_RASTER = 0.95


def tier(sheet: Sheet) -> str:
    s = sheet.scale
    # dimensions read by OCR (outlined text) can be misread: their consensus is verified, not exact
    ocr_dims = any(t.kind == "dimension" and t.prov.source == "ocr" for t in sheet.texts)
    exact_consensus = s.method == "dimension_consensus" and s.confidence >= 0.8 and not ocr_dims
    if sheet.mode == "vector" and (s.method == "dxf_units" or exact_consensus):
        return "T1"
    if s.method in ("dimension_consensus", "scale_bar", "user") and s.confidence >= 0.8:
        return "T2"
    return "T3"


def apply_confirmation(model: BuildingModel, confirmed_ids: set | None = None) -> None:
    tau = TAU_VECTOR if model.sheet.mode == "vector" else TAU_RASTER
    for e in model.elements:
        if confirmed_ids and e.id in confirmed_ids:
            e.confirmed = True
            e.attrs["confirmed_by"] = "user"
        elif e.prov.confidence >= tau:
            e.confirmed = True
            e.attrs["confirmed_by"] = f"threshold {tau}"
        else:
            e.confirmed = False
            e.attrs["needs_confirmation"] = True


def calibrate_threshold(scores: list[float], correct: list[bool], risk: float = 0.05) -> float | None:
    """Smallest tau such that at most ``risk`` of elements with confidence >= tau are wrong
    (finite-sample correction in the spirit of conformal risk control, Mossina et al.)."""
    pairs = sorted(zip(scores, correct), reverse=True)
    best = None
    wrong = 0
    for k, (s, ok) in enumerate(pairs, start=1):
        wrong += 0 if ok else 1
        if (wrong + 1) / (k + 1) <= risk:
            best = s
    return best
