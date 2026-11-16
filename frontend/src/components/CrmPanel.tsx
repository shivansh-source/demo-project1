import { api } from "../api";
import { useLoad } from "../hooks";

export function CrmPanel() {
  const { data, error } = useLoad(() => api.crm(), [], 4000);

  return (
    <section>
      <h2>CRM sync</h2>
      {error && <p className="error">{error}</p>}
      {data && (
        <>
          <div className="card crm-head">
            <div>
              <span className={data.live ? "badge badge-hot" : "badge badge-none"}>
                {data.live ? `Live: ${data.provider}` : "Demo CRM (mock)"}
              </span>
              <p className="muted small">
                {data.live
                  ? "Hot leads are being created or updated as contacts in your CRM."
                  : "Pushes go to an in-memory stand-in. Set CRM_PROVIDER=hubspot and CRM_API_TOKEN to send them to HubSpot."}
              </p>
            </div>
            <div className="crm-stats">
              <div>
                <strong>{data.hot_leads}</strong>
                <span>hot leads</span>
              </div>
              <div>
                <strong>{data.pushed}</strong>
                <span>pushed to CRM</span>
              </div>
            </div>
          </div>

          <table>
            <thead>
              <tr>
                <th>Contact</th>
                <th>Company</th>
                <th>Score</th>
                <th>CRM id</th>
                <th>Status</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              {data.pushes.map((p) => (
                <tr key={p.id}>
                  <td>
                    {p.name ?? p.email}
                    <div className="muted small">{p.email}</div>
                  </td>
                  <td>{p.company ?? "-"}</td>
                  <td>{p.score}</td>
                  <td className="mono">{p.external_id ?? "-"}</td>
                  <td>{p.status}</td>
                  <td>{new Date(p.created_at).toLocaleTimeString()}</td>
                </tr>
              ))}
              {data.pushes.length === 0 && (
                <tr>
                  <td colSpan={6} className="muted">
                    Nothing pushed yet. Import leads: hot ones (score 70+) show up here within seconds.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}
