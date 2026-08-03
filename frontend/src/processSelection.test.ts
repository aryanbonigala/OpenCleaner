import { describe, expect, it } from "vitest";
import { canPreviewProcess, processSelectBlockReason } from "./processSelection";
import type { ProcessControl, ScanItem } from "./api";

function processControl(overrides: Partial<ProcessControl>): ProcessControl {
  return {
    applicable: true,
    category: "non_essential",
    action_policy: "preview_required",
    safe_to_end: false,
    safe_to_suspend: true,
    safe_to_disable_startup: false,
    confidence: 0.7,
    evidence: [],
    ...overrides,
  };
}

function item(overrides: Partial<ScanItem>): ScanItem {
  return {
    id: "1",
    scan_version: 2,
    item_type: "process",
    source: "processes",
    display_name: "x",
    raw_name: "x.exe",
    bucket: "unknown",
    risk_level: "unknown",
    protected: false,
    cleanup_eligible: false,
    performance_eligible: false,
    confidence: 0.5,
    explanation: { summary: "" },
    recommendations: {},
    provenance: [],
    timestamps: {},
    scanner_facts: {},
    process_control: processControl({}),
    ...overrides,
  };
}

describe("processSelectBlockReason", () => {
  it("blocks essential items", () => {
    const it1 = item({ process_control: processControl({ category: "essential" }) });
    expect(processSelectBlockReason(it1, false)).toBe("essential");
    expect(canPreviewProcess(it1, false)).toBe(false);
  });

  it("blocks unknown items even with explicit confirmation", () => {
    const it1 = item({ process_control: processControl({ category: "unknown" }) });
    expect(processSelectBlockReason(it1, true)).toBe("report_only");
  });

  it("blocks report-only and unsupported policies", () => {
    expect(
      processSelectBlockReason(item({ process_control: processControl({ action_policy: "report_only" }) }), false)
    ).toBe("report_only");
    expect(
      processSelectBlockReason(item({ process_control: processControl({ action_policy: "unsupported" }) }), false)
    ).toBe("report_only");
  });

  it("blocks non-process item types (services/startup/tasks are report-only)", () => {
    const it1 = item({ item_type: "service" });
    expect(processSelectBlockReason(it1, false)).toBe("not_process");
  });

  it("requires explicit confirmation for explicit_selection_required items", () => {
    const it1 = item({ process_control: processControl({ action_policy: "explicit_selection_required" }) });
    expect(processSelectBlockReason(it1, false)).toBe("needs_explicit_confirmation");
    expect(canPreviewProcess(it1, false)).toBe(false);
    expect(canPreviewProcess(it1, true)).toBe(true);
  });

  it("allows a non-essential, suspend-safe process", () => {
    const it1 = item({});
    expect(processSelectBlockReason(it1, false)).toBeNull();
    expect(canPreviewProcess(it1, false)).toBe(true);
  });

  it("blocks when not safe to suspend", () => {
    const it1 = item({ process_control: processControl({ safe_to_suspend: false }) });
    expect(processSelectBlockReason(it1, false)).toBe("not_reversible");
  });
});
