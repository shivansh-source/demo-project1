import { useState } from "react";
import { api } from "../api";
import type { Batch } from "../types";

const SAMPLE = `[
  {"email": "jane@acme.com", "company_domain": "acme.com", "job_title": "VP Sales"}
]`;

export function ImportPanel({ onImported }: { onImported: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [json, setJson] = useState(SAMPLE);
  const [batch, setBatch] = useState<Batch | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<Batch>) {
    setBusy(true);
    setError(null);
    try {
      setBatch(await action());
      onImported();
    } catch (e) {
      setBatch(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function submitJson() {
    let rows: unknown;
    try {
      rows = JSON.parse(json);
    } catch {
      setError("The JSON is not valid.");
      return;
    }
    if (!Array.isArray(rows)) {
      setError("The JSON must be an array of objects.");
      return;
    }
    void run(() => api.importJson(rows as unknown[]));
  }

  return (
    <section>
      <h2>Import leads</h2>
      <div className="grid-2">
        <div className="card">
          <h3>CSV file</h3>
          <p className="muted">Required columns: email, company_domain.</p>
          <input type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <div className="actions">
            <button disabled={!file || busy} onClick={() => file && void run(() => api.importCsv(file))}>
              Upload CSV
            </button>
          </div>
        </div>
        <div className="card">
          <h3>JSON array</h3>
          <textarea rows={6} value={json} onChange={(e) => setJson(e.target.value)} spellCheck={false} />
          <div className="actions">
            <button disabled={busy} onClick={submitJson}>
              Import JSON
            </button>
          </div>
        </div>
      </div>

      {error && <p className="error">{error}</p>}

      {batch && (
        <div className="card">
          <h3>Batch #{batch.id} ({batch.source})</h3>
          <p>
            {batch.total_rows} rows: <strong>{batch.accepted_rows} accepted</strong>,{" "}
            <strong>{batch.rejected_rows} rejected</strong>. The worker now enriches and scores them in the
            background; open Leads and refresh in a few seconds.
          </p>
          {batch.errors.length > 0 && (
            <table>
              <thead>
                <tr>
                  <th>Row</th>
                  <th>Reason</th>
                  <th>Raw data</th>
                </tr>
              </thead>
              <tbody>
                {batch.errors.map((err) => (
                  <tr key={err.row_number}>
                    <td>{err.row_number}</td>
                    <td>{err.reason}</td>
                    <td className="mono">{JSON.stringify(err.raw_payload)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </section>
  );
}
