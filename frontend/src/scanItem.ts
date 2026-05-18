import type { ItemType, RiskBucket, ScanItem } from "./api";

/** Canonical intelligence block on ScanItem. */
export type IntelligenceSnapshot = NonNullable<ScanItem["intelligence"]>;

export function itemBucket(it: ScanItem): RiskBucket {
  return it.bucket ?? (it as { rule_bucket?: RiskBucket }).rule_bucket ?? "unknown";
}

export function itemName(it: ScanItem): string {
  return it.display_name ?? (it as { name?: string }).name ?? it.raw_name ?? "";
}

export function itemReasoning(it: ScanItem): string {
  return it.explanation?.summary ?? (it as { reasoning?: string }).reasoning ?? "";
}

export function getIntel(it: ScanItem): IntelligenceSnapshot | Record<string, never> {
  if (it.intelligence && typeof it.intelligence === "object") {
    return it.intelligence;
  }
  const legacy = (it as { detail?: { intelligence?: unknown } }).detail?.intelligence;
  if (legacy && typeof legacy === "object") {
    return legacy as IntelligenceSnapshot;
  }
  return {};
}

export function knownLabel(it: ScanItem): "n/a" | "known" | "unknown" {
  const intel = getIntel(it);
  if (intel.applicable === false) return "n/a";
  if (intel.known === true) return "known";
  return "unknown";
}

export function rankMemory(it: ScanItem): number | undefined {
  return it.metrics?.rank_memory_impact ?? (it as { rank_memory_impact?: number }).rank_memory_impact ?? undefined;
}

export function rankGaming(it: ScanItem): number | undefined {
  return it.metrics?.rank_gaming_impact ?? (it as { rank_gaming_impact?: number }).rank_gaming_impact ?? undefined;
}

export function rankDeletion(it: ScanItem): number | undefined {
  return it.metrics?.rank_deletion_risk ?? (it as { rank_deletion_risk?: number }).rank_deletion_risk ?? undefined;
}

export function normalizedRisk(it: ScanItem): string {
  const intel = getIntel(it);
  const ir = (intel.risk_level || "").toLowerCase();
  if (ir) return ir;
  const bucket = itemBucket(it);
  if (bucket === "risky_system_critical") return "critical";
  if (bucket === "unknown") return "unknown";
  return "other";
}

export function vendorCategoryLine(it: ScanItem): string {
  const intel = getIntel(it);
  const vendor = it.vendor ?? intel.vendor;
  const category = it.category ?? intel.category;
  if (vendor || category) return `${vendor ?? "—"} · ${category ?? "—"}`;
  return "—";
}

export function itemTypeLabel(it: ScanItem): string {
  return (it.item_type as ItemType).replaceAll("_", " ");
}
