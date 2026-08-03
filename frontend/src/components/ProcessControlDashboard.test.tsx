import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ProcessControl, ProcessInventoryResponse, ScanItem } from "../api";
import { ProcessControlDashboard } from "./ProcessControlDashboard";

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
    process_control: processControl({}),
    ...overrides,
  };
}

const essentialItem = item({
  id: "essential-1",
  display_name: "System",
  scanner_facts: { pid: 100 },
  process_control: processControl({ category: "essential", action_policy: "blocked", blocked_reason: "Core OS process." }),
});

const unknownItem = item({
  id: "unknown-1",
  display_name: "Mystery.exe",
  scanner_facts: { pid: 200 },
  process_control: processControl({ category: "unknown", action_policy: "report_only" }),
});

const previewableItem = item({
  id: "previewable-1",
  display_name: "Updater.exe",
  scanner_facts: { pid: 300 },
  process_control: processControl({ category: "non_essential", action_policy: "preview_required", safe_to_suspend: true }),
});

const serviceItem = item({
  id: "service-1",
  item_type: "service",
  display_name: "Print Spooler",
  process_control: processControl({ category: "important", action_policy: "report_only" }),
});

const inventoryFixture: ProcessInventoryResponse = {
  scan_id: "scan-1",
  generated_at: "2026-01-01T00:00:00+00:00",
  platform: "Windows 11",
  items_count: 4,
  counts: { essential: 1, unknown: 1, non_essential: 1, important: 1 },
  items: [essentialItem, unknownItem, previewableItem, serviceItem],
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

describe("ProcessControlDashboard", () => {
  it("renders the Process Control view", async () => {
    render(<ProcessControlDashboard scan={null} scanning={false} onRunScan={vi.fn()} />);
    expect(await screen.findByText("Process Control")).toBeTruthy();
    expect(screen.getByText("Understand what’s running and what OpenCleaner will refuse to touch.")).toBeTruthy();
  });

  it("renders the no-scan empty state", async () => {
    installFetchMock({ ...inventoryFixture, items: [], counts: {}, items_count: 0, message: "No scan available yet. Run a scan first (POST /api/scan)." });
    render(<ProcessControlDashboard scan={null} scanning={false} onRunScan={vi.fn()} />);
    expect(await screen.findByText("Run a scan first to build a process inventory.")).toBeTruthy();
  });

  it("renders category summary counts", async () => {
    const { container } = render(<ProcessControlDashboard scan={null} scanning={false} onRunScan={vi.fn()} />);
    await screen.findByText("Process Control");
    const essentialCard = container.querySelector(".process-category-essential");
    expect(essentialCard).toBeTruthy();
    expect(within(essentialCard as HTMLElement).getByText("1")).toBeTruthy();
  });

  it("shows the essential item as locked and non-selectable", async () => {
    render(<ProcessControlDashboard scan={null} scanning={false} onRunScan={vi.fn()} />);
    const row = (await screen.findByText("System")).closest("tr") as HTMLElement;
    const checkbox = within(row).getByRole("checkbox") as HTMLInputElement;
    expect(checkbox.disabled).toBe(true);
    expect(within(row).getByText("Locked")).toBeTruthy();
  });

  it("does not allow selecting an unknown/report-only item", async () => {
    render(<ProcessControlDashboard scan={null} scanning={false} onRunScan={vi.fn()} />);
    const row = (await screen.findByText("Mystery.exe")).closest("tr") as HTMLElement;
    const checkbox = within(row).getByRole("checkbox") as HTMLInputElement;
    expect(checkbox.disabled).toBe(true);
  });

  it("disables the preview button when nothing selectable is checked", async () => {
    render(<ProcessControlDashboard scan={null} scanning={false} onRunScan={vi.fn()} />);
    const button = await screen.findByText(/Preview reversible suspend \(0\)/);
    expect((button as HTMLButtonElement).disabled).toBe(true);
  });

  it("sends a preview request for a selected previewable item and shows the disclaimer", async () => {
    render(<ProcessControlDashboard scan={null} scanning={false} onRunScan={vi.fn()} />);
    const row = (await screen.findByText("Updater.exe")).closest("tr") as HTMLElement;
    const checkbox = within(row).getByRole("checkbox") as HTMLInputElement;
    expect(checkbox.disabled).toBe(false);
    fireEvent.click(checkbox);

    const button = await screen.findByText(/Preview reversible suspend \(1\)/);
    fireEvent.click(button);

    await waitFor(() => {
      const previewCall = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/api/processes/preview-end"));
      expect(previewCall).toBeTruthy();
      const body = JSON.parse(String(previewCall?.[1]?.body ?? "{}"));
      expect(body.item_ids).toEqual(["previewable-1"]);
    });

    expect(await screen.findByText("Preview only. No process was ended, suspended, or modified.")).toBeTruthy();
    expect(endCalled).toBe(false);
  });

  it("renders cross-links to the other two surfaces", async () => {
    const onNavigate = vi.fn();
    render(<ProcessControlDashboard scan={null} scanning={false} onRunScan={vi.fn()} onNavigate={onNavigate} />);
    await screen.findByText("Process Control");

    fireEvent.click(screen.getByText("Preview gaming session →"));
    expect(onNavigate).toHaveBeenCalledWith("fps");

    fireEvent.click(screen.getByText("Ask what can be previewed →"));
    expect(onNavigate).toHaveBeenCalledWith("chat");
  });
});
