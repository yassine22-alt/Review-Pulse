"""Pairs of versions with the truth known by construction. A plan from `synth.make_plan` is the old version; the new version is
the same plan regenerated without the planted error (a door widened) or the same PDF edited with PyMuPDF (a note added, a room
renamed, a sheet renumbered, a view moved, an unrelated change, a change in the wrong place). Comments are planted on the old
version with the status the edit must produce."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from ..synth.make_plan import make_plan
from .model import CANNOT_TELL, CHANGED_NOT_SETTLED, MOVED, NOT_ADDRESSED, RESOLVED, Comment

BAND = 70.0
NOTE = "ALL DOORS SHALL HAVE 0.90 M MINIMUM CLEAR WIDTH"
WRONG_NOTE = "CONTRACTOR TO VERIFY ALL DIMENSIONS ON SITE"


@dataclass
class Case:
    name: str
    old: str
    new: str
    comments: list[Comment]
    expect: dict[str, str]                      # comment id -> expected status
    new_issues: int = 0                         # changed places no comment asked for
    not_clouded: int | None = None              # None: the new PDF has no clouds
    note: str = ""
    extra: dict = field(default_factory=dict)


# ---- editing helpers --------------------------------------------------------------------------------------------------------

def sheetize(src: str | Path, out: str | Path, number: str, title: str = "FLOOR PLAN") -> Path:
    """The plan page with a title block band under it (sheet number, title, project) so the drawing set model reads a number."""
    s = pymupdf.open(str(src))
    W, H = s[0].rect.width, s[0].rect.height
    d = pymupdf.open()
    p = d.new_page(width=W, height=H + BAND)
    p.show_pdf_page(pymupdf.Rect(0, 0, W, H), s, 0)
    p.draw_rect(pymupdf.Rect(W - 330, H + 6, W - 8, H + BAND - 6), color=(0, 0, 0), width=0.8)
    p.insert_text((W - 320, H + 22), "PROJECT", fontsize=6)
    p.insert_text((W - 320, H + 40), "SYNTH HOUSE", fontsize=9)
    p.insert_text((W - 230, H + 22), "SHEET TITLE", fontsize=6)
    p.insert_text((W - 230, H + 40), title, fontsize=10)
    p.insert_text((W - 120, H + 22), "SHEET NUMBER", fontsize=6)
    p.insert_text((W - 120, H + 44), number, fontsize=16)
    d.save(str(out))
    return Path(out)


def words_of(pdf: str | Path, page: int = 0) -> list[tuple[float, float, float, float, str]]:
    with pymupdf.open(str(pdf)) as d:
        return [(w[0], w[1], w[2], w[3], w[4]) for w in d[page].get_text("words")]


def find_word(pdf, text: str, left_of: float | None = None, right_of: float | None = None, near=None):
    cands = [w for w in words_of(pdf) if w[4] == text]
    if left_of is not None:
        cands = [w for w in cands if w[0] < left_of]
    if right_of is not None:
        cands = [w for w in cands if w[0] > right_of]
    if near is not None:
        cands.sort(key=lambda w: (w[0] - near[0]) ** 2 + (w[1] - near[1]) ** 2)
    return cands[0] if cands else None


def box_around(w, pad=26.0):
    return (round(w[0] - pad, 1), round(w[1] - pad, 1), round(w[2] + pad, 1), round(w[3] + pad, 1))


def edit_text(src, out, old_box, new_text: str) -> None:
    """Replace the text inside `old_box` by `new_text` (the old words are redacted, line art is kept)."""
    d = pymupdf.open(str(src))
    p = d[0]
    r = pymupdf.Rect(old_box)
    if _has_text(p, r):
        p.add_redact_annot(r + (-0.5, -0.5, 0.5, 0.5))
        p.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
    if new_text:
        p.insert_text((r.x0, r.y1 - 1), new_text, fontsize=max(5.0, (r.y1 - r.y0) * 0.85), fontname="helv")
    d.save(str(out))


def _has_text(page, r) -> bool:
    return bool(page.get_text("words", clip=r))


def add_note(src, out, at, text: str, fontsize=7.0) -> None:
    d = pymupdf.open(str(src))
    d[0].insert_text(at, text, fontsize=fontsize, fontname="helv")
    d.save(str(out))


def add_cloud(src, out, rects: list[tuple[float, float, float, float]]) -> None:
    """A revision cloud as Bluebeam writes it: a polygon annotation with a /BE cloud border effect."""
    d = pymupdf.open(str(src))
    p = d[0]
    for r in rects:
        a = p.add_polygon_annot([(r[0], r[1]), (r[2], r[1]), (r[2], r[3]), (r[0], r[3])])
        a.set_colors(stroke=(1, 0, 0))
        a.set_border(width=1.5)
        a.update()
        d.xref_set_key(a.xref, "BE", "<</S/C/I 2>>")
    d.save(str(out))


def shift_page(src, out, dx: float, dy: float, rotate: int = 0, pad: float = 80.0) -> None:
    """The whole page drawn again, shifted (and turned in the content by `rotate` degrees), on a bigger page."""
    s = pymupdf.open(str(src))
    W, H = s[0].rect.width, s[0].rect.height
    d = pymupdf.open()
    if rotate % 180:
        p = d.new_page(width=H + 2 * pad, height=W + 2 * pad)
        p.show_pdf_page(pymupdf.Rect(pad, pad, pad + H, pad + W), s, 0, rotate=rotate)
    else:
        p = d.new_page(width=W + 2 * pad, height=H + 2 * pad)
        p.show_pdf_page(pymupdf.Rect(pad + dx, pad + dy, pad + dx + W, pad + dy + H), s, 0, rotate=rotate)
    d.save(str(out))


def combine_views(plan: str | Path, table_pdf: str | Path, out: str | Path, table_at: tuple[float, float],
                  clip) -> tuple[float, float, float, float]:
    """A sheet with a plan and a small second view (a clipped part of another sheet) at `table_at`. Returns the view's box."""
    s = pymupdf.open(str(plan))
    t = pymupdf.open(str(table_pdf))
    W, H = s[0].rect.width, s[0].rect.height
    d = pymupdf.open()
    p = d.new_page(width=W + 360, height=H + BAND)
    p.show_pdf_page(pymupdf.Rect(0, 0, W, H), s, 0)
    c = pymupdf.Rect(clip)
    box = pymupdf.Rect(table_at[0], table_at[1], table_at[0] + c.width, table_at[1] + c.height)
    p.show_pdf_page(box, t, 0, clip=c)
    d.save(str(out))
    return (box.x0, box.y0, box.x1, box.y1)


# ---- cases ------------------------------------------------------------------------------------------------------------------

def _plan(dir_: Path, seed: int, name: str, errors=()) -> tuple[str, dict]:
    out = make_plan(dir_, seed=seed, errors=tuple(errors), png=False, name=name)
    return out["pdf"], json.loads(Path(out["truth"]).read_text(encoding="utf-8"))


def _door_tag(truth: dict, door_id: str) -> str:
    return next(o["tag"] for o in truth["openings"] if o["id"] == door_id)


def _door_comment(cid: str, pdf: str, tag: str, with_tag_text: bool) -> Comment:
    w = find_word(pdf, tag, left_of=500)
    txt = (f"Door {tag} clear width is under the 0.80 m minimum. Provide at least 0.80 m clear width. (IBC 1010.1.1)"
           if with_tag_text else "Entry door to this bedroom is too narrow. Door clear width shall be a minimum of 0.80 m. (IBC 1010.1.1)")
    return Comment(cid, txt, "IBC 1010.1.1", sheet="A-101", page=1, bbox=box_around(w, 22.0))


def make_cases(work: str | Path, seeds=(12, 13, 14, 15)) -> list[Case]:
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    cases: list[Case] = []
    for seed in seeds:
        d = work / f"s{seed}"
        d.mkdir(exist_ok=True)
        narrow, t_n = _plan(d, seed, "narrow", ("metric_door_narrow",))
        clean, _t_c = _plan(d, seed, "clean")
        unl, t_u = _plan(d, seed, "unlabelled", ("comp_unlabelled_room",))
        tag = _door_tag(t_n, "door:bed1-corridor")
        o101 = sheetize(narrow, d / "narrow_A101.pdf", "A-101")
        n101 = sheetize(clean, d / "clean_A101.pdf", "A-101")
        o_clean = sheetize(clean, d / "clean_old_A101.pdf", "A-101")
        c_tag = _door_comment("C1", str(o101), tag, True)
        c_box = _door_comment("C1", str(o101), tag, False)

        # 1. the door was widened (geometry and schedule regenerated): RESOLVED, nothing else changed
        cases.append(Case(f"door_widened_s{seed}", str(o101), str(n101), [c_tag], {"C1": RESOLVED}, 0,
                          note="door widened to fix a width comment; the schedule row follows"))
        cases.append(Case(f"door_widened_boxonly_s{seed}", str(o101), str(n101), [c_box], {"C1": RESOLVED}, 0,
                          note="same, comment names no tag, only a box"))
        # 2. door not fixed, an unrelated change far away
        far = (60.0, 30.0)
        add_note(o101, d / "unrelated.pdf", far, "REV B ISSUED FOR COORDINATION")
        cases.append(Case(f"door_unfixed_unrelated_s{seed}", str(o101), str(d / "unrelated.pdf"), [c_tag], {"C1": NOT_ADDRESSED}, 1,
                          note="comment's region unchanged, an unrelated note added elsewhere"))
        # 3. a change in the wrong place: another door row of the schedule edited, the commented door untouched
        other = "P1" if tag != "P1" else "P2"
        wt = find_word(o101, other, right_of=500)
        val = next(w for w in words_of(o101) if abs(w[1] - wt[1]) < 2 and wt[2] + 30 < w[0] < wt[2] + 120 and w[4][:1] == "0" and "," in w[4] and w[4] != "2,10")
        edit_text(o101, d / "wrongplace.pdf", (val[0], val[1], val[2] + 1, val[3]), "1,00")
        cases.append(Case(f"wrong_place_s{seed}", str(o101), str(d / "wrongplace.pdf"), [c_tag], {"C1": NOT_ADDRESSED}, 1,
                          note="the width of a different door was edited; the commented door is as before"))
        # 4. a note requested and added
        blank = (40.0, 14.0)
        cn = Comment("C1", f"Add a note stating '{NOTE}'. (IBC 1010.1.1)", "IBC 1010.1.1", "A-101", 1, (30.0, 4.0, 330.0, 26.0))
        add_note(o_clean, d / "note_added.pdf", blank, NOTE)
        cases.append(Case(f"note_added_s{seed}", str(o_clean), str(d / "note_added.pdf"), [cn], {"C1": RESOLVED}, 0,
                          note="the requested note appears at the asked place"))
        add_note(o_clean, d / "note_wrong_here.pdf", blank, WRONG_NOTE)
        cases.append(Case(f"note_wrong_text_s{seed}", str(o_clean), str(d / "note_wrong_here.pdf"), [cn], {"C1": CHANGED_NOT_SETTLED}, 0,
                          note="a different note was put where the requested one belongs"))
        add_note(o_clean, d / "note_wrong_far.pdf", (60.0, 470.0), WRONG_NOTE)
        cases.append(Case(f"note_wrong_far_s{seed}", str(o_clean), str(d / "note_wrong_far.pdf"), [cn], {"C1": NOT_ADDRESSED}, 1,
                          note="a different note added elsewhere; the asked place is untouched"))
        # 5. a room labelled / renamed
        bed3 = next(r for r in t_u["rooms"] if r["id"] == "bed3")
        # the room has no label in the old version: place the new label where a label would sit (room centre in points)
        k, ox, oy = t_u["pdf_transform"]["k"], t_u["pdf_transform"]["ox"], t_u["pdf_transform"]["oy"]
        pts = bed3["polygon"]
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        pt = 72 / 25.4
        # the page is drawn with y down: y_pt = H_pt - (oy + k * y) * pt
        unl_sheet = sheetize(unl, d / "unl_A101.pdf", "A-101")
        with pymupdf.open(str(unl)) as dd:
            Hpt = dd[0].rect.height
        px, py = (ox + k * cx) * pt, Hpt - (oy + k * cy) * pt
        lab_box = (px - 40, py - 14, px + 40, py + 4)
        c_label = Comment("C1", "Room is not labelled. Label this room 'CHAMBRE 3'. (IBC 1004.1)", "IBC 1004.1", "A-101", 1, lab_box)
        add_note(unl_sheet, d / "labelled.pdf", (px - 22, py), "CHAMBRE 3", fontsize=9)
        cases.append(Case(f"room_labelled_s{seed}", str(unl_sheet), str(d / "labelled.pdf"), [c_label], {"C1": RESOLVED}, 0,
                          note="the missing room label was added"))
        add_note(unl_sheet, d / "mislabelled.pdf", (px - 22, py), "SALON", fontsize=9)
        cases.append(Case(f"room_renamed_wrong_s{seed}", str(unl_sheet), str(d / "mislabelled.pdf"), [c_label], {"C1": CHANGED_NOT_SETTLED}, 0,
                          note="a label was added but not the requested one"))
        kw = find_word(o_clean, "CUISINE")
        c_ren = Comment("C1", "Kitchen label wrong. Rename the room to 'KITCHEN'. (local amendment 4)", "", "A-101", 1, box_around(kw, 6.0))
        edit_text(o_clean, d / "renamed_salon.pdf", (kw[0], kw[1], kw[2], kw[3]), "SALON")
        cases.append(Case(f"room_renamed_other_s{seed}", str(o_clean), str(d / "renamed_salon.pdf"), [c_ren], {"C1": CHANGED_NOT_SETTLED}, 0,
                          note="the room was renamed, not as asked"))
        edit_text(o_clean, d / "renamed_ok.pdf", (kw[0], kw[1], kw[2], kw[3]), "KITCHEN")
        cases.append(Case(f"room_renamed_ok_s{seed}", str(o_clean), str(d / "renamed_ok.pdf"), [c_ren], {"C1": RESOLVED}, 0,
                          note="the room was renamed as asked"))
        # 6. sheet renumbered
        n102 = sheetize(clean, d / "clean_A102.pdf", "A-102")
        c_num = Comment("C1", "Show the door swing clear of the corridor. (IBC 1010.1.4)", "IBC 1010.1.4", "A-101", 1,
                        box_around(find_word(o_clean, "P2", left_of=500), 20.0))
        cases.append(Case(f"sheet_renumbered_s{seed}", str(o_clean), str(n102), [c_num], {"C1": MOVED}, 0,
                          note="only the sheet number changed"))
        # 7. a view moved on the sheet
        sched = find_word(clean, "TABLEAU")
        clip = (sched[0] - 12, sched[1] - 8, sched[0] + 160, sched[1] + 130)
        old_v = d / "views_old.pdf"
        new_v = d / "views_new.pdf"
        vb_old = combine_views(clean, clean, old_v, (780.0, 40.0), clip)
        combine_views(clean, clean, new_v, (800.0, 120.0), clip)
        # the second view repeats words of the first; the comment sits on the second view (a copy of the schedule)
        c_view = Comment("C1", "Door schedule: clear width of every door to be shown in mm. (local amendment 7)", "", None, 1, vb_old)
        cases.append(Case(f"view_moved_s{seed}", str(old_v), str(new_v), [c_view], {"C1": MOVED}, 0,
                          note="a view was moved on the sheet, content unchanged", extra={"box": vb_old}))
        # 8. nothing changed at all
        shutil.copy(o101, d / "identical.pdf")
        cases.append(Case(f"identical_s{seed}", str(o101), str(d / "identical.pdf"), [c_tag, Comment("C2", NOTE.title(), "", "A-101", 1, (30, 4, 330, 26)),
                                                                                       c_label_dummy(o101)],
                          {"C1": NOT_ADDRESSED, "C2": NOT_ADDRESSED, "C3": NOT_ADDRESSED}, 0, note="the same file twice"))
        # 9. shifted and turned pages
        shift_page(o101, d / "shifted.pdf", 33.0, 21.0)
        cases.append(Case(f"shifted_s{seed}", str(o101), str(d / "shifted.pdf"), [c_tag, c_label_dummy(o101)],
                          {"C1": NOT_ADDRESSED, "C3": NOT_ADDRESSED}, 0, note="the whole page moved on a bigger page"))
        shift_page(o101, d / "turned.pdf", 0.0, 0.0, rotate=90)
        cases.append(Case(f"turned_content_s{seed}", str(o101), str(d / "turned.pdf"), [c_tag, c_label_dummy(o101)],
                          {"C1": NOT_ADDRESSED, "C3": NOT_ADDRESSED}, 0, note="the whole drawing turned a quarter turn"))
        dr = pymupdf.open(str(o101))
        dr[0].set_rotation(90)
        dr.save(str(d / "rotflag.pdf"))
        cases.append(Case(f"rotate_flag_s{seed}", str(o101), str(d / "rotflag.pdf"), [c_tag], {"C1": NOT_ADDRESSED}, 0,
                          note="the page /Rotate flag set to 90"))
        # 10. revision clouds: the door fix clouded, the schedule row not
        wp = find_word(n101, tag, left_of=500)
        door_cloud = (wp[0] - 60, wp[1] - 60, wp[2] + 60, wp[3] + 60)
        add_cloud(n101, d / "clouded.pdf", [door_cloud])
        cases.append(Case(f"clouds_partial_s{seed}", str(o101), str(d / "clouded.pdf"), [c_tag], {"C1": RESOLVED}, 0, not_clouded=1,
                          note="the door change is clouded, the schedule change is not", extra={"cloud": door_cloud}))
        # 11. comment on a sheet that was removed from the set
        two = d / "two_old.pdf"
        a = pymupdf.open(str(n101))
        a.insert_pdf(pymupdf.open(str(sheetize(clean, d / "second.pdf", "A-102"))))
        a.save(str(two))
        one = d / "one_new.pdf"
        b = pymupdf.open(str(n101))
        b.save(str(one))
        cases.append(Case(f"sheet_removed_s{seed}", str(two), str(one),
                          [Comment("C1", "Revise the roof drainage note. (IBC 1503.4)", "IBC 1503.4", "A-102", 2, (50, 50, 200, 120))],
                          {"C1": CANNOT_TELL}, 0, note="the commented sheet is gone from the new set"))
    return cases


def c_label_dummy(pdf) -> Comment:
    w = find_word(pdf, "SEJOUR")
    return Comment("C3", "Room name is not in the language of the jurisdiction. (local amendment 2)", "", "A-101", 1, box_around(w, 8.0))
