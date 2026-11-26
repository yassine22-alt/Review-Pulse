import { useEffect, useRef, useState } from "react";
import { plainEvidence } from "./plain";
import type { CorrectionList, Item, SheetView } from "./types";

export const TONE: Record<string, string> = { revision_required: "bad", information_requested: "ask" };
export const toneOf = (i: Item) => TONE[i.status] ?? "ok";
const DONE: Record<string, string> = { accept: "Accepted", edit: "Edited", drop: "Dropped" };

export interface ItemActions {
  decide: (item: Item, action: "accept" | "edit" | "drop" | "reset", wording?: string) => Promise<void>;
  setAside: (item: Item, state: "deferred" | "not_applicable", note: string) => Promise<void>;
  restore: (clause: string) => Promise<void>;
}

export function Findings({ sheets, list, located, selected, opened, canDecide, editing, setEditing, onSelect, onZoom, actions }: {
  sheets: SheetView[]; list: CorrectionList; located: Set<string>; selected: string | null; opened: Set<string>; canDecide: boolean;
  editing: boolean; setEditing: (v: boolean) => void; onSelect: (key: string) => void; onZoom: () => void; actions: ItemActions;
}) {
  const [filter, setFilter] = useState<string>("all");
  const statuses = [...new Set(list.items.map((i) => i.status))];
  const shown = list.items.filter((i) => filter === "all" || i.status === filter);
  const left = list.edit_burden.unreviewed;

  if (!list.items.length) {
    return (
      <div className="blank">
        <h3>No corrections to show</h3>
        <p>{list.uncovered_clauses > 0
          ? `${list.uncovered_clauses} requirements have not been checked yet. Approve checks in the Requirements tab, then run them. An empty list does not mean the plans comply.`
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
        <p>{left === 0 ? "Every item has your decision." : `${left} of ${list.items.length} still need your decision.`}
          {list.uncovered_clauses > 0 && ` ${list.uncovered_clauses} requirements were not checked.`}</p>
      </div>
      <ol className="cards">
        {shown.map((item) => (
          <Card key={item.key} sheets={sheets} item={item} open={selected === item.key} located={located.has(item.key)}
            seen={opened.has(item.key)} canDecide={canDecide} editing={editing && selected === item.key}
            setEditing={setEditing} onSelect={onSelect} onZoom={onZoom} actions={actions} />
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

function Card({ sheets, item, open, located, seen, canDecide, editing, setEditing, onSelect, onZoom, actions }: {
  sheets: SheetView[]; item: Item; open: boolean; located: boolean; seen: boolean; canDecide: boolean; editing: boolean;
  setEditing: (v: boolean) => void; onSelect: (key: string) => void; onZoom: () => void; actions: ItemActions;
}) {
  const ref = useRef<HTMLLIElement>(null);
  const [draft, setDraft] = useState(item.wording);
  const [aside, setAside] = useState<"" | "deferred" | "not_applicable">("");
  const [note, setNote] = useState("");
  useEffect(() => setDraft(item.wording), [item.wording, editing]);
  useEffect(() => { if (open) ref.current?.scrollIntoView({ block: "nearest" }); else setAside(""); }, [open]);
  const state = item.review.action;
  return (
    <li ref={ref} className={`item ${toneOf(item)} ${open ? "open" : ""} ${item.dropped ? "dropped" : ""}`}>
      <button className="head" aria-expanded={open} onClick={() => onSelect(item.key)}>
        <span className="num">{item.n ?? "x"}</span>
        <span className="sum">
          <span className="line"><strong>{item.status_label}</strong><em>{item.citation}</em></span>
          <span className="quote-short">{item.quote}</span>
        </span>
        {state !== "pending" && <span className={`decided ${state}`}>{DONE[state]}</span>}
      </button>
      {open && (
        <div className="body">
          <h4>{item.from_document ? "The requirement, as written" : "A built-in rule, not from your document"}</h4>
          <blockquote>{item.quote}</blockquote>

          <h4>What the drawings show</h4>
          {item.facts.length === 0 && <p className="muted">No value could be read for this requirement.</p>}
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
                  <button onClick={() => actions.decide(item, "drop")}>Drop <kbd>D</kbd></button>
                </>
              ) : (
                <>
                  <span className="muted">{DONE[state]} by {item.review.by}</span>
                  <button onClick={() => setEditing(true)}>Edit</button>
                  <button onClick={() => actions.decide(item, "reset")}>Undo</button>
                </>
              )}
              {!aside && (
                <span className="more">
                  <button className="link" onClick={() => setAside("deferred")}>Deferred submittal</button>
                  <button className="link" onClick={() => setAside("not_applicable")}>Does not apply</button>
                </span>
              )}
            </div>
          )}
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
