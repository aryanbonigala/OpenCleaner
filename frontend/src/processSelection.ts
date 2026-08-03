import type { ScanItem } from "./api";

/**
 * UX-only mirror of backend/app/services/process_inventory.py::_preview_row.
 * The backend is the authority — this only decides what the UI *offers* to select
 * so users aren't surprised by a preview that blocks everything they checked.
 */
export type ProcessBlockReason =
  | "not_process"
  | "essential"
  | "blocked"
  | "unknown"
  | "report_only"
  | "needs_explicit_confirmation"
  | "not_reversible";

export function processSelectBlockReason(
  it: ScanItem,
  confirmExplicitSelection: boolean
): ProcessBlockReason | null {
  const pc = it.process_control;
  if (it.item_type !== "process") return "not_process";
  if (pc.category === "essential") return "essential";
  if (pc.action_policy === "blocked") return "blocked";
  if (pc.category === "unknown" || pc.action_policy === "report_only" || pc.action_policy === "unsupported") {
    return "report_only";
  }
  if (pc.action_policy === "explicit_selection_required" && !confirmExplicitSelection) {
    return "needs_explicit_confirmation";
  }
  if (!pc.safe_to_suspend) return "not_reversible";
  return null;
}

export function canPreviewProcess(it: ScanItem, confirmExplicitSelection: boolean): boolean {
  return processSelectBlockReason(it, confirmExplicitSelection) === null;
}

export const PROCESS_BLOCK_REASON_TEXT: Record<ProcessBlockReason, string> = {
  not_process: "Report-only item type — no control flow exists for it yet.",
  essential: "Essential — never selectable.",
  blocked: "Blocked by process-control policy.",
  unknown: "Unknown — not safe by default.",
  report_only: "Report-only — not offered for any action.",
  needs_explicit_confirmation: "Requires explicit selection — check the confirmation box below.",
  not_reversible: "No reversible action is classified safe for this process.",
};
