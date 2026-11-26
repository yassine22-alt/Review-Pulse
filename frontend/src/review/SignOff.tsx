import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { CorrectionList } from "./types";

const EXPORTS = [
  { format: "html", label: "Correction letter", hint: "Opens in the browser, ready to print", open: true },
  { format: "pdf", label: "Marked up drawings", hint: "PDF with a numbered cloud at each place", open: true },
  { format: "csv", label: "Spreadsheet", hint: "CSV, one line per comment", open: false },
  { format: "bcf", label: "BCF issues", hint: "For design tools that read BCF", open: false },
];

export function SignOffDrawer({ project, list, canSign, close, reload }: {
  project: string; list: CorrectionList; canSign: boolean; close: () => void; reload: () => Promise<void>;
}) {
  const [results, setResults] = useState<string[]>([]);
  const [choice, setChoice] = useState<Record<string, string>>({});
  const [problem, setProblem] = useState("");
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    api<{ signoff_results: string[] }>("/api/reviewer-states").then((s) => setResults(s.signoff_results))
      .catch((e: Error) => setProblem(e.message));
    box.current?.focus();
  }, []);
  const left = list.edit_burden.unreviewed;

  async function sign(discipline: string, result: string) {
    try {
      await api(`/api/projects/${project}/signoffs`, { method: "POST", json: { discipline, result, cycle: list.cycle } });
      await reload();
    } catch (e) { setProblem((e as Error).message); }
  }

  return (
    <div className="scrim" onClick={close}>
      <div className="drawer" role="dialog" aria-modal="true" aria-label="Sign off and export" tabIndex={-1} ref={box}
        onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.key === "Escape" && close()}>
        <header><h2>Sign off and export</h2><button onClick={close}>Close</button></header>
        <p className="muted">Review round {list.cycle}. Proposed overall result: <strong>{list.overall.label}</strong>.</p>
        {problem && <p className="problem" role="alert">{problem}</p>}
        {left > 0 && <p className="notice-line">{left} comments have no decision from you yet. They are exported as proposed.</p>}
        {list.uncovered_clauses > 0 && (
          <p className="notice-line">{list.uncovered_clauses} requirements were not checked by the tool. They are yours to check.</p>
        )}
        <h3>By discipline</h3>
        {Object.keys(list.disciplines).length === 0 && <p className="muted">There is nothing to sign yet.</p>}
        {Object.entries(list.disciplines).map(([id, d]) => (
          <div className="signrow" key={id}>
            <div><strong>{d.label}</strong>
              <small>{d.signed ? `Signed "${d.signed.result}" by ${d.signed.reviewer}` : `Proposed: ${d.proposed}`}</small></div>
            {canSign && (
              <>
                <select aria-label={`Result for ${d.label}`} value={choice[id] ?? d.signed?.result ?? d.proposed}
                  onChange={(e) => setChoice({ ...choice, [id]: e.target.value })}>
                  {[...new Set([d.proposed, ...results])].map((r) => <option key={r}>{r}</option>)}
                </select>
                <button className="primary" onClick={() => sign(id, choice[id] ?? d.signed?.result ?? d.proposed)}>
                  {d.signed ? "Sign again" : "Sign"}</button>
              </>
            )}
          </div>
        ))}
        <h3>Export</h3>
        <div className="exports">
          {EXPORTS.map((x) => (
            <a key={x.format} href={`/api/projects/${project}/correction-list?format=${x.format}`}
              {...(x.open ? { target: "_blank", rel: "noreferrer" } : {})}>
              <strong>{x.label}</strong><small>{x.hint}</small>
            </a>
          ))}
        </div>
      </div>
    </div>
  );
}
