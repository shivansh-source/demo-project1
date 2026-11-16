export type Segment = "hot" | "nurture" | "disqualified";
export type JobStatus = "queued" | "running" | "done" | "failed";

export interface RowError {
  row_number: number;
  reason: string;
  raw_payload: Record<string, unknown>;
}

export interface Batch {
  id: number;
  source: string;
  filename: string | null;
  created_at: string;
  total_rows: number;
  accepted_rows: number;
  rejected_rows: number;
  errors: RowError[];
}

export interface RuleEntry {
  points: number;
  reason: string;
}

export interface Score {
  id: number;
  lead_id: number;
  score: number;
  rule_breakdown: {
    rules: Record<string, RuleEntry>;
    raw_total: number;
    capped: boolean;
  };
  rules_version: string;
  reasoning: string | null;
  reasoning_status: "ok" | "pending" | "failed" | "skipped";
  created_at: string;
}

export interface Company {
  id: number;
  domain: string;
  name: string | null;
  employee_count: number | null;
  industry: string | null;
  country: string | null;
  enrichment_status: string;
}

export interface LeadSummary {
  id: number;
  email: string;
  first_name: string | null;
  last_name: string | null;
  job_title: string | null;
  segment: Segment | null;
  company_id: number;
}

export interface LeadDetail extends LeadSummary {
  company: Company;
  latest_score: Score | null;
}

export interface LeadList {
  items: LeadSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface Job {
  id: string;
  type: string;
  status: JobStatus;
  attempts: number;
  max_attempts: number;
  last_error: string | null;
  enqueued_at: string | null;
  payload: Record<string, unknown>;
}

export interface Rescore {
  lead_id: number;
  job_id: string | null;
  queued: boolean;
}

export interface CrmPush {
  id: number;
  lead_id: number;
  email: string;
  name: string | null;
  company: string | null;
  score: number;
  status: string;
  external_id: string | null;
  created_at: string;
}

export interface CrmOverview {
  provider: string;
  live: boolean;
  hot_leads: number;
  pushed: number;
  pushes: CrmPush[];
}
