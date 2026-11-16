import { useState } from "react";
import { api } from "./api";
import { ImportPanel } from "./components/ImportPanel";
import { JobsPanel } from "./components/JobsPanel";
import { LeadDetailView } from "./components/LeadDetail";
import { LeadsTable } from "./components/LeadsTable";
import { useLoad } from "./hooks";

type Tab = "leads" | "import" | "jobs";

export default function App() {
  const [tab, setTab] = useState<Tab>("leads");
  const [selected, setSelected] = useState<number | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const health = useLoad(() => api.health(), []);

  function go(next: Tab) {
    setTab(next);
    setSelected(null);
  }

  return (
    <div className="app">
      <header>
        <h1>Lead Qualification</h1>
        <nav>
          {(["leads", "import", "jobs"] as Tab[]).map((t) => (
            <button key={t} className={tab === t ? "active" : ""} onClick={() => go(t)}>
              {t}
            </button>
          ))}
        </nav>
        <span className={health.error || health.data?.database !== "ok" ? "status bad" : "status ok"}>
          API {health.error ? "unreachable" : (health.data?.status ?? "...")}
        </span>
      </header>

      <main>
        {tab === "import" && <ImportPanel onImported={() => setRefreshKey((k) => k + 1)} />}
        {tab === "leads" &&
          (selected === null ? (
            <LeadsTable refreshKey={refreshKey} onSelect={setSelected} />
          ) : (
            <LeadDetailView leadId={selected} onBack={() => setSelected(null)} />
          ))}
        {tab === "jobs" && <JobsPanel />}
      </main>
    </div>
  );
}
