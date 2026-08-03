import type { ChatCommandPreviewAction, ChatCommandPreviewResponse } from "../api";
import { ChatPreviewItemList } from "./ChatPreviewItemList";
import { EmptyState } from "./EmptyState";

type Props = {
  response: ChatCommandPreviewResponse;
  onRunScan: () => void;
  onEnableExplicitSelection: () => void;
  onOpenProcessDetail: (pid: number) => void;
};

function findPid(response: ChatCommandPreviewResponse, action: ChatCommandPreviewAction): number | null {
  const match = [...response.items, ...response.blocked].find((it) => action.item_ids.includes(it.id));
  if (match?.pid) return match.pid;
  const detailPid = response.detail?.pid;
  return typeof detailPid === "number" ? detailPid : null;
}

function ActionControl({ action, response, onRunScan, onEnableExplicitSelection, onOpenProcessDetail }: Props & { action: ChatCommandPreviewAction }) {
  switch (action.kind) {
    case "run_scan":
      return (
        <button type="button" className="primary" onClick={onRunScan}>
          {action.label}
        </button>
      );
    case "confirm_explicit_selection":
      return (
        <button type="button" onClick={onEnableExplicitSelection}>
          {action.label}
        </button>
      );
    case "review_preview":
      return (
        <a className="chat-action-link" href="#chat-preview-result">
          {action.label}
          {action.item_ids.length > 0 ? ` (${action.item_ids.length} item${action.item_ids.length === 1 ? "" : "s"})` : ""}
        </a>
      );
    case "open_process_detail": {
      const pid = findPid(response, action);
      if (!pid) return <span className="muted">{action.label}</span>;
      return (
        <button type="button" onClick={() => onOpenProcessDetail(pid)}>
          {action.label}
        </button>
      );
    }
    case "none":
    default:
      return <span className="muted chat-action-info">{action.label}</span>;
  }
}

export function ChatPreviewResponse({ response, onRunScan, onEnableExplicitSelection, onOpenProcessDetail }: Props) {
  const noScanAvailable =
    response.actions.some((a) => a.kind === "run_scan") && response.items.length === 0 && response.blocked.length === 0;

  if (noScanAvailable) {
    return (
      <div className="chat-response card">
        <EmptyState
          title="No scan available yet"
          description={response.summary}
          action={
            <button type="button" className="primary" onClick={onRunScan}>
              Run scan
            </button>
          }
        />
      </div>
    );
  }

  return (
    <div className="chat-response card">
      <span className="muted chat-intent">{response.intent.replace(/_/g, " ")}</span>
      <p className="chat-summary">{response.summary}</p>

      {response.warnings.length > 0 ? (
        <ul className="chat-warnings">
          {response.warnings.map((w, i) => (
            <li key={i} className="warn-inline">
              {w}
            </li>
          ))}
        </ul>
      ) : null}

      <ChatPreviewItemList title="Would be offered as a preview" items={response.items} />
      <ChatPreviewItemList title="Held back — locked, unknown, or informational" items={response.blocked} />

      {response.preview ? (
        <div id="chat-preview-result" className="chat-preview-result">
          <h4>Preview result</h4>
          <p className="muted">
            {Object.entries(response.preview.counts)
              .map(([key, value]) => `${key}: ${value}`)
              .join(" · ")}
          </p>
          <p className="footer-note">{response.preview.disclaimer}</p>
        </div>
      ) : null}

      {response.actions.length > 0 ? (
        <div className="chat-action-row">
          {response.actions.map((action, i) => (
            <ActionControl
              key={`${action.kind}-${i}`}
              action={action}
              response={response}
              onRunScan={onRunScan}
              onEnableExplicitSelection={onEnableExplicitSelection}
              onOpenProcessDetail={onOpenProcessDetail}
            />
          ))}
        </div>
      ) : null}

      <p className="footer-note">{response.disclaimer}</p>
    </div>
  );
}
