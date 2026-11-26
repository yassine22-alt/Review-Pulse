import { useState } from "react";
import { api, type Project } from "../api";
import { plainNeed, plainOutcome } from "./plain";
import type { Clause, Reading } from "./types";

const GROUPS = [
  { key: "approve", title: "Waiting for your approval" },
  { key: "approved", title: "Approved checks" },
  { key: "manual", title: "Check these yourself" },
  { key: "unread", title: "Not read yet" },
] as const;

function groupOf(r?: Reading) {
  if (!r) return "unread";
  if (r.decision?.state === "approved") return "approved";
  if (r.status === "DRAFTED" && !r.decision) return "approve";
  return "manual";
}

export function Requirements({ project, clauses, readings, canDecide, busy, reload, onError, startJob }: {
  project: Project; clauses: Clause[]; readings: Record<string, Reading>; canDecide: boolean; busy: boolean;
  reload: () => Promise<void>; onError: (m: string) => void; startJob: (path: string) => Promise<void>;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const url = `/api/projects/${project.id}`;
  const approved = clauses.filter((c) => groupOf(readings[c.id]) === "approved").length;
  const unread = clauses.filter((c) => !readings[c.id]).length;

  async function confirmInventory(value: boolean) {
    try {
      await api(url, { method: "PATCH", json: { inventory_reviewed: value } });
      await reload();
    } catch (e) { onError((e as Error).message); }
  }

  return (
    <>
      <div className="runbar">
        <p><strong>{approved}</strong> of {clauses.length} requirements have an approved check.</p>
        {canDecide && (
          <div className="row">
            {unread > 0 && <button disabled={busy} onClick={() => startJob("interpret")}>Read {unread} requirements</button>}
            <button className="primary" disabled={busy || (!approved && !project.rules.total)} onClick={() => startJob("check")}>
              Run the checks</button>
          </div>
        )}
        {canDecide && (
          <label className="confirm">
            <input type="checkbox" checked={!!(project as Project & { inventory_reviewed?: boolean }).inventory_reviewed}
              onChange={(e) => confirmInventory(e.target.checked)} />
            <span>I looked over the plan and every room, door and window was found. Without this, a check can report a
              violation but never a pass.</span>
          </label>
        )}
      </div>
      {GROUPS.map((g) => {
        const rows = clauses.filter((c) => groupOf(readings[c.id]) === g.key);
        if (!rows.length) return null;
        return (
          <section key={g.key} className="clauses">
            <h4>{g.title} <span className="count">{rows.length}</span></h4>
            <ol className="cards">
              {rows.map((c) => (
                <ClauseCard key={c.id} url={url} clause={c} reading={readings[c.id]} open={open === c.id}
                  toggle={() => setOpen(open === c.id ? null : c.id)} canDecide={canDecide} reload={reload} onError={onError} />
              ))}
            </ol>
          </section>
        );
      })}
    </>
  );
}

function ClauseCard({ url, clause, reading, open, toggle, canDecide, reload, onError }: {
  url: string; clause: Clause; reading?: Reading; open: boolean; toggle: () => void; canDecide: boolean;
  reload: () => Promise<void>; onError: (m: string) => void;
}) {
  const [working, setWorking] = useState("");
  const [read, setRead] = useState(false);
  const notes = [...(reading?.review?.review?.issues ?? []).map((i) => i.message),
    ...(reading?.review?.review?.limitations ?? [])];

  async function call(label: string, path: string, json?: unknown) {
    setWorking(label);
    try { await api(`${url}/${path}`, { method: "POST", json }); await reload(); }
    catch (e) { onError((e as Error).message); }
    setWorking("");
  }
  const decide = (action: string) => call("Saving", "decision", { clause: clause.id, action, acknowledge: read });

  return (
    <li className={`item clause ${groupOf(reading)} ${open ? "open" : ""}`}>
      <button className="head" aria-expanded={open} onClick={toggle}>
        <span className="cid">{clause.id}</span>
        <span className="sum"><span className="quote-short">{clause.text}</span></span>
      </button>
      {open && (
        <div className="body">
          <blockquote>{clause.text}</blockquote>
          {reading?.status === "DRAFTED" && (
            <>
              <h4>The check that would run</h4>
              <p className="wording">{reading.plain || reading.readback}</p>
              {reading.plain_applies_when && <p className="muted">Applies when: {reading.plain_applies_when}</p>}
              {reading.plain_unless && <p className="muted">Unless: {reading.plain_unless}</p>}
              {reading.readback && <code className="formula">{reading.readback}</code>}
              {reading.preview && (
                <p className="where">Preview on this plan: {plainOutcome(reading.preview.outcome)}.
                  {reading.preview.missing?.length
                    ? ` Still needed: ${reading.preview.missing.map(plainNeed).join(", ")}.` : ""}</p>
              )}
            </>
          )}
          {reading?.status === "UNRESOLVED" && <div className="question"><h4>Why there is no check</h4><p>{reading.reason}</p></div>}
          {reading?.notes?.map((n, i) => <p key={i} className="muted">{n}</p>)}
          {reading?.review && (
            <div className={notes.length ? "question" : ""}>
              <h4>Second reading of the check</h4>
              {notes.length ? <ul>{notes.map((n, i) => <li key={i}>{n}</li>)}</ul> : <p>Nothing to add.</p>}
            </div>
          )}
          {canDecide && reading?.status === "DRAFTED" && !reading.decision && (
            !reading.review ? (
              <div className="decide">
                <button className="primary" disabled={!!working} onClick={() => call("Reading again", "review", { clause: clause.id })}>
                  {working || "Get a second reading"}</button>
                <button disabled={!!working} onClick={() => decide("reject")}>This check is wrong</button>
              </div>
            ) : (
              <>
                {notes.length > 0 && (
                  <label className="confirm"><input type="checkbox" checked={read} onChange={(e) => setRead(e.target.checked)} />
                    <span>I read these notes.</span></label>
                )}
                <div className="decide">
                  <button className="primary" disabled={!!working || (notes.length > 0 && !read)} onClick={() => decide("approve")}>
                    {working || "Approve this check"}</button>
                  <button disabled={!!working} onClick={() => decide("reject")}>This check is wrong</button>
                </div>
              </>
            )
          )}
          {reading?.decision && (
            <div className="decide">
              <span className="muted">{reading.decision.state === "approved" ? "Approved" : "Rejected"} by {reading.decision.by}</span>
              {canDecide && <button disabled={!!working} onClick={() => decide("reset")}>Withdraw</button>}
            </div>
          )}
          {canDecide && !reading && (
            <div className="decide">
              <button className="primary" disabled={!!working}
                onClick={() => call("Reading", `interpret/${encodeURIComponent(clause.id)}`)}>{working || "Read this requirement"}</button>
            </div>
          )}
        </div>
      )}
    </li>
  );
}
