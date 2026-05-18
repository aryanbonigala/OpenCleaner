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

export interface ScoredItem {
  id: string;
  category: string;
  item_type: ItemType;
  name: string;
  path?: string | null;
  detail: Record<string, unknown>;
  rule_bucket: RiskBucket;
  confidence: number;
  reasoning: string;
  ml_rank_score?: number | null;
  rank_startup_impact?: number | null;
  rank_memory_impact?: number | null;
  rank_cpu_impact?: number | null;
  rank_gpu_impact?: number | null;
  rank_gaming_impact?: number | null;
  rank_deletion_risk?: number | null;
  rank_usefulness?: number | null;
}

export interface ScanSummary {
  scan_id: string;
  platform: string;
  mode: PermissionMode;
  items_count: number;
  buckets: Record<string, number>;
  disk_usage_sample?: Record<string, unknown> | null;
}

export interface ScanResult {
  summary: ScanSummary;
  items: ScoredItem[];
}

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

export const client = {
  health: () => api<{ status: string }>("/health"),
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
  explain: (item: ScoredItem) =>
    api<ExplainResponse>("/api/explain", {
      method: "POST",
      body: JSON.stringify({ item }),
    }),
  cleanup: (item_ids: string[], confirm_medium_risk: boolean, include_recycle_bin: boolean) =>
    api("/api/cleanup/execute", {
      method: "POST",
      body: JSON.stringify({ item_ids, confirm_medium_risk, include_recycle_bin }),
    }),
  quarantineList: () => api<{ entries: unknown[] }>("/api/quarantine"),
  restore: (id: string) =>
    api("/api/quarantine/restore", {
      method: "POST",
      body: JSON.stringify({ id }),
    }),
  perfStart: (preset: string, target_process_names: string[]) =>
    api<{ suspended_pids: number[]; preset: string }>("/api/performance/start", {
      method: "POST",
      body: JSON.stringify({ preset, target_process_names }),
    }),
  perfStop: () =>
    api<{ resumed: number[] }>("/api/performance/stop", {
      method: "POST",
    }),
  feedback: (item: ScoredItem, decision: "keep" | "remove" | "ignore") =>
    api("/api/feedback", {
      method: "POST",
      body: JSON.stringify({ item, decision, weight: 1.0 }),
    }),
  exportReportUrl: (fmt: "json" | "md") => `${API_BASE}/api/export/report?fmt=${encodeURIComponent(fmt)}`,
};
