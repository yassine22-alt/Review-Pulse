import { useState, type FormEvent } from "react";
import { draftComment } from "./Parts";
import type { Determination, NoteRef, SheetView } from "./types";

export const CHOICES = [
  { key: "shown", button: "Shown on the plans", done: "Shown on the plans", ask: "What did you rely on?",
    hint: "Optional when you picked a note or a sheet.", required: false, place: true },
  { key: "correction", button: "Needs correction", done: "Correction", ask: "Comment to the applicant",
    hint: "The requirement is quoted after your comment.", required: true, place: true },
  { key: "not_applicable", button: "Does not apply", done: "Does not apply", ask: "Why does it not apply here?", hint: "",
    required: true, place: false },
  { key: "deferred", button: "Later submittal", done: "Deferred submittal", ask: "Who submits it, and when?", hint: "",
    required: true, place: false },
] as const;

export type Choice = (typeof CHOICES)[number]["key"];

const sheetLabel = (sheets: SheetView[], id: string) => {
  const s = sheets.find((x) => x.id === id);
  return s ? `Sheet ${s.index + 1}` : "A sheet";
};

/** The reviewer's own decision on one requirement. It works whether or not the tool could read it. */
export function Decision({ decided, sheets, viewing, picked, clearPicked, canDecide, save, takeBack, missing = [] }: {
  decided?: Determination; sheets: SheetView[]; viewing?: SheetView; picked: NoteRef | null; clearPicked: () => void;
  canDecide: boolean; save: (state: Choice, note: string, evidence: NoteRef | null) => Promise<boolean>; takeBack: () => void;
  missing?: string[];                 // parts the reviewer ticked as missing
}) {
  const [choice, setChoice] = useState<Choice | null>(null);
  const [note, setNote] = useState("");
  const [sheet, setSheet] = useState("");
  const [saving, setSaving] = useState(false);
  const [lastDraft, setLastDraft] = useState("");

  if (decided) {
    const c = CHOICES.find((x) => x.key === decided.state);
    return (
      <div className="mine-decision">
        <h4>Your office decided</h4>
        <p><strong>{c?.done ?? decided.state}</strong> by {decided.by}</p>
        {decided.evidence && (
          <p className="where">{sheetLabel(sheets, decided.evidence.sheet)}{decided.evidence.text && `: ${decided.evidence.text}`}</p>
        )}
        {decided.note && <p className="wording">{decided.note}</p>}
        {decided.parts && (
          <ul className="ticked">{decided.parts.map((p) => (
            <li key={p.text} className={p.mark}>{p.mark === "seen" ? "Seen" : "Missing"}: {p.text}</li>
          ))}</ul>
        )}
        {canDecide && <button onClick={takeBack}>Take this decision back</button>}
      </div>
    );
  }
  if (!canDecide) return null;

  const current = CHOICES.find((x) => x.key === choice);
  const place: NoteRef | null = current?.place ? picked ?? (sheet ? { sheet, text: "", box: null } : null) : null;
  const ready = !!current && (current.required ? !!note.trim() : current.key !== "shown" || !!place || !!note.trim());

  /** Opening "Needs correction" starts from the parts ticked as missing; words the reviewer typed are never replaced. */
  function choose(key: Choice | null) {
    const drafted = draftComment(missing);
    if (key === "correction" && drafted && (!note.trim() || note === lastDraft)) { setNote(drafted); setLastDraft(drafted); }
    else if (key !== "correction" && note === lastDraft) setNote("");
    setChoice(key);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!current || !ready) return;
    setSaving(true);
    if (await save(current.key, note.trim(), place)) { setChoice(null); setNote(""); setSheet(""); clearPicked(); }
    setSaving(false);
  }

  return (
    <div className="mine-decision">
      <h4>Your decision</h4>
      <div className="choices" role="group" aria-label="Your decision on this requirement">
        {CHOICES.map((c) => (
          <button key={c.key} type="button" aria-pressed={choice === c.key} onClick={() => choose(choice === c.key ? null : c.key)}
            disabled={c.key === "shown" && missing.length > 0}
            title={c.key === "shown" && missing.length > 0 ? "A part is ticked as missing" : undefined}>
            {c.button}</button>
        ))}
      </div>
      {picked && !current && <p className="muted small">A note is picked as your evidence. Choose a decision.</p>}
      {current && (
        <form className="why" onSubmit={submit}>
          {current.place && (picked ? (
            <div className="picked">
              <span><b>{sheetLabel(sheets, picked.sheet)}</b> {picked.text}</span>
              <button type="button" className="link" onClick={clearPicked}>Remove</button>
            </div>
          ) : (
            <label>Sheet that shows it
              <select value={sheet} onChange={(e) => setSheet(e.target.value)}>
                <option value="">No sheet picked</option>
                {viewing && <option value={viewing.id}>The sheet on screen (Sheet {viewing.index + 1})</option>}
                {sheets.filter((s) => s.id !== viewing?.id).map((s) => <option key={s.id} value={s.id}>Sheet {s.index + 1}</option>)}
              </select>
            </label>
          ))}
          <label>{current.ask}
            <textarea autoFocus rows={current.key === "correction" ? 4 : 2} maxLength={2000} value={note}
              onChange={(e) => setNote(e.target.value)} />
            {current.hint && <small className="muted">{current.hint}</small>}
          </label>
          <div className="row">
            <button className="primary" disabled={!ready || saving}>{saving ? "Saving" : "Record my decision"}</button>
            <button type="button" onClick={() => setChoice(null)}>Cancel</button>
          </div>
        </form>
      )}
    </div>
  );
}
