import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ProcessControl, ProcessInventoryResponse, ScanItem } from "../api";
import { FpsOptimizerPanel } from "./FpsOptimizerPanel";

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
    id: overrides.id ?? "1",
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
    metrics: {},
    process_control: processControl({}),
    ...overrides,
  };
}

const essentialItem = item({
  id: "essential-1",
  display_name: "WindowServer",
  scanner_facts: { pid: 10 },
  process_control: processControl({ category: "essential", action_policy: "blocked", blocked_reason: "Core OS process." }),
});

const unknownItem = item({
  id: "unknown-1",
  display_name: "Mystery.exe",
  scanner_facts: { pid: 20 },
  process_control: processControl({ category: "unknown", action_policy: "report_only" }),
});

const fpsCandidateItem = item({
  id: "fps-1",
  display_name: "OverlayHelper.exe",
  scanner_facts: { pid: 300 },
  metrics: { memory_mb: 128 },
  process_control: processControl({ category: "gaming_fps_impact", action_policy: "preview_required", safe_to_suspend: true }),
});

const fpsExplicitItem = item({
  id: "fps-explicit-1",
  display_name: "BrowserSync.exe",
  scanner_facts: { pid: 301 },
  metrics: { memory_mb: 256 },
  process_control: processControl({
    category: "gaming_fps_impact",
    action_policy: "explicit_selection_required",
    safe_to_suspend: true,
  }),
});

const fpsBlockedItem = item({
  id: "fps-blocked-1",
  display_name: "AntiCheatOverlay.exe",
  scanner_facts: { pid: 302 },
  process_control: processControl({ category: "gaming_fps_impact", action_policy: "blocked", safe_to_suspend: false }),
});

const nonFpsServiceItem = item({
  id: "service-1",
  item_type: "service",
  display_name: "Print Spooler",
  process_control: processControl({ category: "gaming_fps_impact", action_policy: "preview_required" }),
});

const inventoryFixture: ProcessInventoryResponse = {
  scan_id: "scan-1",
  generated_at: "2026-01-01T00:00:00+00:00",
  platform: "Windows 11",
  items_count: 6,
  counts: { essential: 1, unknown: 1, gaming_fps_impact: 3 },
  items: [essentialItem, unknownItem, fpsCandidateItem, fpsExplicitItem, fpsBlockedItem, nonFpsServiceItem],
  warnings: [],
  message: null,
};

function jsonResponse(data: unknown) {
  return {
    ok: true,
    status: 200,
    headers: { get: () => "application/json" },
    json: async () => data,
    text: async () => JSON.stringify(data),
  } as unknown as Response;
}

let fetchMock: ReturnType<typeof vi.fn>;
let endCalled: boolean;

function installFetchMock(inventory: ProcessInventoryResponse) {
  endCalled = false;
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (url.endsWith("/api/processes") && (!init || init.method === undefined)) {
      return Promise.resolve(jsonResponse(inventory));
    }
    if (url.endsWith("/api/processes/preview-end")) {
      const body = JSON.parse(String(init?.body ?? "{}"));
      const rows = body.item_ids.map((id: string) => {
        const found = inventory.items.find((i) => i.id === id);
        return {
          id,
          display_name: found?.display_name ?? id,
          pid: found?.scanner_facts?.pid ?? null,
          status: "would_allow",
          recommended_action: "suspend_preview_only",
          reason: "Would be offered as a reversible suspend once execution exists. Nothing ran.",
          process_control: found?.process_control ?? null,
        };
      });
      return Promise.resolve(
        jsonResponse({
          preview_id: null,
          counts: { selected: rows.length, would_allow: rows.length, blocked: 0, skipped: 0 },
          items: rows,
          disclaimer: "Preview only. No process was ended, suspended, or modified.",
        })
      );
    }
    if (url.endsWith("/api/processes/end")) {
      endCalled = true;
      return Promise.resolve(jsonResponse({ detail: "not implemented" }));
    }
    return Promise.reject(new Error(`Unexpected fetch: ${url}`));
  });
  vi.stubGlobal("fetch", fetchMock);
}

beforeEach(() => {
  installFetchMock(inventoryFixture);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("FpsOptimizerPanel", () => {
  it("renders the FPS panel", async () => {
    render(<FpsOptimizerPanel scan={null} scanning={false} onRunScan={vi.fn()} />);
    expect(await screen.findByText("Preview gaming session")).toBeTruthy();
    expect(
      screen.getByText(
        "OpenCleaner will not touch essential, unknown, security, driver, browser, or shell processes automatically."
      )
    ).toBeTruthy();
  });

  it("only lists FPS-impact process candidates, excluding other categories and item types", async () => {
    render(<FpsOptimizerPanel scan={null} scanning={false} onRunScan={vi.fn()} />);
    await screen.findByText("OverlayHelper.exe");
    expect(screen.queryByText("WindowServer")).toBeNull();
    expect(screen.queryByText("Mystery.exe")).toBeNull();
    expect(screen.queryByText("Print Spooler")).toBeNull();
  });

  it("allows selecting a preview-required FPS candidate", async () => {
    render(<FpsOptimizerPanel scan={null} scanning={false} onRunScan={vi.fn()} />);
    const row = (await screen.findByText("OverlayHelper.exe")).closest("tr") as HTMLElement;
    const checkbox = within(row).getByRole("checkbox") as HTMLInputElement;
    expect(checkbox.disabled).toBe(false);
  });

  it("disables an essential-adjacent blocked FPS row", async () => {
    render(<FpsOptimizerPanel scan={null} scanning={false} onRunScan={vi.fn()} />);
    const row = (await screen.findByText("AntiCheatOverlay.exe")).closest("tr") as HTMLElement;
    const checkbox = within(row).getByRole("checkbox") as HTMLInputElement;
    expect(checkbox.disabled).toBe(true);
  });

  it("requires the explicit-selection checkbox before an explicit-selection item is selectable", async () => {
    render(<FpsOptimizerPanel scan={null} scanning={false} onRunScan={vi.fn()} />);
    const row = (await screen.findByText("BrowserSync.exe")).closest("tr") as HTMLElement;
    let checkbox = within(row).getByRole("checkbox") as HTMLInputElement;
    expect(checkbox.disabled).toBe(true);

    const consent = screen.getByLabelText(/I understand this may close browser windows/);
    fireEvent.click(consent);

    checkbox = within(row).getByRole("checkbox") as HTMLInputElement;
    expect(checkbox.disabled).toBe(false);
  });

  it("sends a preview-only request and never calls /api/processes/end", async () => {
    render(<FpsOptimizerPanel scan={null} scanning={false} onRunScan={vi.fn()} />);
    const row = (await screen.findByText("OverlayHelper.exe")).closest("tr") as HTMLElement;
    const checkbox = within(row).getByRole("checkbox") as HTMLInputElement;
    fireEvent.click(checkbox);

    const button = await screen.findByText(/Preview reversible suspend \(1\)/);
    fireEvent.click(button);

    await waitFor(() => {
      const previewCall = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/api/processes/preview-end"));
      expect(previewCall).toBeTruthy();
      const body = JSON.parse(String(previewCall?.[1]?.body ?? "{}"));
      expect(body.item_ids).toEqual(["fps-1"]);
    });

    expect(await screen.findByText("Preview only. No process was ended, suspended, or modified.")).toBeTruthy();
    expect(endCalled).toBe(false);
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/api/processes/end"))).toBe(false);
  });

  it("renders the no-candidates empty state when nothing is FPS-impact", async () => {
    installFetchMock({ ...inventoryFixture, items: [essentialItem, unknownItem], items_count: 2 });
    render(<FpsOptimizerPanel scan={null} scanning={false} onRunScan={vi.fn()} />);
    expect(await screen.findByText("No FPS-impact candidates in this scan.")).toBeTruthy();
  });

  it("renders the no-scan empty state", async () => {
    installFetchMock({ ...inventoryFixture, items: [], counts: {}, items_count: 0, message: "No scan available yet. Run a scan first (POST /api/scan)." });
    render(<FpsOptimizerPanel scan={null} scanning={false} onRunScan={vi.fn()} />);
    expect(await screen.findByText("Run a scan first to build a process inventory.")).toBeTruthy();
  });
});
