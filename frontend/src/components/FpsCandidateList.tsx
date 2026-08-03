import type { ScanItem } from "../api";
import { formatCpu, formatMb, pidOf, reasonPreview, PROCESS_ACTION_POLICY_LABEL } from "../processItem";
import { PROCESS_BLOCK_REASON_TEXT, processSelectBlockReason } from "../processSelection";
import { EmptyState } from "./EmptyState";
import { ProcessSafetyBadge } from "./ProcessSafetyBadge";

type Props = {
  items: ScanItem[];
  selectedIds: Set<string>;
  confirmExplicitSelection: boolean;
  onToggle: (id: string) => void;
};

export function FpsCandidateList({ items, selectedIds, confirmExplicitSelection, onToggle }: Props) {
  if (items.length === 0) {
    return (
      <EmptyState
        title="No FPS-impact candidates in this scan."
        description="OpenCleaner only lists processes the backend already classified as gaming/FPS-impact. Run a fresh scan, or check Process Control for the full inventory."
      />
    );
  }

  return (
    <div className="table-wrap process-table-wrap">
      <table className="process-table">
        <thead>
          <tr>
            <th />
            <th>Name</th>
            <th>PID</th>
            <th>Memory</th>
            <th>CPU</th>
            <th>Policy</th>
            <th>Safety</th>
            <th>Reason / evidence</th>
          </tr>
        </thead>
        <tbody>
          {items.map((it) => {
            const blockReason = processSelectBlockReason(it, confirmExplicitSelection);
            const selectable = blockReason === null;
            const pc = it.process_control;
            return (
              <tr key={it.id} className={selectable ? "" : "process-row-locked"}>
                <td>
                  <input
                    type="checkbox"
                    checked={selectedIds.has(it.id)}
                    disabled={!selectable}
                    title={blockReason ? PROCESS_BLOCK_REASON_TEXT[blockReason] : "Selectable for preview"}
                    onChange={() => onToggle(it.id)}
                  />
                </td>
                <td className="cell-long-text">{it.display_name}</td>
                <td className="muted">{pidOf(it) ?? "—"}</td>
                <td>{formatMb(it.metrics?.memory_mb)}</td>
                <td>{formatCpu(it.metrics?.cpu_percent)}</td>
                <td className="muted">{PROCESS_ACTION_POLICY_LABEL[pc.action_policy] ?? pc.action_policy}</td>
                <td>
                  <ProcessSafetyBadge item={it} />
                </td>
                <td className="muted process-reason-cell">
                  {blockReason ? PROCESS_BLOCK_REASON_TEXT[blockReason] : reasonPreview(it)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
