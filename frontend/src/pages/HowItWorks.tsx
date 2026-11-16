const STEPS = [
  ["Import", "A CSV or JSON array arrives. Each row is validated and normalized (lowercase email, domain without www). Bad rows are stored with a reason."],
  ["Save and queue", "Leads and companies are upserted in Postgres, so re-importing never duplicates. After the save commits, jobs are sent to the Redis queue."],
  ["Enrich", "A worker looks up company size, industry and country through a provider interface. A deterministic mock is built in."],
  ["Score", "Rules from scoring.yaml add up to 0-100. The per-rule breakdown and a hash of the rules are stored. A new row per run keeps the history."],
  ["Segment", "70 or more is hot, 40 or more is nurture, the rest are disqualified."],
  ["Explain and push", "An AI model (Groq) writes a short explanation of the breakdown (it never changes the score). Hot leads are pushed to the CRM once per score."],
];

function Arrow({ d, dashed = false, both = false }: { d: string; dashed?: boolean; both?: boolean }) {
  return (
    <path
      d={d}
      className={dashed ? "dg-line dg-dashed" : "dg-line"}
      markerEnd="url(#arrow)"
      markerStart={both ? "url(#arrow)" : undefined}
      fill="none"
    />
  );
}

function Box({
  x, y, w, h, title, sub, kind = "default",
}: { x: number; y: number; w: number; h: number; title: string; sub?: string; kind?: string }) {
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={10} className={`dg-box dg-${kind}`} />
      <text x={x + w / 2} y={y + (sub ? h / 2 - 4 : h / 2 + 5)} textAnchor="middle" className="dg-title">
        {title}
      </text>
      {sub && (
        <text x={x + w / 2} y={y + h / 2 + 15} textAnchor="middle" className="dg-sub">
          {sub}
        </text>
      )}
    </g>
  );
}

export function HowItWorks() {
  return (
    <div className="section">
      <h1 className="page-title">How it works</h1>
      <p className="muted lead-sm">
        A lead goes in as a row in a file and comes out as a scored, explained and (if hot) CRM-synced
        contact. The web app and the worker never talk directly: they share Postgres for data and Redis
        for work.
      </p>

      <div className="card diagram">
        <svg viewBox="0 0 960 500" role="img" aria-label="Architecture diagram of the lead pipeline">
          <defs>
            <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0 0 L10 5 L0 10 z" className="dg-arrowhead" />
            </marker>
          </defs>

          <Box x={20} y={40} w={130} h={46} title="CSV upload" kind="source" />
          <Box x={20} y={112} w={130} h={46} title="JSON API" kind="source" />
          <Box x={210} y={60} w={170} h={76} title="Import and validate" sub="FastAPI" />
          <Box x={210} y={196} w={170} h={76} title="PostgreSQL" sub="leads, companies, scores" kind="store" />
          <Box x={500} y={60} w={170} h={76} title="Redis + RQ queue" sub="retries and backoff" kind="store" />
          <Box x={730} y={60} w={170} h={76} title="Web app" sub="leads, scores, jobs" kind="source" />

          <rect x={40} y={316} width={880} height={160} rx={14} className="dg-group" />
          <text x={60} y={340} className="dg-group-label">Worker (RQ)</text>

          <Box x={64} y={366} w={170} h={64} title="1. Enrich" sub="company data" kind="step" />
          <Box x={274} y={366} w={170} h={64} title="2. Score" sub="rules in scoring.yaml" kind="step" />
          <Box x={484} y={366} w={170} h={64} title="3. Segment" sub="hot / nurture / out" kind="step" />
          <Box x={704} y={338} w={196} h={56} title="4a. Explain" sub="Groq AI, optional" kind="ai" />
          <Box x={704} y={404} w={196} h={56} title="4b. Push to CRM" sub="hot only, once per score" kind="crm" />

          <Arrow d="M150 63 L210 92" />
          <Arrow d="M150 135 L210 106" />
          <Arrow d="M295 136 L295 196" />
          <Arrow d="M380 98 L500 98" />
          <text x={440} y={88} textAnchor="middle" className="dg-note">jobs, after commit</text>
          <Arrow d="M585 136 L585 316" />
          <text x={597} y={236} className="dg-note">worker pulls jobs</text>
          <Arrow d="M234 398 L274 398" />
          <Arrow d="M444 398 L484 398" />
          <Arrow d="M654 398 L680 398 L680 366 L704 366" />
          <Arrow d="M654 398 L680 398 L680 432 L704 432" />
          <Arrow d="M340 272 L340 316" dashed both />
          <text x={352} y={300} className="dg-note">read and write rows</text>
          <Arrow d="M730 98 L670 98" dashed />
          <Arrow d="M800 136 L800 160 L330 160 L330 196" dashed />
        </svg>
        <div className="legend">
          <span><i className="sw sw-step" /> pipeline step</span>
          <span><i className="sw sw-store" /> storage</span>
          <span><i className="sw sw-ai" /> AI (explains only)</span>
          <span><i className="sw sw-crm" /> external CRM</span>
          <span>dashed = read or write</span>
        </div>
      </div>

      <h2 className="section-title left">Step by step</h2>
      <ol className="steps">
        {STEPS.map(([title, text], i) => (
          <li className="card" key={title}>
            <span className="step-no">{i + 1}</span>
            <div>
              <h3>{title}</h3>
              <p className="muted">{text}</p>
            </div>
          </li>
        ))}
      </ol>

      <h2 className="section-title left">Two rules the design holds to</h2>
      <div className="feature-grid two">
        <div className="card feature">
          <h3>The model never scores</h3>
          <p className="muted">
            Scores come only from the rules file. The AI model sees the finished breakdown and
            writes a sentence about it, and if it fails the score is untouched.
          </p>
        </div>
        <div className="card feature">
          <h3>Nothing is silently lost or repeated</h3>
          <p className="muted">
            Rejected rows are recorded, re-imports do not duplicate, failed jobs retry with backoff,
            and a CRM push is guarded by an idempotency key.
          </p>
        </div>
      </div>
    </div>
  );
}
