/**
 * Public JSON contracts from apps/api/app/schemas/discovery.py.
 * UUIDs and timezone-aware ISO datetimes serialize as strings. These types do
 * not validate URLs, UUIDs, datetime ordering or source evidence at runtime.
 */
export type UUID = string;
export type ISODateTime = string;

export type RunStatus = "queued" | "running" | "completed" | "partial" | "failed";
export type ErrorCode =
  | "source_unavailable"
  | "timeout"
  | "invalid_evidence"
  | "internal_error"
  | "insufficient_context"
  | "analysis_warning";

export type DiscoveryCreate = {
  /** Canonical public https://github.com/owner/repo URL; server strips trailing slash. */
  repo_url: string;
};

type ItemRead = {
  /** Entity ID shared by list and map; distinct from the imported item ID. */
  id: UUID;
  origin_item_id: UUID;
  label: string;
  external_id: string;
  original_url: string | null;
};

export type ProjectRead = ItemRead & { entity_type: "project" };
export type ArticleRead = ItemRead & { entity_type: "article" };

export type TopicRead = {
  /** OpenAlex topic identifier, not a graph entity UUID. */
  id: string;
  namespace: "openalex";
  label: string;
  score: number | null;
};

export type EvidenceRead = {
  id: UUID;
  origin_item_id: UUID;
  side: "repo" | "article";
  reference_url: string;
  locator: string;
  excerpt: string;
  /** Source snapshot hash (sha256:HASH). */
  capture_version: string;
  captured_at: ISODateTime;
};

export type SuggestionRead = {
  /** Relationship ID shared by list, map edge and feedback. */
  id: UUID;
  relationship_type: "project_article";
  /** Persisted review state, returned again when reading after feedback. */
  status: "pending" | "confirmed" | "rejected";
  project_id: UUID;
  article: ArticleRead;
  justification: string;
  score: number | null;
  topics: TopicRead[];
  evidences: EvidenceRead[];
  created_at: ISODateTime;
  updated_at: ISODateTime;
};

type RunReadFields = {
  id: UUID;
  repo_url: string;
  created_at: ISODateTime;
  /** Server-calculated deadline; must follow created_at. */
  deadline_at: ISODateTime;
  /** Safe warning codes; empty for a clean analysis. */
  warnings: string[];
};

/** Mirrors RunRead.coherent_state; failed runs may fail before starting. */
export type RunRead = RunReadFields & (
  | {
      status: "queued";
      project: ProjectRead | null;
      started_at: null;
      finished_at: null;
      error_code: null;
    }
  | {
      status: "running";
      project: ProjectRead | null;
      started_at: ISODateTime;
      finished_at: null;
      error_code: null;
    }
  | {
      status: "completed";
      project: ProjectRead;
      started_at: ISODateTime;
      finished_at: ISODateTime;
      error_code: null;
    }
  | {
      status: "partial";
      project: ProjectRead;
      started_at: ISODateTime;
      finished_at: ISODateTime;
      error_code: ErrorCode;
    }
  | {
      status: "failed";
      project: ProjectRead | null;
      started_at: ISODateTime | null;
      finished_at: ISODateTime;
      error_code: ErrorCode;
    }
);

/** Strict integer range enforced by DiscoveryQuery and DiscoveryPage. */
export type DiscoveryLimit =
  | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10
  | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20
  | 21 | 22 | 23 | 24 | 25 | 26 | 27 | 28 | 29 | 30
  | 31 | 32 | 33 | 34 | 35 | 36 | 37 | 38 | 39 | 40
  | 41 | 42 | 43 | 44 | 45 | 46 | 47 | 48 | 49 | 50;

export type DiscoveryQuery = {
  /** Omission uses the server default of 20; null is not accepted. */
  limit?: DiscoveryLimit;
  /** Omission or null starts the first page. */
  cursor?: UUID | null;
};

export type DiscoveryPage = {
  run: RunRead;
  suggestions: SuggestionRead[];
  /** Nonnegative total across pages, not just suggestions.length. */
  total_suggestions: number;
  limit: DiscoveryLimit;
  next_cursor: UUID | null;
};

export type FeedbackUpdate = {
  status: "confirmed" | "rejected";
};

export type FeedbackRead = {
  /** Relationship ID shared by suggestion, map edge and feedback. */
  id: UUID;
  status: "confirmed" | "rejected";
  updated_at: ISODateTime;
};

/** Public JSON contracts from apps/api/app/schemas/monitoring.py. */
export type MonitorUpdate = {
  enabled: boolean;
  /** Strict integer 60..86400 seconds; server default 300. */
  interval_seconds?: number;
  /** Server default false. */
  reanalyze_on_change?: boolean;
};

export type MonitorRead = {
  id: UUID;
  repo_url: string;
  source_item_id: UUID | null;
  enabled: boolean;
  interval_seconds: number;
  reanalyze_on_change: boolean;
  latest_run_id: UUID;
  last_checked_at: ISODateTime | null;
  last_changed_at: ISODateTime | null;
  next_check_at: ISODateTime | null;
  error_code: string | null;
  /** Context has changed relative to the monitor's latest run. */
  stale: boolean;
};

export type ChangeRead = {
  id: UUID;
  monitor_id: UUID;
  repo_url: string;
  kind: "source_changed";
  observed_at: ISODateTime;
  previous_hash: string;
  current_hash: string;
  read_at: ISODateTime | null;
  latest_run_id: UUID | null;
};

export type ChangePage = {
  items: ChangeRead[];
  limit: DiscoveryLimit;
  next_cursor: UUID | null;
};

export type ApiErrorDetail = {
  code: string;
  message: string;
  retryable: boolean;
};

export type ApiError = {
  error: ApiErrorDetail;
};
