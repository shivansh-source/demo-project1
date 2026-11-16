import { useEffect, useState } from "react";
import { api } from "./api";
import { isLoggedIn, logout } from "./auth";
import { ImportPanel } from "./components/ImportPanel";
import { CrmPanel } from "./components/CrmPanel";
import { JobsPanel } from "./components/JobsPanel";
import { LeadDetailView } from "./components/LeadDetail";
import { LeadsTable } from "./components/LeadsTable";
import { useLoad } from "./hooks";
import { HowItWorks } from "./pages/HowItWorks";
import { Landing } from "./pages/Landing";
import { LoginPage } from "./pages/Login";

type Page = "home" | "how" | "login" | "dashboard";
type Tab = "leads" | "import" | "crm" | "jobs";
const PAGES: Page[] = ["home", "how", "login", "dashboard"];

function pageFromHash(): Page {
  const h = window.location.hash.replace("#/", "") as Page;
  return PAGES.includes(h) ? h : "home";
}

export default function App() {
  const [page, setPage] = useState<Page>(pageFromHash());
  const [authed, setAuthed] = useState(isLoggedIn());
  const [tab, setTab] = useState<Tab>("leads");
  const [selected, setSelected] = useState<number | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const health = useLoad(() => api.health(), []);

  useEffect(() => {
    const onHash = () => setPage(pageFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  function go(next: string) {
    window.location.hash = `#/${next}`;
    window.scrollTo(0, 0);
  }

  // The dashboard needs the (demo) login.
  const view: Page = page === "dashboard" && !authed ? "login" : page;

  function signOut() {
    logout();
    setAuthed(false);
    go("home");
  }

  const apiOk = !health.error && health.data?.database === "ok";

  return (
    <div className="site">
      <div className="announce">
        Demo build: sample data only. Sign in with the demo account to explore.{" "}
        <a href="#/how">See how it works</a>
      </div>
      <header className="topbar">
        <a className="brand" href="#/home">
          <span className="logo-mark" />
          LeadQual
        </a>
        <nav>
          <a className={view === "home" ? "active" : ""} href="#/home">Product</a>
          <a className={view === "how" ? "active" : ""} href="#/how">How it works</a>
          <a className={view === "dashboard" ? "active" : ""} href="#/dashboard">Dashboard</a>
        </nav>
        <span className={apiOk ? "status ok" : "status bad"}>
          <i /> API {apiOk ? "online" : "offline"}
        </span>
        {authed ? (
          <button className="btn-outline sm" onClick={signOut}>Sign out</button>
        ) : (
          <a className="btn-primary sm" href="#/login">Sign in</a>
        )}
      </header>

      <main className="container">
        {view === "home" && <Landing go={go} />}
        {view === "how" && <HowItWorks />}
        {view === "login" && (
          <LoginPage
            onSuccess={() => {
              setAuthed(true);
              go("dashboard");
            }}
          />
        )}
        {view === "dashboard" && (
          <>
            <div className="tabs">
              {(["leads", "import", "crm", "jobs"] as Tab[]).map((t) => (
                <button
                  key={t}
                  className={tab === t ? "tab active" : "tab"}
                  onClick={() => {
                    setTab(t);
                    setSelected(null);
                  }}
                >
                  {t}
                </button>
              ))}
            </div>
            {tab === "import" && <ImportPanel onImported={() => setRefreshKey((k) => k + 1)} />}
            {tab === "leads" &&
              (selected === null ? (
                <LeadsTable refreshKey={refreshKey} onSelect={setSelected} />
              ) : (
                <LeadDetailView leadId={selected} onBack={() => setSelected(null)} />
              ))}
            {tab === "crm" && <CrmPanel />}
            {tab === "jobs" && <JobsPanel />}
          </>
        )}
      </main>

      <footer className="footer">
        <div>LeadQual demo. Lead generation and qualification pipeline.</div>
        <div className="muted-light">FastAPI, PostgreSQL, Redis + RQ, React</div>
      </footer>
    </div>
  );
}
