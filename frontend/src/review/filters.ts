import { shapesOf, type Item, type Point, type SheetView, type View } from "./types";

export const SEVERITY: Record<string, string> = { critical: "Critical", major: "Major", minor: "Minor", info: "For information", "": "Not rated" };
export const FAMILY: Record<string, string> = {
  document: "From your document", reviewer: "Written by a reviewer", C: "Built-in: sizes and access",
  K: "Built-in: consistency", P: "Built-in: completeness", Q: "Built-in: drawing quality", other: "Built-in: other",
};

const centre = (p: Point[]) => [p.reduce((a, q) => a + q[0], 0) / p.length, p.reduce((a, q) => a + q[1], 0) / p.length] as Point;

function inside([x, y]: Point, poly: Point[]) {
  let hit = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i], [xj, yj] = poly[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) hit = !hit;
  }
  return hit;
}

function distance([x, y]: Point, poly: Point[]) {
  let best = Infinity;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [ax, ay] = poly[j], [dx, dy] = [poly[i][0] - ax, poly[i][1] - ay];
    const t = Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy || 1)));
    best = Math.min(best, Math.hypot(x - ax - t * dx, y - ay - t * dy));
  }
  return best;
}

const roomName = (s: SheetView, i: number) => s.rooms[i].label || `Room without a label ${i + 1} (sheet ${s.index + 1})`;

/** The rooms an item is about: those it names, and those an element it names stands in or against. A door sits in the wall
 *  between two rooms, so "against" means no further than half the element's own length. */
export function roomsOf(item: Item, view: View | null): string[] {
  const found = new Set<string>();
  for (const { sheet, shape } of shapesOf(item, view)) {
    const s = view?.sheets.find((x) => x.index === sheet);
    if (!s) continue;
    const ids = new Set(shape.subjects);
    s.rooms.forEach((r, i) => { if (ids.has(r.id)) found.add(roomName(s, i)); });
    for (const e of s.elements) {
      if (!ids.has(e.id) || e.cls === "wall") continue;
      const pts = e.line ?? e.poly ?? [];
      if (!pts.length) continue;
      const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
      const reach = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)) / 2;
      const c = centre(pts);
      s.rooms.forEach((r, i) => { if (r.poly.length > 2 && (inside(c, r.poly) || distance(c, r.poly) <= reach)) found.add(roomName(s, i)); });
    }
  }
  return [...found].sort();
}
