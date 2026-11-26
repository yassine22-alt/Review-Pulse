import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type Job, type Project, type User } from "../api";
import { Logo, Problem, Spinner } from "../ui";
import { Findings, toneOf, type ItemActions } from "./Findings";
import { Requirements } from "./Requirements";
import { SheetCanvas, type Mark } from "./SheetCanvas";
import { SignOffDrawer } from "./SignOff";
import { shapesOf, type Clause, type CorrectionList, type Reading, type View } from "./types";

interface Data {
  project: Project; view: View | null; list: CorrectionList;
  clauses: Clause[]; readings: Record<string, Reading>; jobs: Job[];
}

export function ReviewDesk({ user }: { user: User }) {
  const { id = "" } = useParams();
  const [data, setData] = useState<Data | null>(null);
  const [problem, setProblem] = useState("");
  const [tab, setTab] = useState<"corrections" | "requirements" | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [opened, setOpened] = useState<Set<string>>(new Set());
  const [sheet, setSheet] = useState(0);
  const [focus, setFocus] = useState(0);
  const [editing, setEditing] = useState(false);
  const [signing, setSigning] = useState(false);
  const canDecide = user.roles.includes("reviewer");

  const load = useCallback(async () => {
    const url = `/api/projects/${id}`;
    try {
      const [project, view, list, doc, readings, jobs] = await Promise.all([
        api<Project>(url),
        api<View>(`${url}/view`).catch(() => null),
        api<CorrectionList>(`${url}/correction-list`),
        api<{ clauses: Clause[] }>(`${url}/document`).catch(() => ({ clauses: [] as Clause[] })),
        api<Record<string, Reading>>(`${url}/interpreted`),
        api<Job[]>(`${url}/jobs`),
      ]);
      setData({ project, view, list, clauses: doc.clauses, readings, jobs });
      setTab((t) => t ?? (list.items.length ? "corrections" : "requirements"));
    } catch (e) { setProblem((e as Error).message); }
  }, [id]);
  useEffect(() => { load(); }, [load]);

  const running = data?.jobs.filter((j) => j.status === "queued" || j.status === "running") ?? [];
  useEffect(() => {
    if (!running.length) return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [running.length, load]);

  const places = useMemo(() => new Map((data?.list.items ?? []).map((i) =>
    [i.key, shapesOf(i, data!.view)])), [data]);
  const located = useMemo(() => new Set([...places].filter(([, p]) => p.length).map(([k]) => k)), [places]);

  const select = useCallback((key: string | null) => {
    setSelected(key);
    setEditing(false);
    if (!key) return;
    setTab("corrections");
    setOpened((o) => new Set(o).add(key));
    const first = places.get(key)?.[0];
    if (first) setSheet((s) => (places.get(key)!.some((p) => p.sheet === s) ? s : first.sheet));
    setFocus((f) => f + 1);
  }, [places]);

  const actions: ItemActions = useMemo(() => {
    const run = async (work: () => Promise<unknown>) => {
      try { await work(); setProblem(""); await load(); } catch (e) { setProblem((e as Error).message); }
    };
    const url = `/api/projects/${id}`;
    return {
      decide: async (item, action, wording) => {
        await run(() => api(`${url}/correction-list/items/${encodeURIComponent(item.key)}`,
          { method: "PUT", json: { action, wording } }));
      },
      setAside: (item, state, note) => run(() => api(`${url}/clause-states`,
        { method: "PUT", json: { clause: item.clause, state, note } })),
      restore: (clause) => run(() => api(`${url}/clause-states`, { method: "PUT", json: { clause, state: "reset" } })),
    };
  }, [id, load]);

  useEffect(() => {
    const keys = (e: KeyboardEvent) => {
      if (!data || signing || tab !== "corrections" || e.ctrlKey || e.metaKey || e.altKey) return;
      if ((e.target as Element).closest("input, textarea, select")) return;
      const items = data.list.items;
      const at = items.findIndex((i) => i.key === selected);
      const item = items[at];
      const k = e.key.toLowerCase();
      if (k === "j" || k === "k") {
        const next = items[Math.min(items.length - 1, Math.max(0, at + (k === "j" ? 1 : -1)))];
        if (next) select(next.key);
      } else if (k === "escape") select(null);
      else if (k === "enter" && item && !(e.target as Element).closest("button, a")) setFocus((f) => f + 1);
      else if (item && canDecide && item.review.action === "pending") {
        if (k === "a" && (opened.has(item.key) || !located.has(item.key))) actions.decide(item, "accept");
        else if (k === "d") actions.decide(item, "drop");
        else if (k === "e") { e.preventDefault(); setEditing(true); }
      }
    };
    window.addEventListener("keydown", keys);
    return () => window.removeEventListener("keydown", keys);
  }, [data, selected, tab, signing, canDecide, opened, located, actions, select]);

  if (!data) {
    return <div className="centre">{problem ? <><Problem text={problem} /><Link to="/">Back to my work</Link></>
      : <Spinner label="Opening the review desk" />}</div>;
  }
  const { project, view, list } = data;
  const current = view?.sheets.find((s) => s.index === sheet) ?? view?.sheets[0];
  const marks: Mark[] = list.items.filter((i) => !i.dropped).map((i) => ({
    key: i.key, label: String(i.n ?? ""), tone: toneOf(i),
    shapes: (places.get(i.key) ?? []).filter((p) => p.sheet === current?.index).map((p) => p.shape),
  })).filter((m) => m.shapes.length);
  const reviewed = list.edit_burden.items - list.edit_burden.unreviewed;

  async function startJob(path: string) {
    try { await api(`/api/projects/${id}/${path}`, { method: "POST" }); setProblem(""); await load(); }
    catch (e) { setProblem((e as Error).message); }
  }

  return (
    <div className="desk">
      <header className="deskbar">
        <Link to={`/submissions/${project.id}`} className="back" aria-label="Back to the submission"><Logo /></Link>
        <div className="what"><strong>{project.name}</strong><small>{project.plan} · round {list.cycle}</small></div>
        <div className="progressline">
          {list.items.length > 0 && <><progress max={list.items.length} value={reviewed} />
            <span>{reviewed} of {list.items.length} decided</span></>}
        </div>
        <Link to="/">My work</Link>
        <button className="primary" onClick={() => setSigning(true)}>Sign off and export</button>
      </header>
      <div className="stagearea">
        {current ? (
          <SheetCanvas key={current.index} project={project.id} sheet={current} marks={marks} selected={selected}
            focus={focus} onSelect={select} />
        ) : <div className="canvas none"><p>The drawings have not been read yet.</p></div>}
        {view && view.sheets.length > 1 && (
          <nav className="filmstrip" aria-label="Sheets">
            {view.sheets.map((s) => {
              const n = list.items.filter((i) => !i.dropped && places.get(i.key)?.some((p) => p.sheet === s.index)).length;
              return (
                <button key={s.index} aria-current={s.index === current?.index} onClick={() => setSheet(s.index)}>
                  <img src={`/api/projects/${project.id}/sheets/${s.index}/backdrop.png`} alt="" loading="lazy" />
                  <span>Sheet {s.index + 1}</span>{n > 0 && <b>{n}</b>}
                </button>
              );
            })}
          </nav>
        )}
        {running.map((j) => (
          <div className="floating" key={j.id} role="status">
            <progress max={1} value={j.progress} /><span>{j.message || "Working"}</span>
          </div>
        ))}
      </div>
      <aside className="inspector">
        <div className="tabs" role="tablist">
          <button role="tab" aria-selected={tab === "corrections"} onClick={() => setTab("corrections")}>
            Corrections <span className="count">{list.items.length}</span></button>
          <button role="tab" aria-selected={tab === "requirements"} onClick={() => setTab("requirements")}>
            Requirements <span className="count">{data.clauses.length}</span></button>
        </div>
        <div className="scroll">
          <Problem text={problem} />
          {tab === "corrections" ? (
            <Findings sheets={view?.sheets ?? []} list={list} located={located} selected={selected} opened={opened} canDecide={canDecide}
              editing={editing} setEditing={setEditing} onSelect={(k) => select(selected === k ? null : k)}
              onZoom={() => selected && select(selected)} actions={actions} />
          ) : (
            <Requirements project={project} clauses={data.clauses} readings={data.readings} canDecide={canDecide}
              busy={running.length > 0} reload={load} onError={setProblem} startJob={startJob} />
          )}
        </div>
        {tab === "corrections" && list.items.length > 0 && (
          <footer className="keys"><kbd>J</kbd><kbd>K</kbd> move <kbd>Enter</kbd> zoom <kbd>A</kbd> accept <kbd>E</kbd> edit
            <kbd>D</kbd> drop <kbd>Esc</kbd> whole sheet</footer>
        )}
      </aside>
      {signing && <SignOffDrawer project={project.id} list={list} canSign={canDecide} close={() => setSigning(false)} reload={load} />}
    </div>
  );
}
