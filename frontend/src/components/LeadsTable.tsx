import { useState } from "react";
import { api } from "../api";
import { useLoad } from "../hooks";
import type { Segment } from "../types";
import { SegmentBadge } from "./SegmentBadge";

const PAGE_SIZE = 20;

export function LeadsTable({
  refreshKey,
  onSelect,
}: {
  refreshKey: number;
  onSelect: (id: number) => void;
}) {
  const [segment, setSegment] = useState<Segment | "">("");
  const [offset, setOffset] = useState(0);
  const { data, error, loading, reload } = useLoad(
    () => api.listLeads({ segment: segment || undefined, limit: PAGE_SIZE, offset }),
    [segment, offset, refreshKey],
  );

  const total = data?.total ?? 0;

  return (
    <section>
      <h2>Leads</h2>
      <div className="toolbar">
        <label>
          Segment{" "}
          <select
            value={segment}
            onChange={(e) => {
              setSegment(e.target.value as Segment | "");
              setOffset(0);
            }}
          >
            <option value="">all</option>
            <option value="hot">hot</option>
            <option value="nurture">nurture</option>
            <option value="disqualified">disqualified</option>
          </select>
        </label>
        <button onClick={reload}>Refresh</button>
        <span className="muted">{loading ? "Loading..." : `${total} lead${total === 1 ? "" : "s"}`}</span>
      </div>

      {error && <p className="error">{error}</p>}

      <table>
        <thead>
          <tr>
            <th>Email</th>
            <th>Name</th>
            <th>Title</th>
            <th>Segment</th>
          </tr>
        </thead>
        <tbody>
          {data?.items.map((lead) => (
            <tr key={lead.id} className="clickable" onClick={() => onSelect(lead.id)}>
              <td>{lead.email}</td>
              <td>{[lead.first_name, lead.last_name].filter(Boolean).join(" ") || "-"}</td>
              <td>{lead.job_title ?? "-"}</td>
              <td>
                <SegmentBadge segment={lead.segment} />
              </td>
            </tr>
          ))}
          {data && data.items.length === 0 && (
            <tr>
              <td colSpan={4} className="muted">
                No leads yet. Import some first.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <div className="toolbar">
        <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
          Previous
        </button>
        <button disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>
          Next
        </button>
        <span className="muted">
          {total === 0 ? 0 : offset + 1}-{Math.min(offset + PAGE_SIZE, total)} of {total}
        </span>
      </div>
    </section>
  );
}
