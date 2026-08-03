import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

function jsonResponse(data: unknown) {
  return {
    ok: true,
    status: 200,
    headers: { get: () => "application/json" },
    json: async () => data,
    text: async () => JSON.stringify(data),
  } as unknown as Response;
}

const healthFixture = {
  status: "ok",
  version: "0.1.1",
  api_version: "0.1",
  stage: "dev",
  scan_in_progress: "false",
};

let fetchMock: ReturnType<typeof vi.fn>;

function installFetchMock(opts: { healthFails?: boolean }) {
  fetchMock = vi.fn((url: string) => {
    if (url.endsWith("/health")) {
      if (opts.healthFails) return Promise.reject(new Error("connection refused"));
      return Promise.resolve(jsonResponse(healthFixture));
    }
    if (url.endsWith("/api/mode")) return Promise.resolve(jsonResponse({ mode: "read_only" }));
    if (url.endsWith("/api/settings")) {
      return Promise.resolve(
        jsonResponse({
          settings_version: 1,
          cleanup_mode: "quarantine_only",
          risk_visibility: "basic",
          scanner_toggles: { files: true, browser: true, startup: true, tasks: true, performance: true },
          quarantine_retention: "14_days",
          logging_mode: "normal",
        })
      );
    }
    if (url.endsWith("/api/scan/latest")) return Promise.resolve(jsonResponse(null));
    return Promise.reject(new Error(`Unexpected fetch: ${url}`));
  });
  vi.stubGlobal("fetch", fetchMock);
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("App backend readiness gate", () => {
  it("shows a waiting state while health is pending", async () => {
    installFetchMock({});
    render(<App />);
    expect(await screen.findByText("Waiting for backend…")).toBeTruthy();
  });

  it("shows the normal app shell once health succeeds", async () => {
    installFetchMock({});
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Process Control" })).toBeTruthy();
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/api/mode"))).toBe(true);
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/api/settings"))).toBe(true);
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/api/scan/latest"))).toBe(true);
  });

  it("shows backend-not-reachable after bounded retries and never calls startup endpoints", async () => {
    installFetchMock({ healthFails: true });
    render(<App />);

    await vi.runAllTimersAsync();

    expect(await screen.findByText(/Backend not reachable/)).toBeTruthy();
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/api/mode"))).toBe(false);
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/api/settings"))).toBe(false);
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/api/scan/latest"))).toBe(false);
  });

  it("retry re-runs the health check and proceeds once backend is available", async () => {
    installFetchMock({ healthFails: true });
    render(<App />);
    await vi.runAllTimersAsync();
    await screen.findByText(/Backend not reachable/);

    installFetchMock({});
    fireEvent.click(screen.getByText("Retry"));

    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/health"))).toBe(true);
    });
    expect(await screen.findByRole("heading", { name: "Process Control" })).toBeTruthy();
  });
});
