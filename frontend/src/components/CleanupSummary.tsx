import { formatBytes } from "../selection";

type Summary = {
  estimated_bytes?: number;
  confirmed_bytes?: number;
  quarantined?: number;
  skipped?: number;
  failed?: number;
  blocked?: number;
  reclaimed_mb?: number;
};

type Props = {
  result: Summary;
  onViewQuarantine: () => void;
  onDone: () => void;
};

export function CleanupSummary({ result, onViewQuarantine, onDone }: Props) {
  const est = result.estimated_bytes ?? 0;
  const confirmed = result.confirmed_bytes ?? 0;

  return (
    <div className="cleanup-summary panel">
      <div className="panel-header">
        <h2>Cleanup finished</h2>
      </div>
      <div className="cleanup-summary-body">
        <div className="dashboard-stats">
          <div className="card">
            <span className="muted">Estimated (preview)</span>
            <strong>{formatBytes(est)}</strong>
          </div>
          <div className="card">
            <span className="muted">Confirmed quarantined</span>
            <strong>{formatBytes(confirmed)}</strong>
          </div>
          <div className="card">
            <span className="muted">Outcomes</span>
            <strong>
              {result.quarantined ?? 0} quarantined · {result.skipped ?? 0} skipped · {result.failed ?? 0}{" "}
              failed
            </strong>
          </div>
        </div>
        {confirmed < est ? (
          <p className="warn-inline">
            Confirmed size is lower than the estimate — some files may have been in use, skipped, or
            blocked at execution time.
          </p>
        ) : null}
        <p className="muted">
          You can restore quarantined files from the Quarantine screen. OpenCleaner does not send data
          off your device.
        </p>
        <div className="actions">
          <button type="button" className="primary" onClick={onViewQuarantine}>
            Open quarantine
          </button>
          <button type="button" onClick={onDone}>
            Back to dashboard
          </button>
        </div>
      </div>
    </div>
  );
}
