import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useLoad } from "../hooks";
import type { Stats } from "../types";

// Fictional people and companies used by the live demo. example.com is reserved (RFC 2606),
// so these can never be real companies, and HubSpot accepts the addresses. Each run gets fresh email addresses,
// so the pipeline visibly starts from zero every time.
const DEMO_PEOPLE = [
  ["Maya", "Chen", "CTO", "novacore.example.com"],
  ["Arjun", "Mehta", "VP Sales", "helio.example.com"],
  ["Sofia", "Rossi", "Head of Growth", "tidewave.example.com"],
  ["Daniel", "Okafor", "Founder & CEO", "globexa.example.com"],
  ["Emma", "Larsen", "Marketing Manager", "orbitly.example.com"],
  ["Lucas", "Moreau", "Product Manager", "stackwise.example.com"],
  ["Hana", "Sato", "Software Engineer", "nimbus.example.com"],
  ["Noah", "Fischer", "Intern", "quickship.example.com"],
  ["Liam", "Brooks", "Office Assistant", "northwind.example.com"],
];

const STAGES: { key: keyof Stats["pipeline"]; label: string; hint: string }[] = [
  { key: "imported", label: "Imported", hint: "validated and saved" },
  { key: "enriched", label: "Enriched", hint: "company data added" },
  { key: "scored", label: "Scored", hint: "rules give 0-100" },
  { key: "explained", label: "AI explained", hint: "Groq writes why" },
  { key: "pushed", label: "Sent to CRM", hint: "hot leads only" },
];

function demoRows(run: string) {
  return DEMO_PEOPLE.map(([first, last, title, domain]) => ({
    email: `${first.toLowerCase()}.${last.toLowerCase()}${run}@${domain}`,
    company_domain: domain,
    first_name: first,
    last_name: last,
    job_title: title,
  }));
}

export function Overview({ onOpenLead }: { onOpenLead: (id: number) => void }) {
  const totals = useLoad(() => api.stats(), [], 5000);
  const [since, setSince] = useState<string | null>(null);
  const [live, setLive] = useState<Stats | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  useEffect(() => () => {
    if (timer.current) window.clearInterval(timer.current);
  }, []);

  async function runDemo() {
    setError(null);
    setRunning(true);
    setLive(null);
    const start = new Date(Date.now() - 2000).toISOString();
    setSince(start);
    try {
      await api.importJson(demoRows(String(Math.floor(100 + Math.random() * 900))));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setRunning(false);
      return;
    }
    const startedAt = Date.now();
    timer.current = window.setInterval(async () => {
      try {
        const s = await api.stats(start);
        setLive(s);
        const p = s.pipeline;
        const settled =
          p.imported > 0 &&
          p.scored === p.imported &&
          p.pushed >= s.segments.hot &&
          (p.explained === p.scored || Date.now() - startedAt > 25000);
        if (settled || Date.now() - startedAt > 45000) {
          if (timer.current) window.clearInterval(timer.current);
          setRunning(false);
          totals.reload();
        }
      } catch {
        /* keep polling */
      }
    }, 800);
  }

  const view = live ?? totals.data;
  const total = view?.pipeline.imported ?? 0;
  const seg = view?.segments ?? { hot: 0, nurture: 0, disqualified: 0 };
  const segTotal = seg.hot + seg.nurture + seg.disqualified || 1;

  return (
    <section className="overview">
      <div className="overview-head">
        <div>
          <h2>Overview</h2>
          <p className="muted">
            {since ? "Showing the leads from your live demo run." : "All leads in the system."}
          </p>
        </div>
        <button className="btn-primary btn-demo" onClick={() => void runDemo()} disabled={running}>
          {running ? "Running..." : "Run live demo"}
        </button>
      </div>
      {error && <p className="error">{error}</p>}

      <div className={running ? "pipeline running" : "pipeline"}>
        {STAGES.map((stage, i) => {
          const n = view?.pipeline[stage.key] ?? 0;
          const denom = stage.key === "pushed" ? seg.hot || (total ? 1 : 0) : total;
          const pct = denom ? Math.min(100, (n / denom) * 100) : 0;
          const done = denom > 0 && n >= denom;
          return (
            <div className="stage-wrap" key={stage.key}>
              <div className={done ? "stage done" : n > 0 ? "stage active" : "stage"}>
                <div className="stage-num">{n}</div>
                <div className="stage-label">{stage.label}</div>
                <div className="stage-hint">{stage.hint}</div>
                <div className="stage-track">
                  <div className="stage-fill" style={{ width: `${pct}%` }} />
                </div>
              </div>
              {i < STAGES.length - 1 && (
                <div className="connector">
                  <span className="dot" />
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="overview-grid">
        <div className="card">
          <h3>Segments</h3>
          <div className="seg-bar">
            <div className="seg seg-hot" style={{ width: `${(seg.hot / segTotal) * 100}%` }} />
            <div className="seg seg-nurture" style={{ width: `${(seg.nurture / segTotal) * 100}%` }} />
            <div className="seg seg-dq" style={{ width: `${(seg.disqualified / segTotal) * 100}%` }} />
          </div>
          <div className="seg-legend">
            <span><i className="sw seg-hot" /> Hot <strong>{seg.hot}</strong></span>
            <span><i className="sw seg-nurture" /> Nurture <strong>{seg.nurture}</strong></span>
            <span><i className="sw seg-dq" /> Disqualified <strong>{seg.disqualified}</strong></span>
          </div>
          <p className="muted small">
            Hot = score 70+, sent to sales. Nurture = 40-69, for marketing. Below 40 is set aside.
          </p>
        </div>

        <div className="card">
          <h3>Hot leads ready for sales</h3>
          {view && view.hot_leads.length === 0 && (
            <p className="muted">No hot leads yet. Press "Run live demo".</p>
          )}
          <div className="hot-list">
            {view?.hot_leads.map((h) => (
              <button className="hot-card" key={h.lead_id} onClick={() => onOpenLead(h.lead_id)}>
                <div className="hot-score">{h.score}</div>
                <div className="hot-body">
                  <div className="hot-name">
                    {h.name ?? h.email} <span className="muted">· {h.job_title ?? ""}</span>
                  </div>
                  <div className="muted small">{h.company}</div>
                  <div className="hot-reason">
                    {h.reasoning ?? <span className="muted">AI explanation on its way...</span>}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
