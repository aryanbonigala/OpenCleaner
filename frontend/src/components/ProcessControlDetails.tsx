import { Fragment } from "react";
import type { ProcessDetailResponse, ScanItem } from "../api";
import { factValue, itemTypeLabel, pidOf, unavailableFacts } from "../processItem";
import { ProcessSafetyBadge } from "./ProcessSafetyBadge";

type Props = {
  item: ScanItem | null;
  detail: ProcessDetailResponse | null;
  loading: boolean;
};

const FACT_ROWS: Array<{ key: string; label: string }> = [
  { key: "pid", label: "PID" },
  { key: "ppid", label: "Parent PID" },
  { key: "parent_name", label: "Parent process" },
  { key: "username", label: "User" },
  { key: "executable_basename", label: "Executable" },
  { key: "path", label: "Path" },
  { key: "status", label: "Status" },
  { key: "child_pids", label: "Child PIDs" },
  { key: "signature_status", label: "Signature" },
];

export function ProcessControlDetails({ item, detail, loading }: Props) {
  if (!item) {
    return (
      <div className="panel process-details">
        <div className="panel-header">
          <h2>Details</h2>
        </div>
        <p className="muted" style={{ padding: 12 }}>
          Select a running item to see what it is and why OpenCleaner classified it this way.
        </p>
      </div>
    );
  }

  const pc = detail?.process_control ?? item.process_control;
  const unavailable = unavailableFacts(item);
  const warnings = item.recommendations?.warnings ?? [];

  return (
    <div className="panel process-details">
      <div className="panel-header">
        <h2>{item.display_name}</h2>
        <ProcessSafetyBadge item={item} />
      </div>
      <div className="explain">
        <p className="muted">
          {itemTypeLabel(item)} · {item.vendor ?? "Vendor unknown"} {item.category ? `· ${item.category}` : ""}
        </p>

        <h3>What it is</h3>
        <p>{pc.user_visible_summary || detail?.safety_summary || item.explanation.summary || "No summary available."}</p>

        <h3>Why classified this way</h3>
        {pc.blocked_reason ? <p>{pc.blocked_reason}</p> : null}
        {pc.evidence.length > 0 ? (
          <ul>
            {pc.evidence.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        ) : (
          <p className="muted">No evidence recorded.</p>
        )}
        <p className="muted">Confidence: {(pc.confidence * 100).toFixed(0)}%</p>

        <h3>What could break</h3>
        {warnings.length > 0 ? (
          <ul>
            {warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        ) : (
          <p className="muted">{item.recommendations?.primary || "No specific warning recorded."}</p>
        )}

        <h3>Process facts</h3>
        <div className="safety-grid">
          <dl>
            {FACT_ROWS.map(({ key, label }) => {
              const value = key === "pid" ? pidOf(item) : factValue(item, key);
              if (value === null || value === undefined) return null;
              return (
                <Fragment key={key}>
                  <dt>{label}</dt>
                  <dd>{Array.isArray(value) ? value.join(", ") || "—" : String(value)}</dd>
                </Fragment>
              );
            })}
          </dl>
        </div>
        {unavailable.length > 0 ? (
          <p className="muted process-unavailable-facts">Not available: {unavailable.join(", ")}</p>
        ) : null}

        {loading ? <p className="muted">Refreshing from latest scan…</p> : null}
      </div>
    </div>
  );
}
