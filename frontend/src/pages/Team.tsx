import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, type Member, type Role, type User } from "../api";
import { Field, Problem, Spinner } from "../ui";

const CHOICES: { key: Role; label: string; can: string }[] = [
  { key: "reviewer", label: "Reviewer", can: "Approves checks, decides findings and signs off." },
  { key: "coordinator", label: "Coordinator", can: "Opens submissions and uploads files. Cannot decide findings." },
  { key: "admin", label: "Administrator", can: "Manages the team." },
  { key: "applicant", label: "Applicant", can: "Outside the office. Sees no submissions yet." },
];

export function Team({ me }: { me: User }) {
  const [members, setMembers] = useState<Member[] | null>(null);
  const [problem, setProblem] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("reviewer");
  const [link, setLink] = useState("");
  const [copied, setCopied] = useState(false);

  const load = useCallback(() => api<Member[]>("/api/admin/members").then(setMembers)
    .catch((e: Error) => setProblem(e.message)), []);
  useEffect(() => { load(); }, [load]);

  async function invite(e: FormEvent) {
    e.preventDefault();
    setProblem("");
    setLink("");
    setCopied(false);
    try {
      const out = await api<{ token: string }>("/api/admin/invitations", { method: "POST", json: { email, roles: [role] } });
      setLink(`${window.location.origin}${window.location.pathname}#/join/${out.token}`);
      setEmail("");
    } catch (err) { setProblem((err as Error).message); }
  }

  async function setActive(m: Member, active: boolean) {
    if (!active && !window.confirm(`Turn off the account of ${m.name}? They are signed out at once.`)) return;
    try {
      await api(`/api/admin/members/${m.id}`, { method: "PATCH", json: { active } });
      await load();
    } catch (err) { setProblem((err as Error).message); }
  }

  return (
    <>
      <header className="pagehead"><div><h1>Team</h1><p className="muted">Who can work in {me.organisation}.</p></div></header>
      <form className="card inline" onSubmit={invite}>
        <Field label="Email">
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label="Role" hint={CHOICES.find((c) => c.key === role)!.can}>
          <select value={role} onChange={(e) => setRole(e.target.value as Role)}>
            {CHOICES.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
          </select>
        </Field>
        <button className="primary">Create invitation</button>
      </form>
      {link && (
        <div className="card notice">
          <strong>Send this link to them yourself.</strong>
          <p className="muted small">It works once, for 7 days. It is shown only now.</p>
          <code>{link}</code>
          <button onClick={() => navigator.clipboard?.writeText(link).then(() => setCopied(true))}>
            {copied ? "Copied" : "Copy link"}
          </button>
        </div>
      )}
      <Problem text={problem} />
      {!members ? <Spinner label="Loading the team" /> : (
        <table className="card">
          <thead><tr><th>Name</th><th>Email</th><th>Role</th><th><span className="sr">Account</span></th></tr></thead>
          <tbody>
            {members.map((m) => (
              <tr key={m.id} className={m.active ? "" : "off"}>
                <td>{m.name}{m.id === me.id && " (you)"}</td>
                <td>{m.email}</td>
                <td>{m.roles.join(", ")}</td>
                <td>{m.id !== me.id && (
                  <button className="link" onClick={() => setActive(m, !m.active)}>{m.active ? "Turn off" : "Turn on"}</button>
                )}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
