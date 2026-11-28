import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { boundsOf, type Box, type FindingShape, type Point, type SheetView } from "./types";

export interface Mark { key: string; label: string; tone: string; shapes: FindingShape[] }

const join = (p: Point[]) => p.map((q) => q.join(",")).join(" ");
const still = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** The sheet alone, what the tool read on it, or the evidence of the correction items. */
export type Layer = "plan" | "read" | "corrections";
const LAYERS: [Layer, string][] = [["plan", "Plan only"], ["read", "What was read"], ["corrections", "Corrections"]];

/** Rooms and elements as the tool read them: a reviewer sees what a conclusion could and could not have rested on. */
function Detected({ sheet }: { sheet: SheetView }) {
  return (
    <g className="detected">
      {sheet.rooms.map((r) => (
        <polygon key={r.id} className="room" points={join(r.poly)}><title>{r.label || "room without a label"}</title></polygon>
      ))}
      {sheet.elements.map((e) => e.line
        ? <polyline key={e.id} className={`el ${e.cls}`} points={join(e.line)}><title>{e.cls}</title></polyline>
        : e.poly && <polygon key={e.id} className={`el ${e.cls}`} points={join(e.poly)}><title>{e.cls}</title></polygon>)}
    </g>
  );
}

/** Which reader made the reading, in words; a reviewer weighs what was read, and what was not, by it. */
export const READER: Record<string, (model: string | null) => string> = {
  trained: (m) => `Read with the trained drawing model${m ? ` (${m})` : ""}.`,
  rules: () => "Read with the hand written rules only: the trained drawing model did not run. Expect many missed doors and windows on real drawings.",
  fallback: () => "The trained model found no walls here, so the rules' reading is shown. This drawing style may be new to it.",
  scan: () => "Read from a picture of the drawing, with less certainty than from a vector file.",
};

/** How many of each kind were read, in words; zero is said too, since nothing read is not nothing there. */
export function readSummary(sheet: SheetView): string {
  const counts = new Map<string, number>();
  for (const e of sheet.elements) counts.set(e.cls, (counts.get(e.cls) ?? 0) + 1);
  const parts = [`${sheet.rooms.length} room${sheet.rooms.length === 1 ? "" : "s"}`,
    ...[...counts].sort((a, b) => b[1] - a[1]).map(([cls, n]) => `${n} ${cls.replace(/_/g, " ")}${n === 1 ? "" : "s"}`)];
  const how = sheet.reader ? ` ${READER[sheet.reader.kind](sheet.reader.model)}` : "";
  return (sheet.rooms.length + sheet.elements.length === 0
    ? "No rooms or building elements were read on this sheet. That does not mean there are none."
    : `Read on this sheet: ${parts.join(", ")}. Reading can miss and mislabel: check against the plan.`) + how;
}

/** One sheet with pan, zoom and the evidence of the correction items drawn on it. `focus` changes make the view fly there. */
export function SheetCanvas({ project, sheet, marks, selected, focus, onSelect, layer, setLayer }: {
  project: string; sheet: SheetView; marks: Mark[]; selected: string | null; focus: number; onSelect: (key: string) => void;
  layer: Layer; setLayer: (l: Layer) => void;
}) {
  const frame = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 800, h: 600 });
  const [view, setView] = useState<Box>([0, 0, sheet.width, sheet.height]);
  const viewRef = useRef(view);
  viewRef.current = view;
  const anim = useRef(0);
  const drag = useRef<{ x: number; y: number; view: Box; moved: boolean } | null>(null);

  useEffect(() => {
    const el = frame.current!;
    const watch = new ResizeObserver(() => setSize({ w: el.clientWidth || 800, h: el.clientHeight || 600 }));
    watch.observe(el);
    return () => watch.disconnect();
  }, []);

  /** The view box that shows `b` whole, in the frame's own proportions. */
  const frameBox = useCallback((b: Box, pad: number): Box => {
    const ratio = size.w / size.h;
    let w = b[2] * pad;
    let h = b[3] * pad;
    if (w / h < ratio) w = h * ratio; else h = w / ratio;
    return [b[0] + b[2] / 2 - w / 2, b[1] + b[3] / 2 - h / 2, w, h];
  }, [size]);

  const fly = useCallback((to: Box) => {
    cancelAnimationFrame(anim.current);
    if (still()) { setView(to); return; }
    const from = viewRef.current;
    const t0 = performance.now();
    const step = (t: number) => {
      const k = Math.min(1, (t - t0) / 420);
      const e = 1 - (1 - k) ** 3;
      setView(from.map((v, i) => v + (to[i] - v) * e) as Box);
      if (k < 1) anim.current = requestAnimationFrame(step);
    };
    anim.current = requestAnimationFrame(step);
  }, []);

  const fit = useCallback(() => fly(frameBox([0, 0, sheet.width, sheet.height], 1.04)), [fly, frameBox, sheet]);

  useEffect(() => {
    const mark = marks.find((m) => m.key === selected);
    const b = mark && boundsOf(sheet, mark.shapes);
    if (!b) { fit(); return; }
    const min = Math.max(sheet.width, sheet.height) * 0.22;      // keep enough of the surroundings to read the place
    fly(frameBox([b[0] + b[2] / 2 - Math.max(b[2], min) / 2, b[1] + b[3] / 2 - Math.max(b[3], min) / 2,
      Math.max(b[2], min), Math.max(b[3], min)], 1.35));
    return () => cancelAnimationFrame(anim.current);
    // fly again when the reviewer asks (focus), picks another item, changes sheet or the frame is resized
  }, [selected, focus, sheet.index, size]);

  const scale = Math.max(view[2] / size.w, view[3] / size.h);     // sheet units per screen pixel

  const zoom = useCallback((k: number, cx?: number, cy?: number) => {
    cancelAnimationFrame(anim.current);
    setView(([x, y, w, h]) => {
      const nw = Math.min(Math.max(w * k, sheet.width * 0.02), sheet.width * 4);
      const nh = (nw * h) / w;
      const px = cx ?? x + w / 2;
      const py = cy ?? y + h / 2;
      return [px - ((px - x) * nw) / w, py - ((py - y) * nh) / h, nw, nh];
    });
  }, [sheet.width]);

  useEffect(() => {
    const el = frame.current!;
    const wheel = (ev: WheelEvent) => {
      ev.preventDefault();
      const r = el.getBoundingClientRect();
      const [x, y, w, h] = viewRef.current;
      const s = Math.max(w / r.width, h / r.height);
      zoom(ev.deltaY < 0 ? 0.86 : 1.16, x + (w - r.width * s) / 2 + (ev.clientX - r.left) * s,
        y + (h - r.height * s) / 2 + (ev.clientY - r.top) * s);
    };
    el.addEventListener("wheel", wheel, { passive: false });
    return () => el.removeEventListener("wheel", wheel);
  }, [zoom]);

  const down = (ev: ReactPointerEvent) => {
    if (ev.button !== 0 || (ev.target as Element).closest("button, .pin")) return;
    cancelAnimationFrame(anim.current);
    drag.current = { x: ev.clientX, y: ev.clientY, view: viewRef.current, moved: false };
    (ev.currentTarget as Element).setPointerCapture(ev.pointerId);
  };
  const move = (ev: ReactPointerEvent) => {
    const d = drag.current;
    if (!d) return;
    const s = Math.max(d.view[2] / size.w, d.view[3] / size.h);
    setView([d.view[0] - (ev.clientX - d.x) * s, d.view[1] - (ev.clientY - d.y) * s, d.view[2], d.view[3]]);
  };

  const ordered = [...marks].sort((a) => (a.key === selected ? 1 : -1));
  return (
    <div className="canvas" ref={frame} onPointerDown={down} onPointerMove={move} onPointerUp={() => (drag.current = null)}>
      <svg viewBox={view.join(" ")} preserveAspectRatio="xMidYMid meet" aria-label={`Sheet ${sheet.id}`}>
        <rect className="paper" x={0} y={0} width={sheet.width} height={sheet.height} />
        <image href={`/api/projects/${project}/sheets/${sheet.index}/backdrop.png`} width={sheet.width} height={sheet.height} />
        {layer === "read" && <Detected sheet={sheet} />}
        {layer === "corrections" && ordered.map((m) => (
          <g key={m.key} className={`mark ${m.tone} ${selected === m.key ? "on" : selected ? "dim" : ""}`}>
            {m.shapes.map((g, i) => (
              <g key={i}>
                {g.polygons.map((p, j) => <polygon key={j} points={join(p)} />)}
                {g.polylines.map((p, j) => <polyline key={j} points={join(p)} />)}
                {g.points.map((p, j) => <circle key={j} className="spot" cx={p[0]} cy={p[1]} r={6 * scale} />)}
                {g.anchor && (
                  <g className="pin" transform={`translate(${g.anchor[0]} ${g.anchor[1]}) scale(${scale})`} role="button"
                    aria-label={`Finding ${m.label}`} onClick={() => onSelect(m.key)}>
                    <path d="M0 0 C-3 -9 -14 -13 -14 -24 A14 14 0 1 1 14 -24 C14 -13 3 -9 0 0Z" />
                    <text y={-23.5}>{m.label}</text>
                  </g>
                )}
              </g>
            ))}
          </g>
        ))}
      </svg>
      <div className="layers" role="group" aria-label="What to show on the sheet">
        {LAYERS.map(([key, label]) => (
          <button key={key} aria-pressed={layer === key} onClick={() => setLayer(key)}>{label}</button>
        ))}
      </div>
      {layer === "read" && <p className="readout" role="status">{readSummary(sheet)}</p>}
      <div className="zoomer">
        <button onClick={() => zoom(0.75)} aria-label="Zoom in">+</button>
        <button onClick={() => zoom(1.33)} aria-label="Zoom out">−</button>
        <button onClick={fit}>Fit sheet</button>
      </div>
    </div>
  );
}
