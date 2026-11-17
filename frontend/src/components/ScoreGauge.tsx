/** Circular 0-100 score gauge. Colour follows the segment thresholds (70 hot, 40 nurture). */
export function ScoreGauge({ score, size = 140 }: { score: number; size?: number }) {
  const r = 52;
  const c = 2 * Math.PI * r;
  const filled = (Math.max(0, Math.min(score, 100)) / 100) * c;
  const tone = score >= 70 ? "var(--hot)" : score >= 40 ? "var(--blue-600)" : "var(--dq)";
  return (
    <svg width={size} height={size} viewBox="0 0 120 120" role="img" aria-label={`Score ${score} of 100`}>
      <circle cx="60" cy="60" r={r} fill="none" stroke="var(--border)" strokeWidth="10" />
      <circle
        cx="60"
        cy="60"
        r={r}
        fill="none"
        stroke={tone}
        strokeWidth="10"
        strokeLinecap="round"
        strokeDasharray={`${filled} ${c}`}
        transform="rotate(-90 60 60)"
        className="gauge-arc"
      />
      <text x="60" y="64" textAnchor="middle" className="gauge-num" fill={tone}>
        {score}
      </text>
      <text x="60" y="84" textAnchor="middle" className="gauge-label">
        out of 100
      </text>
    </svg>
  );
}

const RULE_LABELS: Record<string, string> = {
  seniority: "Seniority",
  company_size: "Company size",
  industry_fit: "Industry fit",
  engagement: "Engagement",
};

/** Horizontal bars showing how many points each rule contributed (max 40 per rule). */
export function BreakdownBars({ rules }: { rules: Record<string, { points: number; reason: string }> }) {
  const entries = Object.entries(rules).sort((a, b) => b[1].points - a[1].points);
  return (
    <div className="bars">
      {entries.map(([rule, entry]) => (
        <div className="bar-row" key={rule}>
          <div className="bar-head">
            <span>{RULE_LABELS[rule] ?? rule}</span>
            <strong>+{entry.points}</strong>
          </div>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${Math.min(100, (entry.points / 40) * 100)}%` }} />
          </div>
          <div className="muted small">{entry.reason}</div>
        </div>
      ))}
    </div>
  );
}
