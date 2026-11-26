import { useCallback, useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { ReviewDesk } from "./review/ReviewDesk";
import { api, has, setCsrf, whenSignedOut, type Session, type User } from "./api";
import { Logo, Problem, Spinner } from "./ui";
import { Join, SignIn } from "./pages/SignIn";
import { MyWork } from "./pages/MyWork";
import { Submission } from "./pages/Submission";
import { Team } from "./pages/Team";

export function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [problem, setProblem] = useState("");
  const location = useLocation();

  const apply = useCallback((s: Session) => { setCsrf(s.csrf); setSession(s); }, []);
  useEffect(() => {
    whenSignedOut(() => setSession((s) => (s ? { ...s, user: null, csrf: null } : s)));
    api<Session>("/api/auth/session").then(apply).catch((e: Error) => setProblem(e.message));
  }, [apply]);

  const signedIn = (user: User, csrf: string) => apply({ user, csrf, set_up: true });

  if (problem) return <div className="centre"><Problem text={problem} /></div>;
  if (!session) return <div className="centre"><Spinner label="Opening ReviewPulse" /></div>;
  if (location.pathname.startsWith("/join/")) {
    return <Routes><Route path="/join/:token" element={<Join onSignedIn={signedIn} />} /></Routes>;
  }
  if (!session.user) return <SignIn setUp={session.set_up} onSignedIn={signedIn} />;
  if (/^\/submissions\/[^/]+\/review$/.test(location.pathname) && has(session.user, "admin", "coordinator", "reviewer")) {
    return <Routes><Route path="/submissions/:id/review" element={<ReviewDesk user={session.user} />} /></Routes>;
  }
  return <Shell user={session.user} onSignOut={async () => {
    await api("/api/auth/sign-out", { method: "POST" }).catch(() => undefined);
    apply({ user: null, csrf: null, set_up: true });
  }} />;
}

function Shell({ user, onSignOut }: { user: User; onSignOut: () => void }) {
  const office = has(user, "admin", "coordinator", "reviewer");
  return (
    <div className="shell">
      <aside className="rail">
        <div className="brand"><Logo /><span>ReviewPulse</span></div>
        <div className="office">{user.organisation}</div>
        <nav aria-label="Main">
          {office && <NavLink to="/" end>My work</NavLink>}
          {has(user, "admin") && <NavLink to="/team">Team</NavLink>}
        </nav>
        <div className="me">
          <strong>{user.name}</strong>
          <span>{user.roles.join(" and ")}</span>
          <button className="link" onClick={onSignOut}>Sign out</button>
        </div>
      </aside>
      <main className="content">
        {office ? (
          <Routes>
            <Route path="/" element={<MyWork user={user} />} />
            <Route path="/submissions/:id" element={<Submission user={user} />} />
            {has(user, "admin") && <Route path="/team" element={<Team me={user} />} />}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        ) : (
          <section className="empty">
            <h1>Your account is ready</h1>
            <p>The page where applicants answer review comments is not available yet. The office reviewing your
              submission will send you its comments directly.</p>
          </section>
        )}
      </main>
    </div>
  );
}
