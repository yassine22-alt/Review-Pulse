import { useEffect, useState } from "react";
import { api, type Project } from "../api";
import { CHOICES, Decision, type Choice } from "./Decision";
import { Notes } from "./Notes";
import { Parts, type Marks } from "./Parts";
import { plainClause, plainNeed, plainOutcome } from "./plain";
import type { Clause, Determination, NoteRef, PartSearch, Reading, SheetView } from "./types";

const GROUPS = [
  { key: "approve", title: "A check is waiting for your approval" },
  { key: "todo", title: "Left to decide" },
  { key: "approved", title: "Covered by an approved check" },
  { key: "mine", title: "Decided by a reviewer" },
] as const;
type Group = (typeof GROUPS)[number]["key"];

/** Requirements nobody has decided and no approved check covers: what is left of the review. */
export const undecided = (clauses: Clause[], readings: Record<string, Reading>, decisions: Record<string, Determination>) =>
  clauses.filter((c) => ["todo", "approve"].includes(groupOf(readings[c.id], decisions[c.id])));

function groupOf(r?: Reading, mine?: Determination): Group {
  if (mine && !mine.stale) return "mine";
  if (r?.decision?.state === "approved") return "approved";
  if (r?.status === "DRAFTED" && !r.decision) return "approve";
  return "todo";
}

interface Shared {
  sheets: SheetView[]; viewing?: SheetView; onShowNote: (n: NoteRef) => void; canDecide: boolean;
  reload: () => Promise<void>; onError: (m: string) => void;
}

export function Requirements({ project, clauses, readings, decisions, busy, startJob, ...shared }: Shared & {
  project: Project; clauses: Clause[]; readings: Record<string, Reading>; decisions: Record<string, Determination>;
  busy: boolean; startJob: (path: string) => Promise<void>;
}) {
  const { canDecide, reload, onError } = shared;
  const [open, setOpen] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [ticks, setTicks] = useState<Record<string, Marks>>({});   // kept while moving between requirements
  const url = `/api/projects/${project.id}`;
  const ready = usePrepared(url);
  const group = (c: Clause) => groupOf(readings[c.id], decisions[c.id]);
  const left = undecided(clauses, readings, decisions).length;
  const checks = clauses.filter((c) => group(c) === "approved").length;
  const unread = clauses.filter((c) => !readings[c.id] && !decisions[c.id]).length;
  const wanted = search.trim().toLowerCase();
  const shown = clauses.filter((c) => !wanted || `${c.id} ${c.text}`.toLowerCase().includes(wanted));

  const nextAfter = (from: string) => {
    const at = clauses.findIndex((c) => c.id === from);
    return [...clauses.slice(at + 1), ...clauses.slice(0, at)].find((c) => ["todo", "approve"].includes(group(c)));
  };
  /** After a decision, open the next requirement still to decide, in the document's order. */
  const advance = (from: string) => setOpen(nextAfter(from)?.id ?? null);
  /** The next one is searched while the reviewer reads this one; the server keeps what it found. A failure waits for its turn. */
  const prepare = (from: string) => {
    const next = nextAfter(from);
    if (next) api(`${url}/parts?clause=${encodeURIComponent(next.id)}`).catch(() => {});
  };

  async function confirmInventory(value: boolean) {
    try {
      await api(url, { method: "PATCH", json: { inventory_reviewed: value } });
      await reload();
    } catch (e) { onError((e as Error).message); }
  }

  return (
    <>
      <div className="runbar">
        <p><strong>{clauses.length - left}</strong> of {clauses.length} requirements decided or covered, <strong>{left}</strong> left.</p>
        <progress max={clauses.length || 1} value={clauses.length - left} />
        {ready?.running && ready.total > 0 && (
          <p className="muted small" role="status">Searching the drawings ahead of you: {ready.done} of {ready.total} requirements
            ready. You can start now.</p>
        )}
        {canDecide && (
          <details className="auto">
            <summary>Let the tool propose measured checks ({checks} approved)</summary>
            <div className="row">
              {unread > 0 && <button disabled={busy} onClick={() => startJob("interpret")}>Read {unread} requirements</button>}
              <button className="primary" disabled={busy || (!checks && !project.rules.total)} onClick={() => startJob("check")}>
                Run the approved checks</button>
            </div>
            <p className="muted small">Reading takes about a minute a requirement on this kind of machine. You can decide any
              requirement yourself without waiting.</p>
            <label className="confirm">
              <input type="checkbox" checked={!!(project as Project & { inventory_reviewed?: boolean }).inventory_reviewed}
                onChange={(e) => confirmInventory(e.target.checked)} />
              <span>I looked over the plan and every room, door and window was found. Without this, a check can report a
                violation but never a pass.</span>
            </label>
          </details>
        )}
      </div>
      <input className="find" type="search" placeholder="Find a requirement" aria-label="Find a requirement" value={search}
        onChange={(e) => setSearch(e.target.value)} />
      {GROUPS.map((g) => {
        const rows = shown.filter((c) => group(c) === g.key);
        if (!rows.length) return null;
        return (
          <section key={g.key} className="clauses">
            <h4>{g.title} <span className="count">{rows.length}</span></h4>
            <ol className="cards">
              {rows.map((c) => (
                <ClauseCard key={c.id} url={url} clause={c} reading={readings[c.id]} group={g.key}
                  marks={ticks[c.id] ?? {}} setMarks={(m) => setTicks((all) => ({ ...all, [c.id]: m }))}
                  mine={decisions[c.id]?.stale ? undefined : decisions[c.id]} earlier={decisions[c.id]?.stale ? decisions[c.id] : undefined}
                  open={open === c.id} toggle={() => setOpen(open === c.id ? null : c.id)} advance={() => advance(c.id)}
                  prepare={() => prepare(c.id)} {...shared} />
              ))}
            </ol>
          </section>
        );
      })}
      {wanted && shown.length === 0 && <p className="muted">No requirement holds these words.</p>}
    </>
  );
}

function ClauseCard({ url, clause, reading, mine, earlier, group, open, toggle, advance, prepare, marks, setMarks, sheets, viewing,
  onShowNote, canDecide, reload, onError }:
  Shared & { url: string; clause: Clause; reading?: Reading; mine?: Determination; earlier?: Determination; group: Group; open: boolean;
    toggle: () => void; advance: () => void; prepare: () => void; marks: Marks; setMarks: (m: Marks) => void }) {
  const ref = useCardScroll(open);
  const [working, setWorking] = useState("");
  const [read, setRead] = useState(false);
  const [picked, setPicked] = useState<NoteRef | null>(null);
  const [found, setFound] = useState<PartSearch | null>(null);
  const [searching, setSearching] = useState(false);
  const notes = [...(reading?.review?.review?.issues ?? []).map((i) => i.message),
    ...(reading?.review?.review?.limitations ?? [])];
  const picks = reading?.evidence?.chosen ? { chosen: reading.evidence.chosen, checks: reading.evidence.checks } : null;
  const ticked = (found?.parts ?? []).filter((p) => marks[p.text]).map((p) => ({ text: p.text, mark: marks[p.text] }));

  // each part is searched when the card opens; the first time, a model also cuts the requirement into its parts
  const search = open && !found && !mine;
  useEffect(() => {
    if (!search) return;
    let gone = false;
    setSearching(true);
    api<PartSearch>(`${url}/parts?clause=${encodeURIComponent(clause.id)}`)
      .then((r) => { if (!gone) { setFound(r); prepare(); } })
      .catch((e) => { if (!gone) { setFound({ parts: [], split_by_model: false, left_out: [] }); onError((e as Error).message); } })
      .finally(() => { if (!gone) setSearching(false); });
    return () => { gone = true; };
    // prepare is made anew on every render; only the card opening should start a search
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, url, clause.id, onError]);

  async function call(label: string, path: string, json?: unknown) {
    setWorking(label);
    try { await api(`${url}/${path}`, { method: "POST", json }); await reload(); }
    catch (e) { onError((e as Error).message); }
    setWorking("");
  }
  const onCheck = (action: string) => call("Saving", "decision", { clause: clause.id, action, acknowledge: read });

  async function record(state: Choice | "reset", note: string, place: NoteRef | null) {
    try {
      await api(`${url}/clause-states`, { method: "PUT", json: { clause: clause.id, state, note,
        parts: state === "reset" ? [] : ticked,
        evidence: place ? { sheet: place.sheet, box: place.box ?? null, text: place.text } : null } });
      onError("");
      if (state !== "reset") advance();
      await reload();
      return true;
    } catch (e) { onError((e as Error).message); return false; }
  }

  return (
    <li ref={ref} className={`item clause ${group} ${mine ? mine.state : ""} ${open ? "open" : ""}`}>
      <button className="head" aria-expanded={open} onClick={toggle}>
        <span className="cid">{clause.id}</span>
        <span className="sum"><span className="quote-short">{plainClause(clause.text)}</span></span>
        {earlier && <span className="decided deferred">Confirm again</span>}
        {mine && <span className={`decided ${mine.state}`}>{CHOICES.find((c) => c.key === mine.state)?.done}</span>}
      </button>
      {open && (
        <div className="body">
          <blockquote>{plainClause(clause.text)}</blockquote>

          {earlier && (
            <p className="notice-line">{earlier.by} recorded "{CHOICES.find((c) => c.key === earlier.state)?.done}"
              {earlier.note && `: ${earlier.note}`}. It no longer counts because {earlier.stale}. Look again and decide.</p>
          )}

          {picks && !mine && (
            <Notes evidence={picks} sheets={sheets} onShow={onShowNote} onUse={canDecide ? setPicked : undefined}
              picked={picked} />
          )}
          {found && found.parts.length > 0 && !mine && (
            <Parts search={found} sheets={sheets} marks={marks} onShow={onShowNote} onUse={canDecide ? setPicked : undefined}
              picked={picked} setMark={canDecide ? (part, mark) => {
                const next = { ...marks };
                if (mark) next[part] = mark; else delete next[part];
                setMarks(next);
              } : undefined} />
          )}
          {searching && <p className="muted" role="status">Searching the drawings for each part</p>}

          <Decision decided={mine} sheets={sheets} viewing={viewing} picked={picked} clearPicked={() => setPicked(null)}
            canDecide={canDecide} save={record} takeBack={() => record("reset", "", null)}
            missing={ticked.filter((t) => t.mark === "missing").map((t) => t.text)} />

          {!mine && reading?.status === "DRAFTED" && (
            <>
              <h4>A measured check the tool proposes</h4>
              <p className="wording">{reading.plain || reading.readback}</p>
              {reading.plain_applies_when && <p className="muted">Applies when: {reading.plain_applies_when}</p>}
              {reading.plain_unless && <p className="muted">Unless: {reading.plain_unless}</p>}
              {reading.readback && <code className="formula">{reading.readback}</code>}
              {reading.preview && (
                <p className="where">Preview on this plan: {plainOutcome(reading.preview.outcome)}.
                  {reading.preview.missing?.length
                    ? ` Still needed: ${reading.preview.missing.map(plainNeed).join(", ")}.` : ""}</p>
              )}
              {reading.notes?.filter((n) => !n.startsWith("In the drawings:")).map((n, i) => <p key={i} className="muted">{n}</p>)}
              {reading.review && (
                <div className={notes.length ? "question" : ""}>
                  <h4>Second reading of the check</h4>
                  {notes.length ? <ul>{notes.map((n, i) => <li key={i}>{n}</li>)}</ul> : <p>Nothing to add.</p>}
                </div>
              )}
              {canDecide && !reading.decision && (
                !reading.review ? (
                  <div className="decide">
                    <button className="primary" disabled={!!working}
                      onClick={() => call("Reading again", "review", { clause: clause.id })}>{working || "Get a second reading"}</button>
                    <button disabled={!!working} onClick={() => onCheck("reject")}>This check is wrong</button>
                  </div>
                ) : (
                  <>
                    {notes.length > 0 && (
                      <label className="confirm"><input type="checkbox" checked={read} onChange={(e) => setRead(e.target.checked)} />
                        <span>I read these notes.</span></label>
                    )}
                    <div className="decide">
                      <button className="primary" disabled={!!working || (notes.length > 0 && !read)}
                        onClick={() => onCheck("approve")}>{working || "Approve this check"}</button>
                      <button disabled={!!working} onClick={() => onCheck("reject")}>This check is wrong</button>
                    </div>
                  </>
                )
              )}
              {reading.decision && (
                <div className="decide">
                  <span className="muted">{reading.decision.state === "approved" ? "Approved" : "Rejected"} by {reading.decision.by}</span>
                  {canDecide && <button disabled={!!working} onClick={() => onCheck("reset")}>Withdraw</button>}
                </div>
              )}
            </>
          )}
          {!mine && reading?.status === "UNRESOLVED" && (
            <details className="why-not"><summary>Why the tool has no measured check</summary><p>{reading.reason}</p></details>
          )}
          {!mine && canDecide && !reading && (
            <p><button className="link" disabled={!!working}
              onClick={() => call("Reading", `interpret/${encodeURIComponent(clause.id)}`)}>
              {working ? "Reading, about a minute" : "Ask the tool for a measured check"}</button></p>
          )}
        </div>
      )}
    </li>
  );
}

/** How far the server has searched ahead; asked again every few seconds while it is still at it. */
function usePrepared(url: string) {
  const [state, setState] = useState<{ done: number; total: number; running: boolean } | null>(null);
  useEffect(() => {
    let gone = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const ask = () => api<{ done: number; total: number; running: boolean }>(`${url}/prepared`)
      .then((r) => { if (gone) return; setState(r); if (r.running) timer = setTimeout(ask, 5000); })
      .catch(() => {});
    ask();
    return () => { gone = true; clearTimeout(timer); };
  }, [url]);
  return state;
}

/** Keeps the card the desk moved to in view. */
function useCardScroll(open: boolean) {
  const [node, setNode] = useState<HTMLLIElement | null>(null);
  useEffect(() => { if (open) node?.scrollIntoView({ block: "nearest" }); }, [open, node]);
  return setNode;
}
