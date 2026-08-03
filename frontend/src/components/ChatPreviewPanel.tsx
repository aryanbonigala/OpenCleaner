import { useState } from "react";
import { ChatCommandPreviewResponse, ProcessDetailResponse, client, parseApiError } from "../api";
import { ChatCommandInput } from "./ChatCommandInput";
import { ChatPreviewResponse } from "./ChatPreviewResponse";
import { ChatSuggestedPrompts } from "./ChatSuggestedPrompts";
import { ErrorBanner } from "./ErrorBanner";
import { ProcessControlDetails } from "./ProcessControlDetails";

type Props = {
  onRunScan: () => void;
};

export function ChatPreviewPanel({ onRunScan }: Props) {
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
        </div>
      </div>

      <ErrorBanner message={error} onDismiss={() => setError(null)} />

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
        <p className="footer-note">Preview only. No process was ended, suspended, disabled, or modified.</p>
        <p className="footer-note">Execution is not implemented. Unknown and locked items are not safe by default.</p>
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
    </div>
  );
}
