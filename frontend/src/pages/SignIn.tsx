import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, setCsrf, type User } from "../api";
import { Field, Logo, Problem, Spinner } from "../ui";

type Done = (user: User, csrf: string) => void;
interface Signed { user: User; csrf: string }

/** An illustration of what the review desk shows, drawn here and labelled as an example. */
function Sample() {
  return (
    <div className="sample">
      <svg viewBox="0 0 560 300" role="img" aria-label="Example: a door marked on a floor plan with its finding">
        <path className="walls" d="M30 30H530V270H30Z M230 30V120 M230 168V270 M230 150H310 M356 150H530" />
        <path className="thin" d="M230 120A48 48 0 0 1 278 168H230 M310 150A46 46 0 0 0 356 196V150" />
        <text x="130" y="214">BEDROOM</text><text x="430" y="92">KITCHEN</text><text x="450" y="238">HALL</text>
        <rect className="hit" x="304" y="138" width="58" height="64" rx="4" />
        <path className="pinhead" d="M333 138c-3-9-14-13-14-24a14 14 0 1 1 28 0c0 11-11 15-14 24Z" />
        <text x="333" y="118">1</text>
      </svg>
      <figure>
        <b>Revision required</b>
        <q>Every door has a clear width of at least 0.80 m.</q>
        <figcaption>Measured 0.70 m at this door.</figcaption>
      </figure>
      <p className="sample-note">Example</p>
    </div>
  );
}

function Door({ title, lead, children }: { title: string; lead: string; children: ReactNode }) {
  return (
    <div className="door">
      <section className="pitch">
        <div className="brand"><Logo /><span>ReviewPulse</span></div>
        <h2>Every finding shows its rule and its place on the drawing.</h2>
        <p>The requirement is quoted as your document words it. What the drawings cannot settle is said so. You decide.</p>
        <Sample />
      </section>
      <section className="panel">
        <h1>{title}</h1>
        <p className="muted">{lead}</p>
        {children}
      </section>
    </div>
  );
}

export function SignIn({ setUp, onSignedIn }: { setUp: boolean; onSignedIn: Done }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setProblem("");
    try {
      const out = await api<Signed>("/api/auth/sign-in", { method: "POST", json: { email, password } });
      onSignedIn(out.user, out.csrf);
    } catch (err) {
      setProblem((err as Error).message);
      setBusy(false);
    }
  }

  if (!setUp) {
    return (
      <Door title="Set up your office" lead="No account exists on this server yet.">
        <p>The person who runs the server creates the first administrator with this command, then reloads this page:</p>
        <pre>rp create-admin</pre>
      </Door>
    );
  }
  return (
    <Door title="Sign in" lead="Use the account your office gave you.">
      <form onSubmit={submit}>
        <Field label="Email">
          <input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label="Password">
          <input type="password" autoComplete="current-password" required value={password}
            onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <Problem text={problem} />
        <button className="primary" disabled={busy}>{busy ? "Signing in" : "Sign in"}</button>
      </form>
      <p className="muted small">No account, or forgot your password? Ask your office administrator.</p>
    </Door>
  );
}

export function Join({ onSignedIn }: { onSignedIn: Done }) {
  const { token = "" } = useParams();
  const navigate = useNavigate();
  const [invite, setInvite] = useState<{ email: string; organisation: string; roles: string[] } | null>(null);
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<{ email: string; organisation: string; roles: string[] }>(`/api/auth/invitations/${encodeURIComponent(token)}`)
      .then(setInvite).catch((e: Error) => setProblem(e.message));
  }, [token]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setProblem("");
    try {
      const out = await api<Signed>(`/api/auth/invitations/${encodeURIComponent(token)}/accept`,
        { method: "POST", json: { name, password } });
      setCsrf(out.csrf);
      navigate("/", { replace: true });
      onSignedIn(out.user, out.csrf);
    } catch (err) {
      setProblem((err as Error).message);
      setBusy(false);
    }
  }

  if (!invite) {
    return (
      <Door title="Invitation" lead="">
        {problem ? <><Problem text={problem} /><a href="#/" onClick={() => navigate("/")}>Go to sign in</a></>
          : <Spinner label="Checking your invitation" />}
      </Door>
    );
  }
  return (
    <Door title={`Join ${invite.organisation}`} lead={`${invite.email}, as ${invite.roles.join(" and ")}.`}>
      <form onSubmit={submit}>
        <Field label="Your full name" hint="It appears on the decisions you make.">
          <input autoComplete="name" required minLength={2} maxLength={80} value={name}
            onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="Choose a password" hint="12 characters or more. A few unrelated words work well.">
          <input type="password" autoComplete="new-password" required minLength={12} maxLength={128} value={password}
            onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <Problem text={problem} />
        <button className="primary" disabled={busy}>{busy ? "Creating your account" : "Create my account"}</button>
      </form>
    </Door>
  );
}
