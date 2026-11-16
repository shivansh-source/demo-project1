import { useState } from "react";
import { api } from "../api";
import { useLoad } from "../hooks";
import { SegmentBadge } from "./SegmentBadge";

export function LeadDetailView({ leadId, onBack }: { leadId: number; onBack: () => void }) {
  const lead = useLoad(() => api.getLead(leadId), [leadId]);
  const history = useLoad(() => api.getScores(leadId), [leadId]);
  const [message, setMessage] = useState<string | null>(null);

  async function rescore() {
    try {
      const result = await api.rescore(leadId);
      setMessage(
        result.queued
          ? "Rescore queued. Refresh in a few seconds to see the new score."
          : "A rescore is already queued.",
      );
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e));
    }
  }

  function refresh() {
    lead.reload();
    history.reload();
  }

  if (lead.error) {
    return (
      <section>
        <button onClick={onBack}>Back</button>
        <p className="error">{lead.error}</p>
      </section>
    );
  }
  const d = lead.data;
  if (!d) return <p className="muted">Loading...</p>;
  const score = d.latest_score;

  return (
    <section>
      <div className="toolbar">
        <button onClick={onBack}>Back to leads</button>
        <button onClick={refresh}>Refresh</button>
        <button onClick={() => void rescore()}>Rescore</button>
      </div>
      {message && <p className="muted">{message}</p>}

      <h2>
        {[d.first_name, d.last_name].filter(Boolean).join(" ") || d.email} <SegmentBadge segment={d.segment} />
      </h2>
      <p className="muted">
        {d.email} {d.job_title ? `- ${d.job_title}` : ""}
      </p>

      <div className="grid-2">
        <div className="card">
          <h3>Company</h3>
          <dl>
            <dt>Domain</dt>
            <dd>{d.company.domain}</dd>
            <dt>Name</dt>
            <dd>{d.company.name ?? "-"}</dd>
            <dt>Employees</dt>
            <dd>{d.company.employee_count ?? "-"}</dd>
            <dt>Industry</dt>
            <dd>{d.company.industry ?? "-"}</dd>
            <dt>Country</dt>
            <dd>{d.company.country ?? "-"}</dd>
            <dt>Enrichment</dt>
            <dd>{d.company.enrichment_status}</dd>
          </dl>
        </div>

        <div className="card">
          <h3>Latest score</h3>
          {score ? (
            <>
              <p className="big">
                {score.score}
                <span className="muted"> / 100</span>
              </p>
              <table>
                <thead>
                  <tr>
                    <th>Rule</th>
                    <th>Points</th>
                    <th>Why</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(score.rule_breakdown.rules).map(([rule, entry]) => (
                    <tr key={rule}>
                      <td>{rule}</td>
                      <td>{entry.points}</td>
                      <td>{entry.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {score.rule_breakdown.capped && (
                <p className="muted">Raw total {score.rule_breakdown.raw_total} was capped at 100.</p>
              )}
              <p>
                <strong>Explanation:</strong>{" "}
                {score.reasoning ?? <span className="muted">({reasoningNote(score.reasoning_status)})</span>}
              </p>
              <p className="muted mono">rules {score.rules_version.slice(0, 12)}</p>
            </>
          ) : (
            <p className="muted">Not scored yet. The worker is probably still processing it.</p>
          )}
        </div>
      </div>

      <h3>Score history</h3>
      <table>
        <thead>
          <tr>
            <th>When</th>
            <th>Score</th>
            <th>Rules version</th>
            <th>Explanation</th>
          </tr>
        </thead>
        <tbody>
          {history.data?.map((s) => (
            <tr key={s.id}>
              <td>{new Date(s.created_at).toLocaleString()}</td>
              <td>{s.score}</td>
              <td className="mono">{s.rules_version.slice(0, 12)}</td>
              <td>{s.reasoning ?? reasoningNote(s.reasoning_status)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function reasoningNote(status: string): string {
  switch (status) {
    case "pending":
      return "explanation pending";
    case "failed":
      return "explanation failed";
    case "skipped":
      return "reasoning disabled";
    default:
      return status;
  }
}
