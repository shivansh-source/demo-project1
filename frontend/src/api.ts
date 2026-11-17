import type { Batch, CrmOverview, Stats, Job, JobStatus, LeadDetail, LeadList, Rescore, Score, Segment } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, init);
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (body.detail) message = JSON.stringify(body.detail);
    } catch {
      /* keep the status line */
    }
    throw new Error(message);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<{ status: string; database: string }>("/health"),

  importCsv(file: File): Promise<Batch> {
    const form = new FormData();
    form.append("file", file);
    return request<Batch>("/imports/csv", { method: "POST", body: form });
  },

  importJson(rows: unknown[]): Promise<Batch> {
    return request<Batch>("/imports/api", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(rows),
    });
  },

  listLeads(params: { segment?: Segment; limit: number; offset: number }): Promise<LeadList> {
    const query = new URLSearchParams({ limit: String(params.limit), offset: String(params.offset) });
    if (params.segment) query.set("segment", params.segment);
    return request<LeadList>(`/leads?${query}`);
  },

  crm: () => request<CrmOverview>("/crm"),
  stats: (since?: string) =>
    request<Stats>(since ? `/stats?since=${encodeURIComponent(since)}` : "/stats"),
  getLead: (id: number) => request<LeadDetail>(`/leads/${id}`),
  getScores: (id: number) => request<Score[]>(`/leads/${id}/scores`),
  rescore: (id: number) => request<Rescore>(`/leads/${id}/rescore`, { method: "POST" }),

  listJobs(status?: JobStatus): Promise<Job[]> {
    const query = status ? `?status=${status}` : "";
    return request<Job[]>(`/jobs${query}`);
  },
};
