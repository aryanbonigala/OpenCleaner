const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8742";

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) {
    return (await res.json()) as T;
  }
  return (await res.text()) as unknown as T;
}

export type PermissionMode = "read_only" | "assisted" | "performance";

export type ItemType =
  | "process"
  | "service"
  | "startup_entry"
  | "scheduled_task"
  | "file_or_folder"
  | "browser_profile"
  | "duplicate_group"
  | "orphan_app";

export type RiskBucket =
  | "safe_to_remove"
  | "probably_safe"
  | "ask_user"
  | "unknown"
  | "risky_system_critical";

export interface ProvenanceRecord {
  stage: string;
  decided_by: string;
  evidence: string[];
  matched_rule?: string | null;
  matched_intelligence_entry?: string | null;
  ml_score_source?: string | null;
  confidence?: number | null;
}

export interface ItemMetrics {
  memory_mb?: number | null;
  cpu_percent?: number | null;
  size_mb?: number | null;
  ml_rank_score?: number | null;
  rank_startup_impact?: number | null;
  rank_memory_impact?: number | null;
  rank_cpu_impact?: number | null;
  rank_gpu_impact?: number | null;
  rank_gaming_impact?: number | null;
  rank_deletion_risk?: number | null;
  rank_usefulness?: number | null;
}

export interface IntelligenceSnapshot {
  known?: boolean;
  applicable?: boolean;
  match_kind?: string | null;
  name?: string | null;
  vendor?: string | null;
  category?: string | null;
  plain_english_description?: string | null;
  safe_to_stop?: boolean | null;
  safe_to_disable_startup?: boolean | null;
  safe_to_delete?: boolean | null;
  gaming_impact?: string | null;
  memory_impact?: string | null;
  startup_impact?: string | null;
  risk_level?: string | null;
  confidence?: number | null;
  warning_if_changed?: string | null;
  recommended_action?: string | null;
  rules_protect?: boolean;
}

export type ProcessControlCategory =
  | "essential"
  | "important"
  | "non_essential"
  | "gaming_fps_impact"
  | "unknown"
  | "not_applicable";

export type ActionPolicy =
  | "blocked"
  | "report_only"
  | "preview_required"
  | "explicit_selection_required"
  | "allowed_with_confirmation"
  | "unsupported";

/** Process/task control metadata; populated by the backend classifier stage. */
export interface ProcessControl {
  applicable: boolean;
  category: ProcessControlCategory;
  action_policy: ActionPolicy;
  safe_to_end: boolean;
  safe_to_suspend: boolean;
  safe_to_disable_startup: boolean;
  blocked_reason?: string | null;
  user_visible_summary?: string | null;
  fps_impact?: string | null;
  memory_impact?: string | null;
  cpu_impact?: string | null;
  confidence: number;
  evidence: string[];
}

export interface ExplanationBlock {
  summary: string;
  headline?: string | null;
}

export interface Recommendations {
  primary?: string | null;
  warnings?: string[];
}

/** Canonical scan row (v0.4+). */
export interface ScanItem {
  id: string;
  scan_version: number;
  item_type: ItemType;
  source: string;
  subtype?: string | null;
  display_name: string;
  raw_name: string;
  path?: string | null;
  vendor?: string | null;
  category?: string | null;
  metrics: ItemMetrics;
  intelligence?: IntelligenceSnapshot | null;
  bucket: RiskBucket;
  risk_level: string;
  protected: boolean;
  cleanup_eligible: boolean;
  performance_eligible: boolean;
  explanation: ExplanationBlock;
  recommendations: Recommendations;
  provenance: ProvenanceRecord[];
  timestamps: Record<string, string>;
  scanner_facts: Record<string, unknown>;
  confidence: number;
  process_control: ProcessControl;
}

/** @deprecated Use ScanItem — kept for gradual migration */
export type ScoredItem = ScanItem;

export interface ScanSummary {
  scan_id: string;
  scan_schema_version?: number;
  platform: string;
  mode: PermissionMode;
  items_count: number;
  buckets: Record<string, number>;
  disk_usage_sample?: Record<string, unknown> | null;
  generated_at?: string | null;
  scanner_warnings?: string[];
  started_at?: string | null;
  finished_at?: string | null;
  duration_ms?: number | null;
  status?: "success" | "partial_success" | "failed";
}

export interface CleanupPreviewItem {
  id: string;
  display_name: string;
  path?: string | null;
  bucket: string;
  status: string;
  reason: string;
  why_safe_or_unsafe?: string;
  estimated_bytes?: number;
}

export interface CleanupPreviewResponse {
  preview_id: string;
  scan_id: string;
  estimated_bytes: number;
  estimated_mb: number;
  counts: { selected: number; will_quarantine: number; skipped: number; blocked: number };
  items: CleanupPreviewItem[];
  include_recycle_bin: boolean;
  recycle_bin_note?: string | null;
  confirm_medium_risk: boolean;
  disclaimer: string;
}

export interface CleanupExecuteResult {
  reclaimed_bytes: number;
  reclaimed_mb: number;
  actions: Record<string, unknown>[];
  errors: string[];
  summary?: {
    preview_id: string;
    estimated_bytes: number;
    confirmed_bytes: number;
    estimated_mb: number;
    confirmed_mb: number;
    quarantined: number;
    skipped: number;
    failed: number;
    blocked: number;
  };
}

export interface ScanResult {
  summary: ScanSummary;
  items: ScanItem[];
  api_version?: string;
}

export type CleanupMode = "quarantine_only" | "manual_permanent_delete_only";
export type RiskVisibility = "basic" | "advanced";
export type QuarantineRetention = "7_days" | "14_days" | "30_days" | "manual_only";
export type LoggingMode = "normal" | "redacted_paths" | "minimal";

export interface ScannerToggles {
  files: boolean;
  browser: boolean;
  startup: boolean;
  tasks: boolean;
  performance: boolean;
}

export interface UserSettings {
  settings_version: number;
  cleanup_mode: CleanupMode;
  risk_visibility: RiskVisibility;
  scanner_toggles: ScannerToggles;
  quarantine_retention: QuarantineRetention;
  logging_mode: LoggingMode;
}

export type UserSettingsPatch = Partial<
  Omit<UserSettings, "scanner_toggles" | "settings_version">
> & {
  scanner_toggles?: Partial<ScannerToggles>;
};

export interface ExplainResponse {
  what_it_does: string;
  importance: string;
  installer_guess: string;
  gaming_impact: string;
  startup_impact: string;
  safe_to_disable_or_remove: string;
  what_could_break: string;
  local_ml_note: string;
}

/** Read-only process-control inventory from the latest scan. `message` is set when none exists. */
export interface ProcessInventoryResponse {
  scan_id?: string | null;
  generated_at?: string | null;
  platform?: string | null;
  items_count: number;
  counts: Record<string, number>;
  items: ScanItem[];
  warnings: string[];
  message?: string | null;
}

/** GET /api/processes/{pid} — latest-scan lookup, no live OS inspection. */
export interface ProcessDetailResponse {
  item: ScanItem;
  process_control: ProcessControl;
  explanation: ExplanationBlock;
  safety_summary: string;
  blocked_reason?: string | null;
  scanner_facts: Record<string, unknown>;
}

export interface ProcessPreviewEndRequest {
  item_ids: string[];
  confirm_explicit_selection?: boolean;
}

export type ProcessPreviewStatus = "would_allow" | "blocked" | "skipped";
export type ProcessPreviewRecommendedAction =
  | "suspend_preview_only"
  | "end_preview_only"
  | "report_only"
  | "blocked";

export interface ProcessPreviewEndItem {
  id: string;
  display_name: string;
  pid?: number | null;
  status: ProcessPreviewStatus;
  recommended_action: ProcessPreviewRecommendedAction;
  reason: string;
  process_control?: ProcessControl | null;
}

export interface ProcessPreviewEndResponse {
  preview_id?: string | null;
  counts: Record<string, number>;
  items: ProcessPreviewEndItem[];
  disclaimer: string;
}

export interface ChatCommandPreviewRequest {
  message: string;
  confirm_explicit_selection?: boolean;
}

export type ChatCommandPreviewItemStatus = "would_allow" | "blocked" | "informational";

export interface ChatCommandPreviewItem {
  id: string;
  display_name: string;
  pid?: number | null;
  item_type: ItemType;
  category: ProcessControlCategory;
  action_policy: ActionPolicy;
  status: ChatCommandPreviewItemStatus;
  reason: string;
  fps_impact?: string | null;
  user_visible_summary?: string | null;
  blocked_reason?: string | null;
}

export type ChatCommandPreviewActionKind =
  | "run_scan"
  | "review_preview"
  | "confirm_explicit_selection"
  | "open_process_detail"
  | "none";

export interface ChatCommandPreviewAction {
  kind: ChatCommandPreviewActionKind;
  label: string;
  endpoint?: string | null;
  item_ids: string[];
}

export type ChatCommandPreviewIntent =
  | "gaming_safety_preview"
  | "safe_suspend_preview"
  | "explain_process"
  | "unknown_inventory"
  | "protected_inventory"
  | "help";

export interface ChatCommandPreviewResponse {
  intent: ChatCommandPreviewIntent;
  message: string;
  summary: string;
  items: ChatCommandPreviewItem[];
  blocked: ChatCommandPreviewItem[];
  preview?: ProcessPreviewEndResponse | null;
  detail?: Record<string, unknown> | null;
  actions: ChatCommandPreviewAction[];
  warnings: string[];
  disclaimer: string;
}

export function parseApiError(err: unknown): string {
  const raw = err instanceof Error ? err.message : String(err);
  try {
    const parsed = JSON.parse(raw) as { detail?: string };
    if (parsed.detail) return parsed.detail;
  } catch {
    /* plain text */
  }
  return raw || "Request failed";
}

export const client = {
  health: () =>
    api<{ status: string; version: string; api_version: string; scan_in_progress: string }>("/health"),
  scanStatus: () => api<{ scan_in_progress: boolean }>("/api/scan/status"),
  getSettings: () => api<UserSettings>("/api/settings"),
  saveSettings: (patch: UserSettingsPatch) =>
    api<UserSettings>("/api/settings", {
      method: "PUT",
      body: JSON.stringify(patch),
    }),
  resetSettings: () =>
    api<UserSettings>("/api/settings/reset", {
      method: "POST",
    }),
  getMode: () => api<{ mode: PermissionMode }>("/api/mode"),
  setMode: (mode: PermissionMode) =>
    api<{ mode: PermissionMode }>("/api/mode", {
      method: "POST",
      body: JSON.stringify({ mode }),
    }),
  scan: () =>
    api<ScanResult>("/api/scan", {
      method: "POST",
    }),
  latest: () => api<ScanResult | null>("/api/scan/latest"),
  metrics: () =>
    api<{ cpu_percent: number; memory: { total_gb: number; used_gb: number; percent: number } }>(
      "/api/metrics"
    ),
  explain: (item: ScanItem) =>
    api<ExplainResponse>("/api/explain", {
      method: "POST",
      body: JSON.stringify({ item }),
    }),
  cleanupPreview: (
    item_ids: string[],
    confirm_medium_risk: boolean,
    include_recycle_bin: boolean
  ) =>
    api<CleanupPreviewResponse>("/api/cleanup/preview", {
      method: "POST",
      body: JSON.stringify({ item_ids, confirm_medium_risk, include_recycle_bin }),
    }),
  cleanupExecute: (body: {
    preview_id: string;
    item_ids: string[];
    confirm_medium_risk: boolean;
    include_recycle_bin: boolean;
    confirm_permanent_delete: boolean;
  }) =>
    api<CleanupExecuteResult>("/api/cleanup/execute", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  quarantineList: () => api<{ entries: unknown[] }>("/api/quarantine"),
  restore: (id: string) =>
    api("/api/quarantine/restore", {
      method: "POST",
      body: JSON.stringify({ id }),
    }),
  perfPreview: (preset: string, target_process_names: string[]) =>
    api<Record<string, unknown>>("/api/performance/preview", {
      method: "POST",
      body: JSON.stringify({ preset, target_process_names }),
    }),
  perfStart: (preset: string, target_process_names: string[], confirm_apply: boolean) =>
    api<{ suspended_pids: number[]; preset: string }>("/api/performance/start", {
      method: "POST",
      body: JSON.stringify({ preset, target_process_names, confirm_apply }),
    }),
  perfStop: () =>
    api<{ resumed: number[] }>("/api/performance/stop", {
      method: "POST",
    }),
  feedback: (item: ScanItem, decision: "keep" | "remove" | "ignore") =>
    api("/api/feedback", {
      method: "POST",
      body: JSON.stringify({ item, decision, weight: 1.0 }),
    }),
  getProcesses: () => api<ProcessInventoryResponse>("/api/processes"),
  getProcessByPid: (pid: number) => api<ProcessDetailResponse>(`/api/processes/${pid}`),
  previewEndProcesses: (item_ids: string[], confirm_explicit_selection = false) =>
    api<ProcessPreviewEndResponse>("/api/processes/preview-end", {
      method: "POST",
      body: JSON.stringify({ item_ids, confirm_explicit_selection }),
    }),
  safetySummary: () =>
    api<{
      permission_mode: string;
      quarantine: Record<string, unknown>;
      performance_session: Record<string, unknown> | null;
      protected_registry_rules: number;
      running_processes_matching_protection: number;
      recent_actions: unknown[];
      telemetry: string;
    }>("/api/safety/summary"),
  exportReportUrl: (fmt: "json" | "md") => `${API_BASE}/api/export/report?fmt=${encodeURIComponent(fmt)}`,
  previewChatCommand: (message: string, confirm_explicit_selection = false) =>
    api<ChatCommandPreviewResponse>("/api/chat/command-preview", {
      method: "POST",
      body: JSON.stringify({ message, confirm_explicit_selection }),
    }),
};
