import type { Evidence, NoteRef, SheetView } from "./types";

const RESULT: Record<string, string> = {
  agrees: "meets", contradicts: "does not meet", "no figure": "states no figure for", unclear: "is unclear about",
};

/** What the written notes of the drawing set say about a requirement. It points a reviewer to a place; it decides nothing. */
export function Notes({ evidence, sheets, onShow, onUse, picked }: {
  evidence: Evidence; sheets: SheetView[]; onShow: (n: NoteRef) => void; onUse?: (n: NoteRef) => void; picked?: NoteRef | null;
}) {
  const chosen = evidence.chosen;
  const others = (evidence.candidates ?? []).filter((c) => !chosen || c.text !== chosen.text || c.sheet !== chosen.sheet);
  const sheetName = (id: string) => {
    const found = sheets.find((s) => s.id === id);
    return found ? `Sheet ${found.index + 1}` : "A sheet";
  };
  const card = (n: NoteRef, key: string) => {
    const canShow = !!n.box && sheets.some((s) => s.id === n.sheet && s.affine);
    return (
      <li key={key} className={picked && picked.text === n.text && picked.sheet === n.sheet ? "is-picked" : ""}>
        <span>{n.text}</span>
        <small>{sheetName(n.sheet)}
          {canShow && <button className="link" onClick={() => onShow(n)}>Show on the drawing</button>}
          {onUse && <button className="link" onClick={() => { onUse(n); if (canShow) onShow(n); }}>Use as my evidence</button>}</small>
      </li>
    );
  };
  if (!chosen && !others.length) return <p className="muted">No written note on the drawings was found for this requirement.</p>;
  return (
    <div className="notes-found">
      {chosen && (
        <>
          <h4>A note that seems to be about this</h4>
          <ul className="facts">{card(chosen, "chosen")}</ul>
          {evidence.checks?.map((c, i) => c.stated && (
            <p key={i} className="where">The figure read, {c.stated}, {RESULT[c.result] ?? c.result} the limit {c.required}.
              Check that it is the same property.</p>
          ))}
          <p className="muted small">Found by search and picked by the model. It is not a finding: read it on the sheet.</p>
        </>
      )}
      {others.length > 0 && (
        <details open={!chosen}>
          <summary>{chosen ? "Other notes that came close" : "Closest notes on the drawings, found by search only"} ({others.length})</summary>
          <ul className="facts">{others.map((n, i) => card(n, String(i)))}</ul>
        </details>
      )}
    </div>
  );
}
