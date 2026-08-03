import type { CleanupPreviewResponse } from "../api";
import { formatBytes } from "../selection";

type Props = {
  preview: CleanupPreviewResponse;
  confirmCleanup: boolean;
  confirmMedium: boolean;
  confirmPermanent: boolean;
  onConfirmCleanup: (v: boolean) => void;
  onConfirmMedium: (v: boolean) => void;
  onConfirmPermanent: (v: boolean) => void;
  onBack: () => void;
  onExecute: () => void;
};

export function CleanupReview({
  preview,
  confirmCleanup,
  confirmMedium,
  confirmPermanent,
  onConfirmCleanup,
  onConfirmMedium,
  onConfirmPermanent,
  onBack,
  onExecute,
}: Props) {
  const blocked = preview.items.filter((i) => i.status === "blocked");
  const skipped = preview.items.filter((i) => i.status === "skipped");
  const will = preview.items.filter((i) => i.status === "will_quarantine");

  const canExecute =
    confirmCleanup &&
    will.length > 0 &&
    (!preview.include_recycle_bin || confirmPermanent);

  return (
    <div className="cleanup-review panel">
      <div className="panel-header">
        <h2>Review cleanup</h2>
        <span className="muted">Preview only until you confirm</span>
      </div>
      <div className="cleanup-review-body">
        <p>{preview.disclaimer}</p>
        <div className="cleanup-estimate card">
          <span className="muted">Estimated space (selected files)</span>
          <strong>{formatBytes(preview.estimated_bytes)}</strong>
          <span className="muted">
            {preview.counts.will_quarantine} to quarantine · {preview.counts.blocked} blocked ·{" "}
            {preview.counts.skipped} skipped
          </span>
        </div>

        <div className="preview-table-wrap">
          <table className="preview-table">
            <thead>
              <tr>
                <th>Item</th>
                <th>Status</th>
                <th>Est.</th>
                <th>Why</th>
              </tr>
            </thead>
            <tbody>
              {preview.items.map((row) => (
                <tr key={row.id}>
                  <td className="cell-long-text">
                    <strong>{row.display_name}</strong>
                    <div className="muted">{row.path}</div>
                  </td>
                  <td>
                    <span className={`status-${row.status}`}>{row.status.replaceAll("_", " ")}</span>
                  </td>
                  <td>{row.estimated_bytes ? formatBytes(row.estimated_bytes) : "—"}</td>
                  <td>{row.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {blocked.length > 0 ? (
          <p className="muted">
            {blocked.length} item(s) were blocked by safety rules and will not be changed.
          </p>
        ) : null}

        <div className="confirm-box">
          <label>
            <input type="checkbox" checked={confirmCleanup} onChange={(e) => onConfirmCleanup(e.target.checked)} />
            I reviewed the list above and want to move the listed files to <strong>local quarantine</strong>{" "}
            (reversible).
          </label>
          {preview.confirm_medium_risk ? (
            <label>
              <input type="checkbox" checked={confirmMedium} onChange={(e) => onConfirmMedium(e.target.checked)} />
              I accept including medium-risk paths from this preview.
            </label>
          ) : null}
          {preview.include_recycle_bin ? (
            <label className="danger-label">
              <input
                type="checkbox"
                checked={confirmPermanent}
                onChange={(e) => onConfirmPermanent(e.target.checked)}
              />
              I understand emptying the Recycle Bin is <strong>permanent</strong> and separate from quarantine.
              {preview.recycle_bin_note ? <span className="muted"> {preview.recycle_bin_note}</span> : null}
            </label>
          ) : null}
        </div>

        <div className="actions">
          <button type="button" onClick={onBack}>
            Back to results
          </button>
          <button type="button" className="primary danger" disabled={!canExecute} onClick={onExecute}>
            Quarantine selected files
          </button>
        </div>
      </div>
    </div>
  );
}
