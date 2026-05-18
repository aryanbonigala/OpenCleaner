import type { ScanResult } from "../api";

type Props = {
  scan: ScanResult | null;
  version: string | null;
  onRunScan: () => void;
  onViewResults: () => void;
  onQuarantine: () => void;
  scanning: boolean;
};

export function Dashboard({ scan, version, onRunScan, onViewResults, onQuarantine, scanning }: Props) {
  const fileItems = scan?.items.filter((i) => i.item_type === "file_or_folder") ?? [];
  const cleanupReady = fileItems.filter((i) => i.cleanup_eligible).length;

  return (
    <div className="dashboard panel">
      <div className="panel-header">
        <h2>Dashboard</h2>
        {version ? <span className="muted">v{version}</span> : null}
      </div>
      <div className="dashboard-body">
        <p>
          OpenCleaner helps you <strong>review</strong> what is on your PC and optionally move selected
          files to a <strong>local quarantine folder</strong> you can restore later. It does not delete
          things automatically.
        </p>
        <ol className="flow-steps">
          <li>Run a scan (read-only)</li>
          <li>Review findings and risk labels</li>
          <li>Preview cleanup, then quarantine selected files</li>
          <li>Restore from quarantine if needed</li>
        </ol>
        {scan ? (
          <div className="dashboard-stats">
            <div className="card">
              <span className="muted">Last scan</span>
              <strong>{scan.summary.items_count} items</strong>
              <span className="muted">{scan.summary.platform}</span>
            </div>
            <div className="card">
              <span className="muted">Files ready for review</span>
              <strong>{cleanupReady}</strong>
              <span className="muted">marked cleanup-eligible</span>
            </div>
          </div>
        ) : null}
        <div className="dashboard-actions">
          <button type="button" className="primary" disabled={scanning} onClick={onRunScan}>
            {scan ? "Run scan again" : "Run scan"}
          </button>
          {scan ? (
            <>
              <button type="button" disabled={scanning} onClick={onViewResults}>
                Review findings
              </button>
              <button type="button" disabled={scanning} onClick={onQuarantine}>
                Quarantine folder
              </button>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
