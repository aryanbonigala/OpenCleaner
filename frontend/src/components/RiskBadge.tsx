import type { RiskBucket } from "../api";
import { itemBucket } from "../scanItem";
import type { ScanItem } from "../api";

const LABELS: Record<RiskBucket, string> = {
  safe_to_remove: "Low risk — cache/temp style",
  probably_safe: "Probably safe — review path",
  ask_user: "Review recommended",
  unknown: "Unknown — verify first",
  risky_system_critical: "Critical — do not change",
};

export function RiskBadge({ item }: { item: ScanItem }) {
  const bucket = itemBucket(item);
  const risky = bucket === "risky_system_critical";
  const safe = bucket === "safe_to_remove" || bucket === "probably_safe";
  const cls = risky ? "pill risky" : safe ? "pill safe" : bucket === "unknown" ? "pill intel-unknown" : "pill";
  return (
    <span className={cls} title={LABELS[bucket]}>
      {bucket.replaceAll("_", " ")}
    </span>
  );
}
