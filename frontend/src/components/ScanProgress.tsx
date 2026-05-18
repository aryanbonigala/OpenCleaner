type Props = {
  label?: string;
};

export function ScanProgress({ label = "Scanning your system…" }: Props) {
  return (
    <div className="scan-progress panel">
      <div className="scan-progress-inner">
        <div className="spinner" aria-hidden />
        <div>
          <strong>{label}</strong>
          <p className="muted">
            Reading processes, services, startup entries, and safe file locations. This stays on your
            machine — nothing is deleted during a scan.
          </p>
        </div>
      </div>
    </div>
  );
}
