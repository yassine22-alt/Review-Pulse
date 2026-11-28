import { useEffect, useMemo, useRef, useState } from "react";
import { FAMILY, roomsOf, SEVERITY } from "./filters";
import { plainEvidence } from "./plain";
import type { CorrectionList, Item, SheetView, View } from "./types";

export const TONE: Record<string, string> = { revision_required: "bad", information_requested: "ask" };
export const toneOf = (i: Item) => TONE[i.status] ?? "ok";
const DONE: Record<string, string> = { accept: "Accepted", edit: "Edited", drop: "Dismissed" };

export interface ItemActions {
  decide: (item: Item, action: "accept" | "edit" | "drop" | "reset", wording?: string, reason?: string) => Promise<void>;
  follow: (item: Item, change: { assignee?: string; due?: string; resolved?: boolean; note?: string }) => Promise<void>;
  setAside: (item: Item, state: "deferred" | "not_applicable", note: string) => Promise<void>;
  restore: (clause: string) => Promise<void>;
}

export function Findings({ view, list, located, selected, opened, canDecide, people, editing, setEditing, dismissing,
  setDismissing, onSelect, onZoom, actions }: {
  view: View | null; list: CorrectionList; located: Set<string>; selected: string | null; opened: Set<string>; canDecide: boolean;
  people: string[]; editing: boolean; setEditing: (v: boolean) => void; dismissing: boolean; setDismissing: (v: boolean) => void;
  onSelect: (key: string) => void; onZoom: () => void; actions: ItemActions;
}) {
  const sheets: SheetView[] = view?.sheets ?? [];
  const [filter, setFilter] = useState<string>("all");
  const [picks, setPicks] = useState({ severity: "", family: "", room: "" });
  const statuses = [...new Set(list.items.map((i) => i.status))];
  const rooms = useMemo(() => new Map(list.items.map((i) => [i.key, roomsOf(i, view)])), [list, view]);
  const options = {
    severity: [...new Set(list.items.map((i) => i.severity || "none"))],
    family: [...new Set(list.items.map((i) => i.family))],
    room: [...new Set([...rooms.values()].flat())].sort(),
  };
  const shown = list.items.filter((i) => (filter === "all" || i.status === filter)
    && (!picks.severity || (i.severity || "none") === picks.severity)
    && (!picks.family || i.family === picks.family)
    && (!picks.room || rooms.get(i.key)!.includes(picks.room)));
  const left = list.edit_burden.unreviewed;

  if (!list.items.length) {
    return (
      <div className="blank">
        <h3>No corrections to show</h3>
        <p>{list.uncovered_clauses > 0
          ? `${list.uncovered_clauses} requirements are still undecided. Decide them in the Requirements tab. An empty list does not mean the plans comply.`
          : "The checks that ran raised no correction. This covers only the requirements that were checked."}</p>
      </div>
    );
  }
  return (
    <>
      <div className="meter" role="group" aria-label="Filter by status">
        <div className="bar">
          {statuses.map((s) => {
            const n = list.items.filter((i) => i.status === s).length;
            return <i key={s} className={TONE[s] ?? "ok"} style={{ flexGrow: n }} />;
          })}
        </div>
        <div className="filters">
          <button aria-pressed={filter === "all"} onClick={() => setFilter("all")}>All {list.items.length}</button>
          {statuses.map((s) => {
            const mine = list.items.filter((i) => i.status === s);
            return (
              <button key={s} aria-pressed={filter === s} onClick={() => setFilter(s)}>
                <b className={`dot ${TONE[s] ?? "ok"}`} />{mine[0].status_label} {mine.length}
              </button>
            );
          })}
        </div>
        <div className="picks">
          {options.severity.length > 1 && (
            <select aria-label="Filter by severity" value={picks.severity} onChange={(e) => setPicks({ ...picks, severity: e.target.value })}>
              <option value="">Any severity</option>
              {options.severity.map((v) => <option key={v} value={v}>{SEVERITY[v === "none" ? "" : v] ?? v}</option>)}
            </select>
          )}
          {options.family.length > 1 && (
            <select aria-label="Filter by rule family" value={picks.family} onChange={(e) => setPicks({ ...picks, family: e.target.value })}>
              <option value="">Any rule family</option>
              {options.family.map((v) => <option key={v} value={v}>{FAMILY[v] ?? v}</option>)}
            </select>
          )}
          {options.room.length > 0 && (
            <select aria-label="Filter by room" value={picks.room} onChange={(e) => setPicks({ ...picks, room: e.target.value })}>
              <option value="">Any room</option>
              {options.room.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          )}
        </div>
        {shown.length < list.items.length && (
          <p role="status">Showing {shown.length} of {list.items.length}.{" "}
            <button className="link" onClick={() => { setFilter("all"); setPicks({ severity: "", family: "", room: "" }); }}>Show all</button></p>
        )}
        <p>{left === 0 ? "Every item has your decision." : `${left} of ${list.items.length} still need your decision.`}
          {list.uncovered_clauses > 0 && ` ${list.uncovered_clauses} requirements are still undecided.`}</p>
      </div>
      <ol className="cards">
        {shown.map((item) => (
          <Card key={item.key} sheets={sheets} item={item} open={selected === item.key} located={located.has(item.key)}
            seen={opened.has(item.key)} canDecide={canDecide} editing={editing && selected === item.key} people={people}
            dismissing={dismissing && selected === item.key} setDismissing={setDismissing} setEditing={setEditing} onSelect={onSelect} onZoom={onZoom} actions={actions} />
        ))}
      </ol>
      {list.deferred.length > 0 && (
        <section className="aside-list">
          <h4>Deferred submittals</h4>
          {list.deferred.map((d) => (
            <p key={d.clause}>{d.quote} <em>{d.citation}</em>
              {canDecide && <button className="link" onClick={() => actions.restore(d.clause)}>Bring back</button>}</p>
          ))}
        </section>
      )}
    </>
  );
}

function Card({ sheets, item, open, located, seen, canDecide, people, editing, setEditing, dismissing, setDismissing, onSelect,
  onZoom, actions }: {
  sheets: SheetView[]; item: Item; open: boolean; located: boolean; seen: boolean; canDecide: boolean; editing: boolean;
  people: string[]; dismissing: boolean; setDismissing: (v: boolean) => void; setEditing: (v: boolean) => void; onSelect: (key: string) => void; onZoom: () => void; actions: ItemActions;
}) {
  const ref = useRef<HTMLLIElement>(null);
  const [draft, setDraft] = useState(item.wording);
  const [aside, setAside] = useState<"" | "deferred" | "not_applicable">("");
  const [note, setNote] = useState("");
  const [reason, setReason] = useState("");
  useEffect(() => { if (dismissing) setReason(""); }, [dismissing]);
  useEffect(() => setDraft(item.wording), [item.wording, editing]);
  useEffect(() => { if (open) ref.current?.scrollIntoView({ block: "nearest" }); else setAside(""); }, [open]);
  const state = item.review.action;
  return (
    <li ref={ref} className={`item ${toneOf(item)} ${open ? "open" : ""} ${item.dropped ? "dropped" : ""}`}>
      <button className="head" aria-expanded={open} onClick={() => onSelect(item.key)}>
        <span className="num">{item.n ?? "x"}</span>
        <span className="sum">
          <span className="line"><strong>{item.status_label}</strong><em>{item.citation}</em></span>
          <span className="quote-short">{item.decided_by ? item.wording : item.quote}</span>
        </span>
        {item.followup?.resolved && !item.followup.resolved.stale && <span className="decided ok">Resolved</span>}
        {state !== "pending" && <span className={`decided ${state}`}>{DONE[state]}</span>}
      </button>
      {open && (
        <div className="body">
          <h4>{item.from_document ? "The requirement, as written" : "A built-in rule, not from your document"}</h4>
          <blockquote>{item.quote}</blockquote>

          <h4>{item.decided_by ? `What ${item.decided_by} pointed at` : "What the drawings show"}</h4>
          {item.overrode && <p className="notice-line">The tool had concluded: {item.overrode}. The reviewer's decision replaces it.</p>}
          {item.facts.length === 0 && (
            <p className="muted">{item.decided_by ? "No note was pointed at." : "No value could be read for this requirement."}</p>
          )}
          <ul className="facts">
            {item.facts.map((f, i) => (
              <li key={i}>
                <span>{f.subject ? `${f.subject}: ` : ""}{f.statement.replace(/>=/g, "≥").replace(/<=/g, "≤")}</span>
                <small>{plainEvidence(f.source, sheets)}</small>
              </li>
            ))}
          </ul>
          <p className="where">
            {item.locations.map((l) => plainEvidence(l.where, sheets)).join("; ")
              || "No place on a sheet is attached to this item."}
            {item.more_locations > 0 && ` And ${item.more_locations} more places.`}
          </p>
          {located && <button className="ghost" onClick={onZoom}>Show on the drawing <kbd>Enter</kbd></button>}

          {item.question && <div className="question"><h4>What is needed to decide</h4><p>{item.question}</p></div>}

          <h4>Comment to the applicant</h4>
          {editing ? (
            <>
              <textarea autoFocus rows={5} value={draft} onChange={(e) => setDraft(e.target.value)} aria-label="Comment wording" />
              <div className="row">
                <button className="primary" disabled={!draft.trim()}
                  onClick={async () => { await actions.decide(item, "edit", draft); setEditing(false); }}>Save my wording</button>
                <button onClick={() => setEditing(false)}>Cancel</button>
              </div>
            </>
          ) : <p className="wording">{item.wording}</p>}

          {canDecide && !editing && (
            <div className="decide">
              {state === "pending" ? (
                <>
                  <button className="primary" disabled={located && !seen} onClick={() => actions.decide(item, "accept")}>
                    Accept <kbd>A</kbd></button>
                  <button onClick={() => setEditing(true)}>Edit <kbd>E</kbd></button>
                  <button onClick={() => setDismissing(true)}>Dismiss <kbd>D</kbd></button>
                </>
              ) : (
                <>
                  <span className="muted">{item.decided_by && state === "accept" ? "Written" : DONE[state]} by {item.review.by}</span>
                  <button onClick={() => setEditing(true)}>Edit</button>
                  {item.decided_by
                    ? <button onClick={() => actions.restore(item.clause)}>Take this correction back</button>
                    : <button onClick={() => actions.decide(item, "reset")}>Undo</button>}
                </>
              )}
              {!aside && !item.decided_by && (
                <span className="more">
                  <button className="link" onClick={() => setAside("deferred")}>Deferred submittal</button>
                  <button className="link" onClick={() => setAside("not_applicable")}>Does not apply</button>
                </span>
              )}
            </div>
          )}
          {state === "drop" && item.review.reason && <p className="muted">Reason for dismissing: {item.review.reason}</p>}
          {dismissing && state === "pending" && canDecide && (
            <form className="why" onSubmit={async (e) => {
              e.preventDefault();
              await actions.decide(item, "drop", undefined, reason);
              setDismissing(false);
            }}>
              <label>Why is this not a correction?
                <small className="muted">Required. It stays in the history, so that a wrong finding can be traced.</small>
                <input autoFocus required maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} /></label>
              <div className="row"><button className="primary" disabled={!reason.trim()}>Dismiss it</button>
                <button type="button" onClick={() => setDismissing(false)}>Cancel</button></div>
            </form>
          )}
          {!item.dropped && <FollowUp item={item} canDecide={canDecide} people={people} actions={actions} />}
          {aside && (
            <form className="why" onSubmit={async (e) => { e.preventDefault(); await actions.setAside(item, aside, note); }}>
              <label>{aside === "deferred" ? "Who submits it, and when?" : "Why does it not apply here?"}
                <input autoFocus required value={note} onChange={(e) => setNote(e.target.value)} /></label>
              <div className="row"><button className="primary">Confirm</button>
                <button type="button" onClick={() => setAside("")}>Cancel</button></div>
            </form>
          )}
        </div>
      )}
    </li>
  );
}

/** Who takes a comment further and by when, and whether corrected drawings settled it. */
function FollowUp({ item, canDecide, people, actions }: { item: Item; canDecide: boolean; people: string[]; actions: ItemActions }) {
  const f = item.followup;
  const [who, setWho] = useState(f?.assignee ?? "");
  const [due, setDue] = useState(f?.due ?? "");
  const [checked, setChecked] = useState("");
  const [closing, setClosing] = useState(false);
  useEffect(() => { setWho(f?.assignee ?? ""); setDue(f?.due ?? ""); }, [f?.assignee, f?.due]);
  const done = f?.resolved;
  if (!canDecide) {
    return f?.assignee || done ? (
      <div className="follow">
        {f?.assignee && <span>Assigned to {f.assignee}{f.due ? `, due ${f.due}` : ""}.</span>}
        {done && <span>Resolved by {done.by}.</span>}
      </div>
    ) : null;
  }
  const changed = who !== (f?.assignee ?? "") || due !== (f?.due ?? "");
  return (
    <div className="follow">
      <div className="row">
        <label>Assigned to
          {people.length > 0 ? (
            <select value={who} onChange={(e) => setWho(e.target.value)}>
              <option value="">Nobody</option>
              {[...new Set([...people, ...(who ? [who] : [])])].map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          ) : <input maxLength={80} value={who} onChange={(e) => setWho(e.target.value)} />}
        </label>
        <label>Due<input type="date" value={due} onChange={(e) => setDue(e.target.value)} disabled={!who} /></label>
        {changed && <button onClick={() => actions.follow(item, { assignee: who, due: who ? due : "" })}>
          {who ? "Save assignment" : "Remove assignment"}</button>}
      </div>
      {done && !done.stale ? (
        <span>Resolved by {done.by}: {done.note}{" "}
          <button className="link" onClick={() => actions.follow(item, { resolved: false })}>Reopen</button></span>
      ) : (
        <>
          {done?.stale && <span className="notice-line">Marked resolved by {done.by} on earlier drawings. Check the new ones.</span>}
          {closing ? (
            <form className="why" onSubmit={async (e) => {
              e.preventDefault();
              await actions.follow(item, { resolved: true, note: checked });
              setClosing(false);
            }}>
              <label>What did you check?<input autoFocus required maxLength={500} value={checked}
                onChange={(e) => setChecked(e.target.value)} /></label>
              <div className="row"><button className="primary" disabled={!checked.trim()}>Mark resolved</button>
                <button type="button" onClick={() => setClosing(false)}>Cancel</button></div>
            </form>
          ) : <span><button className="link" onClick={() => setClosing(true)}>Mark resolved</button></span>}
        </>
      )}
    </div>
  );
}
