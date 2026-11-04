"""Raster page -> BuildingModel (R13). Same output contract as the vector path.

    page (PDF raster page or image) -> R4 deskew/binarise -> OCR words -> R6 text classes
    -> thin line segments (LSD) as primitives, so R7 dimension consensus works on scans
    -> wall/door/window masks: learned model, rule baseline, or fusion
    -> elements (walls, doors, windows) -> R10 rooms from the mask barrier -> R14 tiers.
A raster sheet is never T1, so FAIL is only possible for confirmed elements (policy J2).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ...annotate.scale import paper_mm_assumed, recover_scale
from ...annotate.text_classify import classify_items
from ...core.ids import IdFactory
from ...core.tiers import apply_confirmation, tier
from ...ingest import raster_prep
from ...schema import BuildingModel, Primitive, Prov, Scale, Sheet
from .vectorize import barrier_from_masks, opening_elements, wall_elements

FUSION_MAX_OVERLAP = 0.4
WALL_PRIOR_M = 0.20        # typical wall thickness, ruler of last resort on scans
DOOR_WIDTH_M = (0.6, 1.3)  # plausible median door width; a scale implying otherwise is not trusted


def load_page(sheet: Sheet) -> tuple[np.ndarray, float]:
    src = Path(sheet.source_file)
    if src.suffix.lower() == ".pdf":
        return raster_prep.render_pdf_page(src, sheet.page)
    return raster_prep.load_image(src)


def line_primitives(binary: np.ndarray, affine, sheet_id: str, max_width_px: float) -> list[Primitive]:
    """Thin straight segments (LSD) as line primitives in sheet space (for dimension pairing)."""
    import cv2

    lsd = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD)
    img = np.where(binary, 0, 255).astype(np.uint8)
    lines, widths, _p, _n = lsd.detect(img)
    if lines is None:
        return []
    a, b, c, d, e, f = affine
    mm = abs(a)
    ids = IdFactory(sheet_id + ":lsd")
    out = []
    for (x1, y1, x2, y2), w in zip(lines.reshape(-1, 4), (widths if widths is not None else np.ones((len(lines), 1))).reshape(-1)):
        if w > max_width_px:
            continue
        p = (round(a * x1 + b * y1 + c, 3), round(d * x1 + e * y1 + f, 3))
        q = (round(a * x2 + b * y2 + c, 3), round(d * x2 + e * y2 + f, 3))
        if p != q:
            # no width: LSD's support-region width is not the stroke width (thin lines are kept
            # by max_width_px above), and a measured-looking width would mislead R7's PDF filters
            out.append(Primitive(id=ids("line", p, q), kind="line", pts=[p, q], width=None,
                                 prov=Prov(source="raster", stage="lsd", confidence=0.7,
                                           evidence={"lsd_width_mm": round(float(w) * mm, 3)})))
    return out


def fuse(model_wall: np.ndarray, rule_wall: np.ndarray, min_px: int = 40) -> np.ndarray:
    """Model walls as the base; rule-wall components that the model missed (overlap < 40%) and
    that are real ink (rule walls are by construction) are added (Zhang 2026 emit-vs-detect idea)."""
    from scipy import ndimage

    lab, n = ndimage.label(rule_wall)
    out = model_wall.copy()
    if n == 0:
        return out
    sizes = ndimage.sum(np.ones_like(lab), lab, index=np.arange(1, n + 1))
    overl = ndimage.sum(model_wall, lab, index=np.arange(1, n + 1))
    for k in np.nonzero((sizes >= min_px) & (overl < FUSION_MAX_OVERLAP * sizes))[0]:
        out |= lab == (k + 1)
    return out


def check_scale_with_doors(sheet: Sheet, scale: Scale, doors: list, mpu: float) -> Scale:
    """Doors are the most standard-sized element on a plan: a scale under which the median detected
    door (>= 3 doors) is narrower than 0.6 m or wider than 1.3 m is wrong, however well its own
    candidates agree (dimension lines split by their text agree with each other at half length).
    Then the title block's scale is used if doors are plausible under it; otherwise the scale stays
    but below T2 confidence. A user calibration is never overridden. Returns ``scale`` unchanged
    when it passes."""
    from statistics import median

    from ...annotate.scale import title_block_scale

    widths = [e.attrs["width_m"] / mpu for e in doors if e.attrs.get("width_m")]
    if len(widths) < 3 or not scale.metres_per_unit or scale.method == "user":
        return scale
    w = median(widths)                                   # sheet units (paper mm on scans)

    def plausible(m: float) -> bool:
        return DOOR_WIDTH_M[0] <= w * m <= DOOR_WIDTH_M[1]

    if plausible(scale.metres_per_unit):
        return scale
    found = f"median door {w * scale.metres_per_unit:.2f} m under the {scale.method} scale"
    tb = title_block_scale(sheet.texts) if sheet.coord_unit == "paper_mm" else None
    if tb and plausible(tb / 1000) and scale.method != "title_block":
        sheet.warnings.append(f"{found}: implausible, title block 1:{tb} used instead (doors {w * tb / 1000:.2f} m)")
        return Scale(metres_per_unit=tb / 1000, method="title_block", confidence=0.7)
    sheet.warnings.append(f"{found}: implausible, scale kept as an estimate (tier T3); verify the scale")
    return scale.model_copy(update={"confidence": min(scale.confidence, 0.5)})


def build_raster_model(sheet: Sheet, method: str = "auto", ocr: bool = True, calibrate=None,
                       confirmed: set | None = None) -> BuildingModel:
    from ...perception.rooms import detect_rooms
    from .rules import close_doorways, wall_mask_rules
    from .segment import model_available, predict_refined

    gray, dpi = load_page(sheet)
    page = raster_prep.prepare(gray, dpi)
    H, W = page.gray.shape
    sheet.mode = "raster"
    sheet.coord_unit = "paper_mm"
    sheet.width, sheet.height = W * 25.4 / dpi, H * 25.4 / dpi
    sheet.warnings = [w for w in sheet.warnings if "raster path (R13) required" not in w]
    if abs(page.skew_deg) > 0:
        sheet.warnings.append(f"page deskewed by {page.skew_deg:.2f} deg")

    words = []
    if ocr:
        from ...ingest.ocr import available_backends, read_page, to_text_items

        if available_backends():
            words = read_page(page.gray)
            sheet.texts = to_text_items(words, page.affine, sheet.id)
            classify_items(sheet.texts)
            from ...annotate.label_llm import apply_llm_labels

            n = apply_llm_labels(sheet.texts)
            if n:
                sheet.warnings.append(f"{n} room label(s) read by the local language model (verify room types)")
        else:
            sheet.warnings.append("no OCR backend installed: labels and dimensions not read")
    rule_wall, t_px = wall_mask_rules(page.binary, [w.box for w in words], gray=page.gray)
    sheet.primitives = line_primitives(page.binary, page.affine, sheet.id, max_width_px=max(2.0, 0.5 * t_px))

    use_model = method in ("model", "fusion") or (method == "auto" and model_available())
    prob = None
    if use_model:
        prob, cls, _s, t_model = predict_refined(page.gray, page.binary)
        t_px = t_model or t_px          # the learned wall mask measures walls, not their outlines

    scale, _rep = recover_scale(sheet, calibrate)
    if scale.metres_per_unit is None and t_px:
        # no readable dimensions: walls are the ruler (typical wall ~0.20 m); estimated, tier T3
        scale = Scale(metres_per_unit=WALL_PRIOR_M / (t_px * abs(page.affine[0])), method="symbol_prior",
                      confidence=0.4)
        sheet.warnings.append(f"scale estimated from wall thickness ({t_px:.1f} px = {WALL_PRIOR_M} m): "
                              "metric rules give at most WARNING")
    sheet.scale = scale
    scale_known = scale.metres_per_unit is not None
    mpu = scale.metres_per_unit or paper_mm_assumed(sheet)
    if not scale_known:
        sheet.warnings.append("scale unknown on this raster page: metric rules give at most WARNING")

    if use_model:
        wall = cls == 1
        door, window = cls == 2, cls == 3
        # fusion only on request: on CubiCasa test it lowers wall precision (0.93 -> 0.74) and
        # room F1 (0.87 -> 0.82) because the added rule walls are mostly furniture and text
        if method == "fusion":
            wall = fuse(wall, rule_wall & ~door & ~window)
        stage = "raster_fusion" if method == "fusion" else "raster_model"
    else:
        wall, door, window = rule_wall, np.zeros_like(rule_wall), np.zeros_like(rule_wall)
        stage = "raster_rules"
        sheet.warnings.append("no raster model: rule baseline only (doors/windows not detected)")

    walls = wall_elements(wall, prob[1] if prob is not None else None, page.affine, sheet.id, stage, stage)
    doors = opening_elements(door, "door", prob[2] if prob is not None else None, page.affine, sheet.id,
                             mpu, stage)
    windows = opening_elements(window, "window", prob[3] if prob is not None else None, page.affine, sheet.id,
                               mpu, stage)
    checked = check_scale_with_doors(sheet, scale, doors, mpu)
    if checked is not scale:
        scale = sheet.scale = checked
        if scale.metres_per_unit != mpu:
            mpu = scale.metres_per_unit
            doors = opening_elements(door, "door", prob[2] if prob is not None else None, page.affine, sheet.id,
                                     mpu, stage)
            windows = opening_elements(window, "window", prob[3] if prob is not None else None, page.affine,
                                       sheet.id, mpu, stage)
    barrier_wall = wall if use_model else close_doorways(wall, t_px)
    barrier = barrier_from_masks(barrier_wall, door, window, page.affine)
    rooms, edges, warn = detect_rooms(sheet, walls, [], doors + windows, mpu, scale_known, barrier=barrier)
    sheet.warnings += warn
    model = BuildingModel(sheet=sheet, elements=walls + doors + windows, rooms=rooms, edges=edges)
    model.tier = tier(sheet)
    apply_confirmation(model, confirmed)
    model.sheet.layout.plan_box = None
    return model
