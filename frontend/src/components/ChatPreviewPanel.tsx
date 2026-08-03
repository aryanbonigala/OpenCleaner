import { useState } from "react";
import { ChatCommandPreviewResponse, ProcessDetailResponse, ScanResult, client, parseApiError } from "../api";
import { PREVIEW_ONLY_NOTICE } from "../copy";
import { useProcessInventory } from "../useProcessInventory";
import { ChatCommandInput } from "./ChatCommandInput";
import { ChatPreviewResponse } from "./ChatPreviewResponse";
import { ChatSuggestedPrompts } from "./ChatSuggestedPrompts";
import { EmptyState } from "./EmptyState";
import { ErrorBanner } from "./ErrorBanner";
import { ProcessControlDetails } from "./ProcessControlDetails";
import { SurfaceCrossLinks, type Surface } from "./SurfaceCrossLinks";

type Props = {
  onRunScan: () => void;
  scan?: ScanResult | null;
  onNavigate?: (target: Surface) => void;
};

export function ChatPreviewPanel({ onRunScan, scan = null, onNavigate }: Props) {
  const { noScan } = useProcessInventory(scan);
  const [message, setMessage] = useState("");
  const [confirmExplicitSelection, setConfirmExplicitSelection] = useState(false);
  const [lastMessage, setLastMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<ChatCommandPreviewResponse | null>(null);

  const [detailPid, setDetailPid] = useState<number | null>(null);
  const [detailResult, setDetailResult] = useState<ProcessDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  async function submit(text: string, confirm = confirmExplicitSelection) {
    const trimmed = text.trim();
    if (!trimmed) return;
    setError(null);
    setLoading(true);
    try {
      const res = await client.previewChatCommand(trimmed, confirm);
      setResponse(res);
      setLastMessage(trimmed);
    } catch (e) {
      setError(parseApiError(e));
    } finally {
      setLoading(false);
    }
  }

  function handleSuggested(prompt: string) {
    setMessage(prompt);
    void submit(prompt);
  }

  function handleEnableExplicitSelection() {
    setConfirmExplicitSelection(true);
    void submit(lastMessage || message, true);
  }

  async function handleOpenProcessDetail(pid: number) {
    setDetailPid(pid);
    setDetailResult(null);
    setDetailLoading(true);
    try {
      const d = await client.getProcessByPid(pid);
      setDetailResult(d);
    } catch (e) {
      setError(parseApiError(e));
    } finally {
      setDetailLoading(false);
    }
  }

  return (
    <div className="panel chat-panel">
      <div className="panel-header chat-header">
        <div>
          <h2>Ask OpenCleaner</h2>
          <p className="muted">Ask what&rsquo;s running, what&rsquo;s locked, and what can be previewed before gaming.</p>
          <p className="muted">{PREVIEW_ONLY_NOTICE}</p>
          <SurfaceCrossLinks current="chat" onNavigate={onNavigate} />
        </div>
      </div>

      <ErrorBanner message={error} onDismiss={() => setError(null)} />

      {noScan ? (
        <EmptyState
          title="Run a scan first to build a process inventory."
          description="No scan available yet. Run a scan first (POST /api/scan)."
          action={
            <button type="button" className="primary" onClick={onRunScan}>
              Run scan
            </button>
          }
        />
      ) : (
        <>
          <ChatCommandInput
            value={message}
            onChange={setMessage}
            confirmExplicitSelection={confirmExplicitSelection}
            onConfirmExplicitSelectionChange={setConfirmExplicitSelection}
            onSubmit={() => submit(message)}
            loading={loading}
          />

          <ChatSuggestedPrompts onSelect={handleSuggested} />

          <div className="chat-safety-footer">
            <p className="footer-note">Unknown and locked items are not safe by default.</p>
          </div>

          {response ? (
            <ChatPreviewResponse
              response={response}
              onRunScan={onRunScan}
              onEnableExplicitSelection={handleEnableExplicitSelection}
              onOpenProcessDetail={handleOpenProcessDetail}
            />
          ) : null}

          {detailPid ? (
            detailResult ? (
              <ProcessControlDetails item={detailResult.item} detail={detailResult} loading={detailLoading} />
            ) : (
              <p className="muted">Loading process detail…</p>
            )
          ) : null}
        </>
      )}
    </div>
  );
}
