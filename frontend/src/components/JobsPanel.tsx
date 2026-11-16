import { useState } from "react";
import { api } from "../api";
import { useLoad } from "../hooks";
import type { JobStatus } from "../types";

export function JobsPanel() {
  const [status, setStatus] = useState<JobStatus | "">("failed");
  const { data, error, loading, reload } = useLoad(() => api.listJobs(status || undefined), [status]);

  return (
    <section>
      <h2>Jobs</h2>
      <div className="toolbar">
        <label>
          Status{" "}
          <select value={status} onChange={(e) => setStatus(e.target.value as JobStatus | "")}>
            <option value="">all</option>
            <option value="queued">queued</option>
            <option value="running">running</option>
            <option value="done">done</option>
            <option value="failed">failed</option>
          </select>
        </label>
        <button onClick={reload}>Refresh</button>
        {loading && <span className="muted">Loading...</span>}
      </div>
      {error && <p className="error">{error}</p>}
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Type</th>
            <th>Status</th>
            <th>Attempts</th>
            <th>Last error</th>
          </tr>
        </thead>
        <tbody>
          {data?.map((job) => (
            <tr key={job.id}>
              <td>{job.id}</td>
              <td>{job.type}</td>
              <td>{job.status}</td>
              <td>
                {job.attempts}/{job.max_attempts}
              </td>
              <td className="mono">{job.last_error ?? ""}</td>
            </tr>
          ))}
          {data && data.length === 0 && (
            <tr>
              <td colSpan={5} className="muted">
                No jobs with this status.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </section>
  );
}
