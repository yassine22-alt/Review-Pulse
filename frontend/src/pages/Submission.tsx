import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type Job, type Project, type User } from "../api";
import { stage } from "../stage";
import { Problem, Spinner, when } from "../ui";

const PLAN_TYPES = ".pdf,.dxf,.dwg,.svg,.png,.jpg,.jpeg,.tif,.tiff";
const REQ_TYPES = ".pdf,.md,.txt,.docx,.xlsx,.xlsm,.csv,.tsv,.html,.htm,.png,.jpg,.jpeg,.tif,.tiff";
const JOB_NAMES: Record<string, string> = {
  analyse: "Reading the drawings", draft: "Reading the requirements", check: "Running the checks", interpret: "Reading each requirement",
  backcheck: "Comparing with the earlier version",
};

export function Submission({ user }: { user: User }) {
  const { id = "" } = useParams();
  const [project, setProject] = useState<Project | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [problem, setProblem] = useState("");
  const [sending, setSending] = useState("");

  const load = useCallback(async () => {
    try {
      // jobs first: asked beside the project, a job ending between the two answers left the page showing the old state for good
      const j = await api<Job[]>(`/api/projects/${id}/jobs`);
      const p = await api<Project>(`/api/projects/${id}`);
      setProject(p);
      setJobs(j);
    } catch (e) { setProblem((e as Error).message); }
  }, [id]);
  useEffect(() => { load(); }, [load]);
  const running = jobs.filter((j) => j.status === "queued" || j.status === "running");
  useEffect(() => {
    if (!running.length) return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [running.length, load]);

  async function upload(kind: "plan" | "requirements", file: File) {
    const form = new FormData();
    form.append("file", file);
    setSending(kind);
    setProblem("");
    try {
      await api(`/api/projects/${id}/${kind}`, { method: "POST", form });
      await load();
    } catch (e) { setProblem((e as Error).message); }
    setSending("");
  }

  if (!project) return problem ? <Problem text={problem} /> : <Spinner label="Opening the submission" />;
  const s = stage(project);
  const failed = jobs.filter((j) => j.status === "failed");
  const reviewable = project.analysed && !!project.requirements && running.length === 0;
  return (
    <>
      <p className="crumb"><Link to="/">My work</Link></p>
      <header className="pagehead">
        <div>
          <h1>{project.name}</h1>
          <p className="muted">Updated {when(project.updated)}. {s.next}</p>
        </div>
        <span className={`chip ${s.lane}`}>{s.label}</span>
      </header>
      <Problem text={problem} />
      <div className="grid">
        <Drop title="Plan set" file={project.plan} accept={PLAN_TYPES} sending={sending === "plan"}
          disabled={running.length > 0} help="Vector PDF or DXF reads best. Scans are read with less certainty."
          onFile={(f) => upload("plan", f)} />
        <Drop title="Code or checklist" file={project.requirements} accept={REQ_TYPES} sending={sending === "requirements"}
          disabled={running.length > 0} help="The document this submission is reviewed against."
          onFile={(f) => upload("requirements", f)} />
      </div>
      {running.map((j) => (
        <div className="card job" key={j.id} role="status">
          <strong>{JOB_NAMES[j.kind] ?? j.kind}</strong>
          <progress max={1} value={j.progress} />
          <span className="muted small">{j.message || "Waiting to start"}. Large drawing sets can take many minutes.
            You can leave this page.</span>
        </div>
      ))}
      {failed.length > 0 && running.length === 0 && (
        <Problem text={`${JOB_NAMES[failed[0].kind] ?? failed[0].kind} did not finish: ${failed[0].error}`} />
      )}
      {reviewable && (
        <section className="card cta">
          <div>
            <h2>Review desk</h2>
            <p className="muted">The drawings beside each requirement: approve the checks, then decide each finding.</p>
          </div>
          <Link className="button primary" to={`/submissions/${project.id}/review`}>Open the review desk</Link>
        </section>
      )}
      {reviewable && (
        <section className="card">
          <h2>Correction list</h2>
          <p className="muted">It holds the findings of the checks a reviewer has approved. An empty list does not mean the
            plans comply.</p>
          <div className="actions">
            <a className="button" href={`/api/projects/${project.id}/correction-list?format=html`} target="_blank"
              rel="noreferrer">Open the list</a>
            <a className="button" href={`/api/projects/${project.id}/correction-list?format=pdf`} target="_blank"
              rel="noreferrer">Marked up drawings</a>
            <a className="button" href={`/api/projects/${project.id}/correction-list?format=csv`}>Download as CSV</a>
          </div>
          {!user.roles.includes("reviewer") && <p className="muted small">Only a reviewer can approve checks and sign off.</p>}
        </section>
      )}
    </>
  );
}

function Drop({ title, file, accept, help, sending, disabled, onFile }: {
  title: string; file: string | null; accept: string; help: string; sending: boolean; disabled: boolean;
  onFile: (f: File) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const take = (f?: File) => { if (f && !disabled && !sending) onFile(f); };
  return (
    <section className={`card drop ${over ? "over" : ""} ${file ? "filled" : ""}`}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); take(e.dataTransfer.files[0]); }}>
      <h2>{title}</h2>
      <p className={file ? "filename" : "muted"}>{file ?? "Nothing uploaded yet. Drop a file here."}</p>
      <p className="muted small">{help}</p>
      <input ref={input} type="file" accept={accept} hidden
        onChange={(e) => { take(e.target.files?.[0]); e.target.value = ""; }} />
      <button className={file ? "" : "primary"} disabled={disabled || sending}
        onClick={() => {
          if (!file || window.confirm("Replacing this file clears the results made from it. Continue?")) input.current?.click();
        }}>
        {sending ? "Uploading" : file ? "Replace file" : "Choose file"}
      </button>
    </section>
  );
}
