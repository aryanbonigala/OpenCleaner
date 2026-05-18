import { describe, expect, it } from "vitest";
import { canSelectForCleanup, defaultSelectedIds } from "./selection";
import type { ScanItem } from "./api";

function item(overrides: Partial<ScanItem>): ScanItem {
  return {
    id: "1",
    scan_version: 1,
    item_type: "file_or_folder",
    source: "filesystem",
    display_name: "x",
    raw_name: "x",
    path: "C:\\x",
    bucket: "safe_to_remove",
    risk_level: "low",
    protected: false,
    cleanup_eligible: true,
    confidence: 0.5,
    explanation: { summary: "" },
    provenance: [],
    timestamps: {},
    scanner_facts: {},
    ...overrides,
  };
}

describe("selection", () => {
  it("selects only safe_to_remove by default", () => {
    const items = [
      item({ id: "a", bucket: "safe_to_remove" }),
      item({ id: "b", bucket: "unknown" }),
      item({ id: "c", bucket: "risky_system_critical", protected: true }),
    ];
    expect([...defaultSelectedIds(items, false)]).toEqual(["a"]);
  });

  it("blocks unknown unless advanced mode", () => {
    expect(canSelectForCleanup(item({ bucket: "unknown" }), false)).toBe(false);
    expect(canSelectForCleanup(item({ bucket: "unknown", cleanup_eligible: true }), true)).toBe(true);
    expect(canSelectForCleanup(item({ bucket: "safe_to_remove" }), false)).toBe(true);
  });
});
