import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ChatCommandPreviewResponse, ProcessControl, ProcessDetailResponse, ScanItem } from "../api";
import { ChatPreviewPanel } from "./ChatPreviewPanel";

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

const DISCLAIMER = "Preview only. No process was ended, suspended, or modified.";
const DESTRUCTIVE_WARNING =
  "Execution is not implemented. This endpoint only previews what would be offered — nothing was ended, suspended, disabled, or removed.";

function baseResponse(overrides: Partial<ChatCommandPreviewResponse>): ChatCommandPreviewResponse {
  return {
    intent: "help",
    message: "",
    summary: "",
    items: [],
    blocked: [],
    preview: null,
    detail: null,
    actions: [],
    warnings: [],
    disclaimer: DISCLAIMER,
    ...overrides,
  };
}

function noScanResponse(message: string): ChatCommandPreviewResponse {
  return baseResponse({
    message,
    summary: "No scan available yet. Run a scan first (POST /api/scan).",
    actions: [{ kind: "run_scan", label: "Run a scan first", endpoint: "POST /api/scan", item_ids: [] }],
  });
}

function gamingResponse(message: string): ChatCommandPreviewResponse {
  return baseResponse({
    intent: "gaming_safety_preview",
    message,
    summary: "1 of 2 FPS-impacting and non-essential items would be offered as a reversible suspend. Nothing ran.",
    items: [
      {
        id: "fps-1",
        display_name: "OverlayHelper.exe",
        pid: 300,
        item_type: "process",
        category: "gaming_fps_impact",
        action_policy: "preview_required",
        status: "would_allow",
        reason: "Would be offered as a reversible suspend.",
        fps_impact: "high",
      },
    ],
    blocked: [
      {
        id: "essential-1",
        display_name: "WindowServer",
        pid: 10,
        item_type: "process",
        category: "essential",
        action_policy: "blocked",
        status: "blocked",
        reason: "Essential process.",
        blocked_reason: "Core OS process.",
      },
    ],
    preview: {
      preview_id: null,
      counts: { selected: 1, would_allow: 1, blocked: 1, skipped: 0 },
      items: [],
      disclaimer: DISCLAIMER,
    },
    actions: [
      { kind: "review_preview", label: "Review this preview in full", endpoint: "POST /api/processes/preview-end", item_ids: ["fps-1"] },
    ],
  });
}

function destructiveResponse(message: string): ChatCommandPreviewResponse {
  return { ...gamingResponse(message), warnings: [DESTRUCTIVE_WARNING] };
}

function explainResponse(message: string): ChatCommandPreviewResponse {
  return baseResponse({
    intent: "explain_process",
    message,
    summary: "Chrome is a web browser.",
    items: [
      {
        id: "chrome-1",
        display_name: "Chrome",
        pid: 400,
        item_type: "process",
        category: "non_essential",
        action_policy: "preview_required",
        status: "informational",
        reason: "Browser process.",
        user_visible_summary: "Chrome is a web browser.",
      },
    ],
    detail: { id: "chrome-1", display_name: "Chrome", pid: 400 },
    actions: [{ kind: "open_process_detail", label: "Open process detail", endpoint: "GET /api/processes/400", item_ids: ["chrome-1"] }],
  });
}

const chromeDetail: ProcessDetailResponse = {
  item: item({
    id: "chrome-1",
    display_name: "Chrome",
    scanner_facts: { pid: 400 },
    process_control: processControl({ user_visible_summary: "Chrome is a web browser." }),
  }),
  process_control: processControl({ user_visible_summary: "Chrome is a web browser." }),
  explanation: { summary: "Chrome is a web browser." },
  safety_summary: "Chrome is a web browser.",
  scanner_facts: { pid: 400 },
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

function installFetchMock(opts: { noScan?: boolean; noInventory?: boolean } = {}) {
  endCalled = false;
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (url.endsWith("/api/processes") && (!init || init.method === undefined)) {
      return Promise.resolve(
        jsonResponse(
          opts.noInventory
            ? { items_count: 0, counts: {}, items: [], warnings: [], message: "No scan available yet. Run a scan first (POST /api/scan)." }
            : { items_count: 0, counts: {}, items: [], warnings: [], message: null }
        )
      );
    }
    if (url.endsWith("/api/chat/command-preview")) {
      const body = JSON.parse(String(init?.body ?? "{}"));
      const message = String(body.message ?? "");
      if (opts.noScan) return Promise.resolve(jsonResponse(noScanResponse(message)));
      if (/kill|terminate|end|shut down/i.test(message)) return Promise.resolve(jsonResponse(destructiveResponse(message)));
      if (/explain/i.test(message)) return Promise.resolve(jsonResponse(explainResponse(message)));
      return Promise.resolve(jsonResponse(gamingResponse(message)));
    }
    if (url.endsWith("/api/processes/400")) {
      return Promise.resolve(jsonResponse(chromeDetail));
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
  installFetchMock();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function chatPostCalls() {
  return fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/api/chat/command-preview"));
}

describe("ChatPreviewPanel", () => {
  it("renders the chat view", () => {
    render(<ChatPreviewPanel onRunScan={vi.fn()} />);
    expect(screen.getByText("Ask OpenCleaner")).toBeTruthy();
    expect(
      screen.getByText("Ask what’s running, what’s locked, and what can be previewed before gaming.")
    ).toBeTruthy();
    expect(screen.getByText("What can I close before gaming?")).toBeTruthy();
  });

  it("fills and submits the command when a suggested prompt is clicked", async () => {
    render(<ChatPreviewPanel onRunScan={vi.fn()} />);
    fireEvent.click(screen.getByText("Explain Chrome"));

    await waitFor(() => expect(chatPostCalls().length).toBe(1));
    const body = JSON.parse(String(chatPostCalls()[0][1]?.body ?? "{}"));
    expect(body.message).toBe("Explain Chrome");
    expect(screen.getByRole("textbox")).toHaveProperty("value", "Explain Chrome");
  });

  it("calls POST /api/chat/command-preview when the form is submitted", async () => {
    render(<ChatPreviewPanel onRunScan={vi.fn()} />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "What can I safely suspend?" } });
    fireEvent.click(screen.getByText("Preview answer"));

    await waitFor(() => {
      const call = chatPostCalls()[0];
      expect(call).toBeTruthy();
      expect(call[1]?.method).toBe("POST");
      const body = JSON.parse(String(call[1]?.body ?? "{}"));
      expect(body.message).toBe("What can I safely suspend?");
    });
  });

  it("shows a run-scan CTA for a no-scan response instead of crashing", async () => {
    installFetchMock({ noScan: true });
    const onRunScan = vi.fn();
    render(<ChatPreviewPanel onRunScan={onRunScan} />);
    fireEvent.click(screen.getByText("What can I close before gaming?"));

    expect(await screen.findByText("No scan available yet")).toBeTruthy();
    const runScanButton = screen.getByText("Run scan");
    fireEvent.click(runScanButton);
    expect(onRunScan).toHaveBeenCalled();
  });

  it("renders summary, preview items, blocked items, and disclaimer for a gaming command", async () => {
    render(<ChatPreviewPanel onRunScan={vi.fn()} />);
    fireEvent.click(screen.getByText("What can I close before gaming?"));

    expect(await screen.findByText(/would be offered as a reversible suspend/)).toBeTruthy();
    expect(screen.getByText("OverlayHelper.exe")).toBeTruthy();
    expect(screen.getByText("WindowServer")).toBeTruthy();
    expect(screen.getAllByText(DISCLAIMER).length).toBeGreaterThan(0);
  });

  it("renders a calm destructive-command warning", async () => {
    render(<ChatPreviewPanel onRunScan={vi.fn()} />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Kill Chrome" } });
    fireEvent.click(screen.getByText("Preview answer"));

    const warning = await screen.findByText(DESTRUCTIVE_WARNING);
    expect(warning.className).toContain("warn-inline");
  });

  it("sends confirm_explicit_selection when the checkbox is checked", async () => {
    render(<ChatPreviewPanel onRunScan={vi.fn()} />);
    fireEvent.click(screen.getByLabelText(/explicit selection/));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "What can I safely suspend?" } });
    fireEvent.click(screen.getByText("Preview answer"));

    await waitFor(() => {
      const call = chatPostCalls()[0];
      const body = JSON.parse(String(call[1]?.body ?? "{}"));
      expect(body.confirm_explicit_selection).toBe(true);
    });
  });

  it("shows the open-process-detail action as safe, non-executing navigation", async () => {
    render(<ChatPreviewPanel onRunScan={vi.fn()} />);
    fireEvent.click(screen.getByText("Explain Chrome"));

    const detailButton = await screen.findByText("Open process detail");
    fireEvent.click(detailButton);

    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/api/processes/400"))).toBe(true);
    });
    expect(await screen.findByText("What it is")).toBeTruthy();
  });

  it("never calls /api/processes/end, even for destructive-sounding commands", async () => {
    render(<ChatPreviewPanel onRunScan={vi.fn()} />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Kill Chrome" } });
    fireEvent.click(screen.getByText("Preview answer"));

    await screen.findByText(DESTRUCTIVE_WARNING);
    expect(endCalled).toBe(false);
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/api/processes/end"))).toBe(false);
  });

  it("never renders an execute/kill/suspend action button", async () => {
    render(<ChatPreviewPanel onRunScan={vi.fn()} />);
    fireEvent.click(screen.getByText("What can I close before gaming?"));
    await screen.findByText("OverlayHelper.exe");

    const dangerousLabels = ["Execute", "Confirm action", "End process", "Kill process", "Suspend now"];
    for (const label of dangerousLabels) {
      expect(screen.queryByRole("button", { name: label })).toBeNull();
    }
  });

  it("shows a proactive no-scan empty state before any message is sent", async () => {
    installFetchMock({ noInventory: true });
    const onRunScan = vi.fn();
    render(<ChatPreviewPanel onRunScan={onRunScan} scan={null} />);

    expect(await screen.findByText("Run a scan first to build a process inventory.")).toBeTruthy();
    expect(screen.queryByRole("textbox")).toBeNull();
    fireEvent.click(screen.getByText("Run scan"));
    expect(onRunScan).toHaveBeenCalled();
  });

  it("renders cross-links to the other two surfaces", () => {
    const onNavigate = vi.fn();
    render(<ChatPreviewPanel onRunScan={vi.fn()} onNavigate={onNavigate} />);

    fireEvent.click(screen.getByText("Review full inventory →"));
    expect(onNavigate).toHaveBeenCalledWith("processes");

    fireEvent.click(screen.getByText("Preview gaming session →"));
    expect(onNavigate).toHaveBeenCalledWith("fps");
  });
});
