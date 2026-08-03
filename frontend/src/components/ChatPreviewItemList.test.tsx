import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { ChatCommandPreviewItem } from "../api";
import { ChatPreviewItemList } from "./ChatPreviewItemList";

afterEach(() => {
  cleanup();
});

function makeItems(count: number): ChatCommandPreviewItem[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `item-${i}`,
    display_name: `Process ${i}`,
    item_type: "process",
    category: "non_essential",
    action_policy: "preview_required",
    status: "informational",
    reason: "Unknown process.",
  }));
}

describe("ChatPreviewItemList", () => {
  it("renders nothing for an empty list", () => {
    const { container } = render(<ChatPreviewItemList title="Informational" items={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("shows all items with no controls when under the cap", () => {
    render(<ChatPreviewItemList title="Informational" items={makeItems(10)} />);
    expect(screen.getByText("Process 0")).toBeTruthy();
    expect(screen.getByText("Process 9")).toBeTruthy();
    expect(screen.queryByText(/^Showing/)).toBeNull();
    expect(screen.queryByText("Show more")).toBeNull();
  });

  it("caps to 25 by default and shows a Show more control", () => {
    render(<ChatPreviewItemList title="Informational" items={makeItems(60)} />);
    expect(screen.getByText("Showing 25 of 60")).toBeTruthy();
    expect(screen.getByText("Process 24")).toBeTruthy();
    expect(screen.queryByText("Process 25")).toBeNull();
    expect(screen.getByText("Show more")).toBeTruthy();
  });

  it("Show more reveals the rest and Show less resets", () => {
    render(<ChatPreviewItemList title="Informational" items={makeItems(60)} />);
    fireEvent.click(screen.getByText("Show more"));

    expect(screen.getByText("Showing 60 of 60")).toBeTruthy();
    expect(screen.getByText("Process 59")).toBeTruthy();

    fireEvent.click(screen.getByText("Show less"));
    expect(screen.getByText("Showing 25 of 60")).toBeTruthy();
    expect(screen.queryByText("Process 59")).toBeNull();
  });

  it("caps two lists independently", () => {
    render(
      <>
        <ChatPreviewItemList title="Allowed" items={makeItems(40)} />
        <ChatPreviewItemList title="Blocked" items={makeItems(5)} />
      </>
    );
    expect(screen.getByText("Showing 25 of 40")).toBeTruthy();
    expect(screen.getAllByText("Show more").length).toBe(1);
  });

  it("never renders an execute/kill/suspend button in a large list", () => {
    render(<ChatPreviewItemList title="Informational" items={makeItems(60)} />);
    fireEvent.click(screen.getByText("Show more"));
    const dangerousLabels = ["Execute", "End process", "Kill process", "Suspend now"];
    for (const label of dangerousLabels) {
      expect(screen.queryByRole("button", { name: label })).toBeNull();
    }
  });
});
