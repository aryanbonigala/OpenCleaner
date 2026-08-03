import type { ScanItem } from "../api";

function describe(item: ScanItem): { label: string; tone: string } {
  const pc = item.process_control;
  if (pc.category === "essential" || pc.action_policy === "blocked") {
    return { label: "Locked", tone: "locked" };
  }
  if (pc.category === "unknown") {
    return { label: "Unknown — not safe by default", tone: "unknown" };
  }
  if (item.item_type !== "process") {
    return { label: "Report-only", tone: "report" };
  }
  switch (pc.action_policy) {
    case "explicit_selection_required":
      return { label: "Explicit selection required", tone: "explicit" };
    case "preview_required":
    case "allowed_with_confirmation":
      return { label: "Preview required", tone: "preview" };
    case "unsupported":
      return { label: "Unsupported", tone: "report" };
    default:
      return { label: "Report-only", tone: "report" };
  }
}

/** Badge text always carries the meaning — never color-only. */
export function ProcessSafetyBadge({ item }: { item: ScanItem }) {
  const { label, tone } = describe(item);
  return <span className={`pill process-safety-${tone}`}>{label}</span>;
}
