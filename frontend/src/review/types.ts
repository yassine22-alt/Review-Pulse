export type Point = [number, number];

export interface FindingShape {
  n: number; id: string | null; anchor: Point | null;
  polygons: Point[][]; polylines: Point[][]; points: Point[]; subjects: string[]; deciding: string[];
}
export interface SheetView {
  index: number; id: string; width: number; height: number;
  elements: { id: string; cls: string; line?: Point[]; poly?: Point[] }[];
  rooms: { id: string; label: string | null; poly: Point[] }[];
  findings: FindingShape[];
}
export interface View { sheets: SheetView[] }
export interface RawFinding { rule_id: string; verdict: string; source?: { clause?: string } | null }

export interface Fact { subject?: string; statement: string; source: string }
export interface Item {
  key: string; clause: string; n: number | null; citation: string; quote: string; title: string;
  discipline: string; discipline_label: string; status: string; status_label: string; outcome: string;
  wording: string; wording_default: string; question: string; facts: Fact[];
  locations: { sheet: string; where: string }[]; more_locations: number; dropped: boolean;
  review: { action: "pending" | "accept" | "edit" | "drop"; by: string | null };
}
export interface CorrectionList {
  cycle: number; items: Item[]; approved_count: number; uncovered_clauses: number;
  overall: { label: string; signed: string | null; unsigned_disciplines: string[] };
  disciplines: Record<string, {
    label: string; items: number; proposed: string; differs: boolean;
    signed: { reviewer: string; result: string; at: string } | null;
  }>;
  deferred: { clause: string; quote: string; citation: string; by: string }[];
  edit_burden: { items: number; accepted: number; edited: number; dropped: number; unreviewed: number };
}

export interface Clause { id: string; heading: string; text: string }
export interface Reading {
  status: "DRAFTED" | "UNRESOLVED"; reason?: string; plain?: string; readback?: string;
  plain_applies_when?: string; plain_unless?: string; notes?: string[];
  preview?: { outcome: string; missing?: string[] };
  review?: { review?: { issues?: { message: string }[]; limitations?: string[] } };
  decision?: { state: "approved" | "rejected"; by: string; at: string } | null;
}

/** The places on the sheets that carry the evidence of one correction item: one shape per finding behind it. */
export function shapesOf(item: Item, view: View | null, findings: RawFinding[]) {
  const mine = new Set(findings.map((f, n) => ((f.source?.clause === item.clause || f.rule_id === item.key) ? n : -1))
    .filter((n) => n >= 0));
  return (view?.sheets ?? []).flatMap((s) => s.findings.filter((g) => mine.has(g.n) && drawable(g))
    .map((shape) => ({ sheet: s.index, shape })));
}

/** Whether something of this shape appears on the sheet: a pin, an outline, a line or a point. */
const drawable = (g: FindingShape) => !!g.anchor || g.polygons.length + g.polylines.length + g.points.length > 0;

export type Box = [number, number, number, number];

/** The box around a shape and the elements it is about, in the sheet's pixels. */
export function boundsOf(sheet: SheetView, shapes: FindingShape[]): Box | null {
  const pts: Point[] = [];
  for (const g of shapes) {
    pts.push(...g.polygons.flat(), ...g.polylines.flat(), ...g.points);
    if (g.anchor) pts.push(g.anchor);
    const ids = new Set(g.subjects);
    for (const e of sheet.elements) if (ids.has(e.id)) pts.push(...(e.line ?? e.poly ?? []));
    for (const r of sheet.rooms) if (ids.has(r.id)) pts.push(...r.poly);
  }
  if (!pts.length) return null;
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  const x = Math.min(...xs);
  const y = Math.min(...ys);
  return [x, y, Math.max(...xs) - x, Math.max(...ys) - y];
}
