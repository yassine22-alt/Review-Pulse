"""R3 - DXF extraction (D3). DWG is converted through the ODA File Converter.

Output uses ``coord_unit = "drawing_unit"``; the scale comes from $INSUNITS.
"""

from __future__ import annotations

import math
from pathlib import Path

from ..core.ids import IdFactory
from ..schema import Dimension, Primitive, Prov, Scale, Sheet, TextItem
from .classify import IngestError

MAX_INSERT_DEPTH = 8
SPLINE_FLATTEN = 0.01        # drawing units; refined by the caller if needed


def open_dxf(path: Path):
    """Return (doc, warnings). DWG goes through ezdxf.addons.odafc."""
    import ezdxf
    from ezdxf import recover

    warnings: list[str] = []
    if path.suffix.lower() == ".dwg":
        from ezdxf.addons import odafc

        if not odafc.is_installed():
            raise IngestError(f"{path.name}: DWG needs the ODA File Converter (install it or export DXF)")
        return odafc.readfile(str(path)), warnings
    try:
        doc, auditor = recover.readfile(str(path))
    except (OSError, ezdxf.DXFStructureError) as e:
        raise IngestError(f"{path.name}: cannot read DXF ({e})") from e
    if auditor.has_errors:
        warnings.append(f"dxf auditor found {len(auditor.errors)} errors (recovered)")
    return doc, warnings


def insunits_to_metres(code: int) -> float | None:
    from ezdxf import units

    if not code:
        return None
    try:
        return units.conversion_factor(code, units.M)
    except (KeyError, IndexError, ValueError):
        return None


UNIT_NAMES = {"mm": 4, "cm": 5, "m": 6, "in": 1, "ft": 2}


class DxfExtractor:
    def __init__(self, sheet_id: str, units_override: str | None = None):
        self.sheet_id = sheet_id
        self.ids = IdFactory(sheet_id)
        self.prims: list[Primitive] = []
        self.texts: list[TextItem] = []
        self.dims: list[Dimension] = []
        self.units_override = units_override
        self.hidden_layers: set[str] = set()
        self.warn: list[str] = []
        self.cur_insert: str | None = None   # handle of the outermost INSERT being expanded
        self._seen_lines: dict = {}
        self.cur_entity: str | None = None     # polyline whose pieces are being expanded

    # -- helpers -------------------------------------------------------
    def _prov(self, e, block, extra=None):
        ev = {"handle": e.dxf.handle, "dxftype": e.dxftype()}
        if block:
            ev["block"] = block
        if self.cur_insert:
            ev["insert_handle"] = self.cur_insert
        if self.cur_entity:
            ev["entity"] = self.cur_entity
        if extra:
            ev.update(extra)
        return Prov(source="vector", stage="dxf_extract", evidence=ev)

    def _common(self, e, block):
        layer = e.dxf.get("layer", "0")
        return dict(layer=layer, block=block, hidden=layer in self.hidden_layers,
                    width=None, prov=self._prov(e, block))

    @staticmethod
    def _xy(v) -> tuple[float, float]:
        return (round(float(v[0]), 6), round(float(v[1]), 6))

    def _line(self, a, b, e, block):
        a, b = self._xy(a), self._xy(b)
        if a == b:
            return
        # identical segments (shared extension lines, overlapping exports) are kept once with a count
        key = (min(a, b), max(a, b), block is not None and block.startswith("dim:"))
        if key in self._seen_lines:
            ev = self._seen_lines[key].prov.evidence
            ev["dup_count"] = ev.get("dup_count", 1) + 1
            return
        prim = Primitive(id=self.ids("line", a, b), kind="line", pts=[a, b], **self._common(e, block))
        self._seen_lines[key] = prim
        self.prims.append(prim)

    # -- entities ------------------------------------------------------
    def walk(self, entities, block: str | None = None, depth: int = 0):
        for e in entities:
            try:
                self._entity(e, block, depth)
            except Exception as ex:  # noqa: BLE001 - one bad entity must not stop the sheet
                self.warn.append(f"skipped {e.dxftype()} {e.dxf.get('handle', '?')}: {ex}")

    def _entity(self, e, block, depth):
        t = e.dxftype()
        if t == "LINE":
            self._line(e.dxf.start, e.dxf.end, e, block)
        elif t == "ARC":
            # centre and angles are in the entity's OCS; mirrored blocks give extrusion (0, 0, -1)
            ocs = e.ocs()
            c = self._xy(ocs.to_wcs(e.dxf.center))
            r = float(e.dxf.radius)
            sp, ep = e.start_point, e.end_point            # WCS
            a_s = math.degrees(math.atan2(sp[1] - c[1], sp[0] - c[0])) % 360
            a_e = math.degrees(math.atan2(ep[1] - c[1], ep[0] - c[0])) % 360
            a0, a1 = (a_s, a_e) if e.dxf.extrusion[2] >= 0 else (a_e, a_s)
            self.prims.append(Primitive(id=self.ids("arc", c, r, a0), kind="arc", center=c, radius=r,
                                        a0=round(a0, 6), a1=round(a1, 6), **self._common(e, block)))
        elif t == "CIRCLE":
            c = self._xy(e.ocs().to_wcs(e.dxf.center))
            self.prims.append(Primitive(id=self.ids("circle", c, e.dxf.radius), kind="circle", center=c,
                                        radius=float(e.dxf.radius), **self._common(e, block)))
        elif t == "ELLIPSE":
            self._ellipse(e, block)
        elif t in ("LWPOLYLINE", "POLYLINE"):
            # pieces of one polyline keep its identity (closed outlines matter to perception)
            prev, self.cur_entity = self.cur_entity, f"{self.cur_insert or ''}/{e.dxf.handle}"
            try:
                self.walk(e.virtual_entities(), block, depth)
            finally:
                self.cur_entity = prev
        elif t == "SPLINE":
            pts = [self._xy(p) for p in e.flattening(SPLINE_FLATTEN)]
            self.prims.append(Primitive(id=self.ids("polyline", pts), kind="polyline", pts=pts,
                                        **self._common(e, block)))
        elif t == "HATCH":
            from ezdxf import path as ezpath

            for p in ezpath.from_hatch(e):
                pts = [self._xy(v) for v in p.flattening(SPLINE_FLATTEN)]
                if len(pts) >= 3:
                    self.prims.append(Primitive(id=self.ids("polygon", pts), kind="polygon", pts=pts, filled=True,
                                                **self._common(e, block)))
        elif t in ("SOLID", "TRACE"):
            v = [self._xy(e.dxf.get(k)) for k in ("vtx0", "vtx1", "vtx3", "vtx2") if e.dxf.hasattr(k)]
            self.prims.append(Primitive(id=self.ids("polygon", v), kind="polygon", pts=v, filled=True,
                                        **self._common(e, block)))
        elif t == "INSERT":
            name = e.dxf.name
            if depth >= MAX_INSERT_DEPTH:
                return
            outer = self.cur_insert is None
            if outer:
                self.cur_insert = e.dxf.handle
            try:
                self.walk(e.virtual_entities(), block or name, depth + 1)
                for a in e.attribs:
                    self._text(a, a.dxf.text, block or name)
            finally:
                if outer:
                    self.cur_insert = None
        elif t == "TEXT":
            self._text(e, e.dxf.text, block)
        elif t == "MTEXT":
            self._text(e, e.plain_text(), block)
        elif t == "DIMENSION":
            self._dimension(e)

    def _ellipse(self, e, block):
        major = e.dxf.major_axis
        r = math.hypot(major[0], major[1])
        if abs(float(e.dxf.ratio) - 1.0) < 1e-6:
            # circular ellipse (e.g. an arc inside a mirrored block): store as ARC
            c = self._xy(e.dxf.center)
            rot = math.degrees(math.atan2(major[1], major[0]))
            s0, s1 = math.degrees(e.dxf.start_param), math.degrees(e.dxf.end_param)
            if e.dxf.extrusion[2] < 0:
                s0, s1 = -s1, -s0
            self.prims.append(Primitive(id=self.ids("arc", c, r, s0), kind="arc", center=c, radius=r,
                                        a0=(rot + s0) % 360, a1=(rot + s1) % 360, **self._common(e, block)))
            return
        pts = [self._xy(p) for p in e.flattening(SPLINE_FLATTEN)]
        self.prims.append(Primitive(id=self.ids("polyline", pts), kind="polyline", pts=pts,
                                    **self._common(e, block)))

    def _text(self, e, text, block):
        from ezdxf import bbox

        text = (text or "").strip()
        if not text:
            return
        ext = bbox.extents([e], fast=True)
        if ext.has_data:
            box = (round(ext.extmin.x, 6), round(ext.extmin.y, 6), round(ext.extmax.x, 6), round(ext.extmax.y, 6))
        else:
            x, y = self._xy(e.dxf.insert)
            box = (x, y, x, y)
        height = e.dxf.get("char_height") if e.dxftype() == "MTEXT" else e.dxf.get("height")
        self.texts.append(TextItem(id=self.ids("text", text, box), text=text, bbox=box,
                                   rotation_deg=float(e.dxf.get("rotation", 0.0)) % 360,
                                   height=float(height) if height else None, layer=e.dxf.get("layer"),
                                   prov=self._prov(e, block)))

    def _dimension(self, e):
        tag = f"dim:{e.dxf.handle}"
        try:
            measured = float(e.get_measurement())
        except Exception:  # noqa: BLE001 - angular/ordinate dims are not lengths
            measured = None
        override = e.dxf.get("text", "")
        p1 = self._xy(e.dxf.get("defpoint2", (0, 0)))
        p2 = self._xy(e.dxf.get("defpoint3", (0, 0)))
        stated = None
        if override and override.strip() and override not in ("<>",):
            from ..annotate.text_classify import classify, dimension_metres

            c = classify(override.replace("<>", "").strip())
            if c.kind == "dimension" and c.value is not None:
                stated = dimension_metres(c.value, c.unit)
        self.dims.append(Dimension(
            id=self.ids("dim", p1, p2), value_m=stated, measured_m=measured, p1=p1, p2=p2,
            prov=Prov(source="vector", stage="dxf_extract",
                      evidence={"handle": e.dxf.handle, "override": override, "measurement_units": measured}),
        ))
        try:
            self.walk(e.virtual_entities(), tag, 1)
        except Exception:  # noqa: BLE001 - dimension without a block
            pass


def extract_dxf(path: Path, sheet_id: str, units: str | None = None) -> Sheet:
    doc, warnings = open_dxf(path)
    ex = DxfExtractor(sheet_id, units)
    for layer in doc.layers:
        if layer.is_off() or layer.is_frozen():
            ex.hidden_layers.add(layer.dxf.name)
    msp = doc.modelspace()
    if len(msp) == 0:
        for lay in doc.layouts:
            if lay.name != "Model" and len(lay):
                warnings.append(f"model space empty but layout {lay.name!r} has content (paper space ignored)")
    ex.walk(msp)
    warnings += ex.warn

    insunits = int(doc.header.get("$INSUNITS", 0))
    mpu = insunits_to_metres(UNIT_NAMES[units]) if units else insunits_to_metres(insunits)
    if mpu is None:
        warnings.append("unitless DXF ($INSUNITS=0): pass --units mm|cm|m")
        scale = Scale()
    else:
        scale = Scale(metres_per_unit=mpu, method="dxf_units" if not units else "user", confidence=1.0)
        # DIMENSION measurements are in drawing units: convert, then check against the drawn length
        for d in ex.dims:
            if d.measured_m is not None:
                d.measured_m = d.measured_m * mpu
            if d.value_m is None and d.measured_m is not None:
                d.value_m = d.measured_m
    ext_pts = [p for pr in ex.prims for p in pr.pts] + [pr.center for pr in ex.prims if pr.center]
    if ext_pts:
        xs, ys = [p[0] for p in ext_pts], [p[1] for p in ext_pts]
        width, height = max(xs) - min(xs), max(ys) - min(ys)
    else:
        width = height = 0.0
    return Sheet(id=sheet_id, source_file=str(path), page=0, mode="vector", coord_unit="drawing_unit",
                 width=round(width, 6), height=round(height, 6), scale=scale, primitives=ex.prims,
                 texts=ex.texts, dimensions=ex.dims, layers=[ly.dxf.name for ly in doc.layers],
                 warnings=warnings)


def dimension_drawn_check(sheet: Sheet, tol: float = 0.01) -> list[str]:
    """R7.1: for DXF with known units, measured and drawn lengths should agree within 1%."""
    out = []
    mpu = sheet.scale.metres_per_unit
    if not mpu:
        return out
    for d in sheet.dimensions:
        drawn = math.dist(d.p1, d.p2) * mpu
        if d.measured_m and drawn > 0 and abs(drawn - d.measured_m) > tol * d.measured_m:
            out.append(f"dimension {d.id}: measured {d.measured_m:.3f} m vs points {drawn:.3f} m")
    return out
