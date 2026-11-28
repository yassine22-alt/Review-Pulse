import type { Project } from "./api";

export type Lane = "waiting" | "working" | "review";

/** Where a submission stands, read only from what the server reports, and the one thing to do next. */
export function stage(p: Project): { lane: Lane; label: string; next: string } {
  const running = p.active_jobs[0];
  if (running) return { lane: "working", label: "Reading", next: running.message || "The server is reading the files." };
  if (!p.plan) return { lane: "waiting", label: "Needs drawings", next: "Upload the plan set." };
  if (!p.requirements) return { lane: "waiting", label: "Needs requirements", next: "Upload the code or checklist." };
  if (!p.analysed) return { lane: "waiting", label: "Drawings not read", next: "Open it to see what went wrong." };
  if (!p.checked) return { lane: "review", label: "Files read", next: "Approve the checks on the review desk." };
  return { lane: "review", label: "Checked", next: "Open it for the correction list." };
}
