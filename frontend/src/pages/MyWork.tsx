import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type Project, type User } from "../api";
import { stage, type Lane } from "../stage";
import { Field, Problem, Spinner, when } from "../ui";

const LANES: { key: Lane; title: string; empty: string }[] = [
  { key: "review", title: "Ready for you", empty: "Nothing is waiting for your review." },
  { key: "working", title: "Being read", empty: "No files are being read." },
  { key: "waiting", title: "Missing something", empty: "No submission is missing a file." },
];

export function MyWork({ user }: { user: User }) {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [problem, setProblem] = useState("");
  const [name, setName] = useState("");
  const [opening, setOpening] = useState(false);
  const [search, setSearch] = useState("");
  const navigate = useNavigate();

  const load = useCallback(() => api<Project[]>("/api/projects")
    .then((p) => { setProjects(p); setProblem(""); }).catch((e: Error) => setProblem(e.message)), []);
  useEffect(() => { load(); }, [load]);
  const busy = !!projects?.some((p) => p.active_jobs.length);
  useEffect(() => {
    if (!busy) return;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [busy, load]);

  async function create(e: FormEvent) {
    e.preventDefault();
    try {
      const p = await api<Project>("/api/projects", { method: "POST", json: { name } });
      navigate(`/submissions/${p.id}`);
    } catch (err) { setProblem((err as Error).message); }
  }

  const shown = (projects ?? []).filter((p) => p.name.toLowerCase().includes(search.trim().toLowerCase()));
  return (
    <>
      <header className="pagehead">
        <div>
          <h1>My work</h1>
          <p className="muted">Hello {user.name.split(" ")[0]}. These are your office's submissions.</p>
        </div>
        <button className="primary" onClick={() => setOpening((o) => !o)} aria-expanded={opening}>New submission</button>
      </header>
      {opening && (
        <form className="card inline" onSubmit={create}>
          <Field label="Name of the submission" hint="For example the address and the permit number.">
            <input autoFocus required maxLength={140} value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <button className="primary">Open it</button>
        </form>
      )}
      <Problem text={problem} />
      {!projects && !problem && <Spinner label="Loading submissions" />}
      {projects && projects.length === 0 && (
        <section className="empty">
          <h2>No submissions yet</h2>
          <p>Open a new submission, then add the plan set and the code or checklist it is reviewed against.</p>
        </section>
      )}
      {projects && projects.length > 0 && (
        <>
          <div className="stats">
            {LANES.map((l) => (
              <div key={l.key} className={l.key}>
                <strong>{projects.filter((p) => stage(p).lane === l.key).length}</strong>
                <span>{l.title}</span>
              </div>
            ))}
          </div>
          <input className="search" type="search" placeholder="Find a submission" aria-label="Find a submission"
            value={search} onChange={(e) => setSearch(e.target.value)} />
          {LANES.map((lane) => {
            const rows = shown.filter((p) => stage(p).lane === lane.key);
            return (
              <section key={lane.key} className={`lane ${lane.key}`}>
                <h2>{lane.title} <span className="count">{rows.length}</span></h2>
                {rows.length === 0 ? <p className="muted small">{lane.empty}</p> : (
                  <ul className="queue">
                    {rows.map((p) => {
                      const s = stage(p);
                      return (
                        <li key={p.id}>
                          <Link to={`/submissions/${p.id}`}>
                            <span className="title">{p.name}<small>{p.plan ?? "no drawings yet"}</small></span>
                            <span className={`chip ${lane.key}`}>{s.label}</span>
                            <span className="next">{s.next}</span>
                            <time dateTime={p.updated}>{when(p.updated)}</time>
                          </Link>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </section>
            );
          })}
        </>
      )}
    </>
  );
}
