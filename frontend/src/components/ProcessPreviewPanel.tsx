import type { ProcessPreviewEndResponse } from "../api";
import { PREVIEW_ONLY_NOTICE } from "../copy";

type Props = {
  selectedCount: number;
  confirmExplicitSelection: boolean;
  onConfirmExplicitSelectionChange: (v: boolean) => void;
  onRunPreview: () => void;
  loading: boolean;
  result: ProcessPreviewEndResponse | null;
};

const STATUS_LABEL: Record<string, string> = {
  would_allow: "Would allow",
  blocked: "Blocked",
  skipped: "Skipped",
};

export function ProcessPreviewPanel({
  selectedCount,
  confirmExplicitSelection,
  onConfirmExplicitSelectionChange,
  onRunPreview,
  loading,
  result,
}: Props) {
  const grouped = result
    ? {
        would_allow: result.items.filter((i) => i.status === "would_allow"),
        blocked: result.items.filter((i) => i.status === "blocked"),
        skipped: result.items.filter((i) => i.status === "skipped"),
      }
    : null;

  return (
    <div className="panel process-preview-panel">
      <div className="panel-header">
        <h2>Preview</h2>
        <span className="muted">{PREVIEW_ONLY_NOTICE}</span>
      </div>
      <div className="explain">
        <div className="confirm-box">
          <label>
            <input
              type="checkbox"
              checked={confirmExplicitSelection}
              onChange={(e) => onConfirmExplicitSelectionChange(e.target.checked)}
            />
            <span>I understand this may close browser windows or affect my desktop session.</span>
          </label>
        </div>

        <button type="button" className="primary" disabled={selectedCount === 0 || loading} onClick={onRunPreview}>
          {loading ? "Previewing…" : `Preview reversible suspend (${selectedCount})`}
        </button>

        {result ? (
          <>
            <p className="footer-note">{result.disclaimer}</p>
            {grouped &&
              (["would_allow", "blocked", "skipped"] as const).map((status) =>
                grouped[status].length > 0 ? (
                  <div key={status} className="preview-table-wrap">
                    <h3>
                      {STATUS_LABEL[status]} ({grouped[status].length})
                    </h3>
                    <table className="preview-table">
                      <thead>
                        <tr>
                          <th>Name</th>
                          <th>PID</th>
                          <th>Reason</th>
                        </tr>
                      </thead>
                      <tbody>
                        {grouped[status].map((row) => (
                          <tr key={row.id}>
                            <td className={`status-${status === "would_allow" ? "will_quarantine" : status}`}>
                              {row.display_name}
                            </td>
                            <td className="muted">{row.pid ?? "—"}</td>
                            <td className="muted">{row.reason}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : null
              )}
          </>
        ) : (
          <p className="muted">Select previewable items in the table, then run a preview to see what would happen.</p>
        )}
      </div>
    </div>
  );
}
