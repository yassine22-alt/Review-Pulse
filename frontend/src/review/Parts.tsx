import type { Found, NoteRef, PartSearch, SheetView } from "./types";

export type Mark = "seen" | "missing";
export type Marks = Record<string, Mark>;

const KIND: Record<string, string> = { label: "Label", row: "Table row", dimensions: "Measurements" };

/** The comment a reviewer starts from when parts are missing: the requirement's own words, nothing added to them. */
export const draftComment = (parts: string[]) =>
  parts.length ? `Show on the plans: ${parts.map((p) => p.replace(/[\s.;:,]+$/, "")).join("; ")}.` : "";

/** One requirement, part by part: what the search found for each, and the reviewer's own tick. Nothing here is a finding. */
export function Parts({ search, sheets, marks, setMark, onShow, onUse, picked }: {
  search: PartSearch; sheets: SheetView[]; marks: Marks; setMark?: (part: string, mark: Mark | null) => void;
  onShow: (n: NoteRef) => void; onUse?: (n: NoteRef) => void; picked?: NoteRef | null;
}) {
  const sheetName = (id: string) => {
    const found = sheets.find((s) => s.id === id);
    return found ? `Sheet ${found.index + 1}` : "A sheet";
  };
  const place = (n: Found, key: string) => {
    const canShow = !!n.box && sheets.some((s) => s.id === n.sheet && s.affine);
    return (
      <li key={key} className={picked && picked.text === n.text && picked.sheet === n.sheet ? "is-picked" : ""}>
        <span>{n.kind && <b className="kind">{KIND[n.kind] ?? n.kind}</b>} {n.text}
          {n.times && n.times > 1 ? ` (${n.times} times on this sheet)` : ""}</span>
        <small>{sheetName(n.sheet)}
          {canShow && <button className="link" onClick={() => onShow(n)}>Show on the drawing</button>}
          {onUse && <button className="link" onClick={() => { onUse(n); if (canShow) onShow(n); }}>Use as my evidence</button>}</small>
      </li>
    );
  };
  const more = (title: string, found: Found[], key: string) => (
    <details>
      <summary>{title}</summary>
      <ul className="facts">{found.map((n, k) => place(n, `${key}-${k}`))}</ul>
    </details>
  );
  const many = search.parts.length > 1;
  const ticked = search.parts.filter((p) => marks[p.text]).length;

  return (
    <div className="parts">
      <h4>{many ? "What this asks, part by part" : "Where to look"}
        {many && <span className="count">{ticked} of {search.parts.length} checked by you</span>}</h4>
      <ol>
        {search.parts.map((p, i) => (
          <li key={p.text} className={`part ${marks[p.text] ?? ""}`}>
            {many && <p className="asked">{p.text}</p>}
            {p.notes.length > 0
              ? <ul className="facts">{p.notes.slice(0, many ? 2 : 1).map((n, k) => place(n, `a${k}`))}</ul>
              : <p className="muted small">No note on the drawings came up.</p>}
            {!many && p.notes.length > 1 && more(`More notes (${p.notes.length - 1})`, p.notes.slice(1), `n${i}`)}
            {p.written.length > 0 && more(`Labels and tables on the drawings (${p.written.length})`, p.written, `w${i}`)}
            {setMark && (
              <div className="choices small" role="group" aria-label={`Your check of: ${p.text}`}>
                <button type="button" aria-pressed={marks[p.text] === "seen"}
                  onClick={() => setMark(p.text, marks[p.text] === "seen" ? null : "seen")}>I saw it on the plans</button>
                <button type="button" aria-pressed={marks[p.text] === "missing"}
                  onClick={() => setMark(p.text, marks[p.text] === "missing" ? null : "missing")}>It is missing</button>
              </div>
            )}
          </li>
        ))}
      </ol>
      {!!search.whole_line?.length && more("Closest notes for the whole requirement"
        + ` (${search.whole_line.length})`, search.whole_line, "all")}
      <p className="muted small">These are places the search found, not findings. A part with a place can still be missing, and
        something drawn without words may not come up. Check each on the sheet.
        {search.left_out.length > 0 && ` Words of the requirement in no part: ${search.left_out.join(", ")}.`}</p>
    </div>
  );
}
