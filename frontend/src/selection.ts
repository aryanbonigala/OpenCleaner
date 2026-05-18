import type { ScanItem } from "./api";
import { getIntel, itemBucket, knownLabel } from "./scanItem";

export type SelectBlockReason =
  | "not_file"
  | "protected"
  | "critical"
  | "unknown"
  | "ask_user"
  | "not_cleanup_eligible";

export function isCleanupFile(it: ScanItem): boolean {
  return it.item_type === "file_or_folder";
}

export function canSelectForCleanup(it: ScanItem, advancedMode: boolean): boolean {
  if (!isCleanupFile(it)) return false;
  if (it.protected) return false;
  const bucket = itemBucket(it);
  if (bucket === "risky_system_critical") return false;
  if (bucket === "unknown" && !advancedMode) return false;
  if (bucket === "ask_user" && !advancedMode) return false;
  if (!it.cleanup_eligible && !advancedMode) return false;
  return true;
}

export function selectBlockReason(it: ScanItem, advancedMode: boolean): SelectBlockReason | null {
  if (!isCleanupFile(it)) return "not_file";
  if (it.protected) return "protected";
  if (itemBucket(it) === "risky_system_critical") return "critical";
  if (itemBucket(it) === "unknown" && !advancedMode) return "unknown";
  if (itemBucket(it) === "ask_user" && !advancedMode) return "ask_user";
  if (!it.cleanup_eligible && !advancedMode) return "not_cleanup_eligible";
  return null;
}

export function defaultSelectedIds(items: ScanItem[], advancedMode: boolean): Set<string> {
  const ids = new Set<string>();
  for (const it of items) {
    if (!canSelectForCleanup(it, advancedMode)) continue;
    if (itemBucket(it) === "safe_to_remove") ids.add(it.id);
  }
  return ids;
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(2)} MB`;
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export function knownBadge(it: ScanItem): string {
  const k = knownLabel(it);
  if (k === "known") return "Known item";
  if (k === "unknown") return "Unknown item";
  return "Not in intelligence DB";
}

export function safetySummary(it: ScanItem): string {
  const intel = getIntel(it);
  if (it.protected || itemBucket(it) === "risky_system_critical") {
    return "Protected — do not remove or disable without expert guidance.";
  }
  if (intel.plain_english_description) return intel.plain_english_description;
  if (intel.recommended_action) return intel.recommended_action;
  return it.explanation?.summary || "Review this item before making changes.";
}
