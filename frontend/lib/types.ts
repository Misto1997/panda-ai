// Mirrors backend/app/schemas/{chat,agui}.py and backend/app/rca/models.py. Keep in sync.
export type CacheStatus = "hit" | "miss" | "off";
export type Step = { node: string; step: string; detail: string; ms: number; cache?: CacheStatus; status?: "running" | "skipped" };
export type Table = { columns: string[]; rows: (string | number | null)[][]; formats: Record<string, string>; titles: Record<string, string>; truncated?: boolean };

export type SegmentContribution = {
  segment: Record<string, string>; baseline: number | null; current: number | null; rel: number | null;
  contribution: number; share_of_change: number | null;
};
export type Rca = {
  title: string; format: string; rel: number | null; material: boolean; tree: string | null;
  current: { start: string; end: string; value: number | null }; baseline: { start: string; end: string; value: number | null };
  checks: { id: string; title: string; fired: boolean; detail: string }[];
  decomposition: { component: string; title: string; format: string; baseline: number; current: number; rel: number | null; contribution: number }[];
  drill_metric: string;
  drill: { dims: string[]; total_change: number; cells: SegmentContribution[]; marginals: Record<string, SegmentContribution> };
  hypotheses: { id: string; claim: string; test: string; status: "confirmed" | "rejected" | "inconclusive"; evidence: string }[];
  queries_run: number;
};
export type ResultMeta = {
  route: string; engine?: string; llm?: string; sources?: Record<string, string>; elapsed_ms?: number; cache?: CacheStatus;
  ir_source?: string; period?: string; rows?: number; docs?: string[]; tree?: string; queries?: number; total_ms?: number;
  bytes_processed?: number; path?: string; sql_attempts?: number; narrated?: boolean;
};
export type Result = {
  type: "answer" | "rca" | "info" | "error"; text: string; table?: Table; chart?: Record<string, unknown> | null;
  sql?: string; rca?: Rca; meta: ResultMeta;
};
export type Turn = {
  id: number; question: string; steps: Step[]; text: string; surface?: A2uiMessage[]; result?: Result;
  error?: string; done: boolean;
};
export type ThreadSummary = { id: string; title: string; updated_at: string; turns: number };
export type StoredTurn = { question: string; response: Result; surface?: A2uiMessage[] | null; created_at: string };
export type Me = { email?: string; remaining_today?: number; daily_limit?: number };
export type CacheStats = { plan_hits: number; plan_misses: number; result_hits: number; result_misses: number; plan_entries: number; result_entries: number };
export type Meta = {
  profile: string; app_env: string;
  llm: string; engine: string; search: string; anchor: string; tables: Record<string, number>; suggestions: string[];
  metrics: { id: string; title: string }[]; cache: CacheStats;
};

// ---- AG-UI events (https://docs.ag-ui.com/concepts/events); only the ones PANDA emits ----
type Base = { timestamp?: number };
export type AgUiEvent =
  | (Base & { type: "RUN_STARTED"; threadId: string; runId: string })
  | (Base & { type: "RUN_FINISHED"; threadId: string; runId: string; outcome?: { type: string }; result?: unknown })
  | (Base & { type: "RUN_ERROR"; message: string; code?: string })
  | (Base & { type: "STEP_STARTED" | "STEP_FINISHED"; stepName: string })
  | (Base & { type: "TEXT_MESSAGE_START"; messageId: string; role: string })
  | (Base & { type: "TEXT_MESSAGE_CONTENT"; messageId: string; delta: string })
  | (Base & { type: "TEXT_MESSAGE_END"; messageId: string })
  | (Base & { type: "ACTIVITY_SNAPSHOT"; messageId: string; activityType: string; content: unknown; replace?: boolean })
  | (Base & { type: "CUSTOM"; name: "panda.step"; value: Step })
  | (Base & { type: "CUSTOM"; name: "panda.result"; value: Result })
  | (Base & { type: "CUSTOM"; name: string; value: unknown });

export const A2UI_SURFACE = "a2ui-surface";

// ---- A2UI v0.9 messages (https://github.com/google/A2UI) ----
export type A2uiComponent = { id: string; component: string; [prop: string]: unknown };
export type A2uiMessage = { version?: string } & (
  | { createSurface: { surfaceId: string; catalogId: string; theme?: { variant?: string } } }
  | { updateComponents: { surfaceId: string; components: A2uiComponent[] } }
  | { updateDataModel: { surfaceId: string; path?: string; value?: unknown } }
  | { deleteSurface: { surfaceId: string } }
);
