import type { SheetView } from "./types";

/** The server's evidence lines name files and internal methods. On screen a reviewer sees sheet numbers and plain words;
    nothing is dropped except the internal sheet name and the reading tier. */
export function plainEvidence(text: string, sheets: SheetView[]): string {
  let out = text;
  for (const s of [...sheets].sort((a, b) => b.id.length - a.id.length)) {
    out = out.split(`sheet ${s.id}`).join(`sheet ${s.index + 1}`).split(s.id).join(`sheet ${s.index + 1}`);
  }
  return out
    .replace(/,? reading tier T\d+/g, "")
    .replace(/\b([a-z]+)_([a-z]+)(?:_([a-z]+))?\b/g, (_m, a, b, c) => [a, b, c].filter(Boolean).join(" "))
    .replace(/>=/g, "≥")
    .replace(/<=/g, "≤")
    .replace(/^(\w)/, (c) => c.toUpperCase());
}

/** Bullets and tick boxes drawn by a symbol font mean nothing outside it. The stored text is not changed. */
export const plainClause = (text: string) => text.replace(/[\uE000-\uF8FF]/g, "").trim();

const OUTCOMES: Record<string, string> = {
  SATISFIED: "this check would be met", VIOLATED: "this check would find a violation",
  UNKNOWN: "this check cannot be decided yet", NOT_APPLICABLE: "this check would not apply", NOTAPPLICABLE: "this check would not apply",
};

export const plainOutcome = (outcome: string) => OUTCOMES[outcome.toUpperCase()] ?? `the result is "${outcome}"`;

export function plainNeed(need: string): string {
  const incomplete = need.match(/^incomplete collection:\s*(.+)$/);
  return incomplete ? `your confirmation that all ${incomplete[1].replace(/_/g, " ")} were found` : need.replace(/_/g, " ");
}
