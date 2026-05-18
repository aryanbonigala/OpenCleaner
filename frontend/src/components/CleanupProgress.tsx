export function CleanupProgress() {
  return (
    <div className="cleanup-progress panel">
      <div className="scan-progress-inner">
        <div className="spinner" aria-hidden />
        <div>
          <strong>Moving files to quarantine…</strong>
          <p className="muted">Files are copied to a local folder first. Nothing is permanently deleted unless you empty the Recycle Bin separately.</p>
        </div>
      </div>
    </div>
  );
}
