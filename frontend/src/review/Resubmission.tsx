import type { BackCheck, NoteRef, SheetView } from "./types";

const STATUS: Record<string, { label: string; tone: string; order: number }> = {
  "NOT ADDRESSED": { label: "Not addressed", tone: "bad", order: 0 },
  "CHANGED BUT NOT SETTLED": { label: "Changed, not settled", tone: "ask", order: 1 },
  "CANNOT TELL": { label: "Cannot tell", tone: "ask", order: 2 },
  MOVED: { label: "Moved", tone: "ask", order: 3 },
  RESOLVED: { label: "Looks resolved", tone: "ok", order: 4 },
};

const count = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** The new drawings against the comments sent on the version before. A reading for the reviewer: it closes nothing. */
export function Resubmission({ data, sheets, onShow, canDecide, busy, compare }: {
  data: BackCheck; sheets: SheetView[]; onShow: (n: NoteRef) => void; canDecide: boolean; busy: boolean; compare: () => void;
}) {
  const sheetName = (id: string) => {
    const found = sheets.find((s) => s.id === id);
    return found ? `Sheet ${found.index + 1}` : "A sheet";
  };
  const answers = [...(data.answers ?? [])].sort((a, b) => (STATUS[a.status]?.order ?? 9) - (STATUS[b.status]?.order ?? 9));

  return (
    <div className="resubmission">
      <p>The earlier version, <b>{data.old_version?.name}</b>, was sent {count(data.comments ?? 0, "comment")}.
        The drawings now under review are <b>{data.new_version?.name}</b>.</p>
      {!data.done && (
        canDecide
          ? <p><button className="primary" disabled={busy} onClick={compare}>
              {busy ? "Comparing the two versions" : "Check the comments against the new drawings"}</button></p>
          : <p className="muted">A reviewer has not run the comparison yet.</p>
      )}
      {data.done && (
        <>
          <ol className="cards">
            {answers.map((a) => (
              <li key={a.id} className="item answer">
                <p className="top"><span className={`decided ${STATUS[a.status]?.tone ?? ""}`}>{STATUS[a.status]?.label ?? a.status}</span>
                  {a.code && <span className="cid">{a.code}</span>}</p>
                <p className="wording">{a.comment}</p>
                <p className="where">{a.reason}</p>
                {a.person_must_check && <p><b>Check:</b> {a.person_must_check}</p>}
                {a.place && sheets.some((s) => s.id === a.place!.sheet && s.affine) && (
                  <small>{sheetName(a.place.sheet)}
                    <button className="link" onClick={() => onShow(a.place!)}>Show on the new drawing</button></small>
                )}
              </li>
            ))}
          </ol>
          <h4>Also in the new drawings</h4>
          <ul>
            <li>{count(data.changes_nobody_asked_for ?? 0, "changed place")} that no comment asked for</li>
            {data.clouds_present && <li>{count(data.changes_outside_clouds ?? 0, "change")} outside every revision cloud</li>}
            {!!data.sheets_added?.length && <li>{count(data.sheets_added.length, "sheet")} added</li>}
            {!!data.sheets_removed?.length && <li>{count(data.sheets_removed.length, "sheet")} removed</li>}
          </ul>
          <p className="muted small">This compares words, drawn lines and table cells of the two files. It is a reading for you
            to check: it closes no comment. Decisions made on the earlier drawings are marked "Confirm again".</p>
        </>
      )}
    </div>
  );
}
