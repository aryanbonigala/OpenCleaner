import { formatBytes } from "../selection";
import { EmptyState } from "./EmptyState";

export type QuarantineEntry = {
  id: string;
  original_path: string;
  quarantine_path: string;
  size_bytes?: number | null;
  restored: boolean | number;
  created_at: string;
};

type Props = {
  entries: QuarantineEntry[];
  loading: boolean;
  onRestore: (id: string) => void;
  busyId: string | null;
};

export function QuarantineManager({ entries, loading, onRestore, busyId }: Props) {
  const active = entries.filter((e) => !e.restored);

  return (
    <div className="quarantine-manager panel">
      <div className="panel-header">
        <h2>Quarantine</h2>
        <span className="muted">{active.length} restorable</span>
      </div>
      <p style={{ padding: "0 12px" }} className="muted">
        Files moved during assisted cleanup are stored here. Restoring puts them back at the original path
        when possible.
      </p>
      {loading ? <p className="muted" style={{ padding: 12 }}>Loading…</p> : null}
      {!loading && active.length === 0 ? (
        <EmptyState title="Quarantine is empty" description="No files are waiting to be restored." />
      ) : (
        <div className="quarantine-list">
          {active.map((e) => (
            <div key={e.id} className="quarantine-row">
              <div className="flex-long-text">
                <strong>{e.original_path}</strong>
                <div className="muted">
                  {e.size_bytes ? formatBytes(e.size_bytes) : "—"} · {e.created_at}
                </div>
              </div>
              <button type="button" disabled={busyId === e.id} onClick={() => onRestore(e.id)}>
                Restore
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
