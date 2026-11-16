import { isLoggedIn } from "../auth";

const FEATURES = [
  ["Import anything", "Upload a CSV or post JSON. Bad rows are kept with a reason, never dropped."],
  ["Transparent scoring", "Weighted rules in one YAML file. Every score stores a per-rule breakdown and a version hash."],
  ["AI explains, never scores", "An AI model (Groq) writes a two-sentence explanation. It cannot change the number."],
  ["Reliable background work", "Redis + RQ jobs with retries, backoff and crash recovery."],
  ["Push to your CRM", "Only hot leads go out, exactly once per score. HubSpot or a mock CRM."],
  ["Auditable history", "Every scoring run is a new row, so you can see why a lead moved."],
];

export function Landing({ go }: { go: (page: string) => void }) {
  return (
    <>
      <section className="hero">
        <span className="pill">Lead generation and qualification</span>
        <h1>
          Find the leads worth <span className="accent">your time</span>
        </h1>
        <p className="lead">
          Import leads, enrich them with company data, score them with rules you can read, and send
          the hot ones to your CRM. Automatically.
        </p>
        <div className="cta-row">
          <button className="btn-primary" onClick={() => go(isLoggedIn() ? "dashboard" : "login")}>
            {isLoggedIn() ? "Open dashboard" : "Try the demo"}
          </button>
          <button className="btn-outline" onClick={() => go("how")}>
            See how it works
          </button>
        </div>
        <div className="hero-stats">
          <div>
            <strong>0 to 100</strong>
            <span>rule-based score</span>
          </div>
          <div>
            <strong>3</strong>
            <span>segments: hot, nurture, out</span>
          </div>
          <div>
            <strong>1x</strong>
            <span>CRM push per score</span>
          </div>
        </div>
      </section>

      <section className="section">
        <h2 className="section-title">Everything between a spreadsheet and your CRM</h2>
        <div className="feature-grid">
          {FEATURES.map(([title, text]) => (
            <div className="card feature" key={title}>
              <h3>{title}</h3>
              <p className="muted">{text}</p>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
