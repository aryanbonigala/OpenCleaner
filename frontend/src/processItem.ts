import type { ItemType, ScanItem } from "./api";

/** Process/service/startup/task facts live in `scanner_facts`; pid/path also mirror onto the item. */
export function factValue(it: ScanItem, key: string): unknown {
  if (key === "path") return it.path ?? it.scanner_facts?.[key] ?? null;
  return it.scanner_facts?.[key] ?? null;
}

export function pidOf(it: ScanItem): number | null {
  const raw = factValue(it, "pid");
  const n = typeof raw === "number" ? raw : typeof raw === "string" ? Number(raw) : NaN;
  return Number.isFinite(n) ? n : null;
}

export function unavailableFacts(it: ScanItem): string[] {
  const raw = factValue(it, "unavailable_facts");
  return Array.isArray(raw) ? raw.map(String) : [];
}

export const PROCESS_CATEGORY_LABEL: Record<string, string> = {
  essential: "Essential",
  important: "Important",
  non_essential: "Non-essential",
  gaming_fps_impact: "Gaming / FPS impact",
  unknown: "Unknown",
  not_applicable: "Not applicable",
};

export const PROCESS_ACTION_POLICY_LABEL: Record<string, string> = {
  blocked: "Blocked",
  report_only: "Report-only",
  preview_required: "Preview required",
  explicit_selection_required: "Explicit selection required",
  allowed_with_confirmation: "Preview required",
  unsupported: "Unsupported",
};

export function itemTypeLabel(it: ScanItem): string {
  return (it.item_type as ItemType).replaceAll("_", " ");
}

export function formatMb(mb: number | null | undefined): string {
  if (typeof mb !== "number") return "—";
  if (mb < 1) return `${Math.round(mb * 1000)} KB`;
  return `${mb.toFixed(1)} MB`;
}

export function formatCpu(pct: number | null | undefined): string {
  return typeof pct === "number" ? `${pct.toFixed(1)}%` : "—";
}

export function reasonPreview(it: ScanItem): string {
  const pc = it.process_control;
  return pc.blocked_reason || pc.user_visible_summary || pc.evidence[0] || "No evidence recorded yet.";
}
