import type { ScanItem } from "../api";
import { formatCpu, formatMb, itemTypeLabel, pidOf, reasonPreview, PROCESS_CATEGORY_LABEL, PROCESS_ACTION_POLICY_LABEL } from "../processItem";
import { PROCESS_BLOCK_REASON_TEXT, processSelectBlockReason } from "../processSelection";
import { ProcessSafetyBadge } from "./ProcessSafetyBadge";

type Props = {
  items: ScanItem[];
  selectedIds: Set<string>;
  confirmExplicitSelection: boolean;
  onToggle: (id: string) => void;
  onOpen: (item: ScanItem) => void;
  openId?: string | null;
};

export function ProcessControlTable({ items, selectedIds, confirmExplicitSelection, onToggle, onOpen, openId }: Props) {
  return (
    <div className="table-wrap process-table-wrap">
      <table className="process-table">
        <thead>
          <tr>
            <th />
            <th>Name</th>
            <th>Type</th>
            <th>Category</th>
            <th>Policy</th>
            <th>Memory</th>
            <th>CPU</th>
            <th>PID</th>
            <th>Vendor</th>
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
              <tr
                key={it.id}
                className={`${selectable ? "" : "process-row-locked"} ${openId === it.id ? "process-row-open" : ""}`}
              >
                <td>
                  <input
                    type="checkbox"
                    checked={selectedIds.has(it.id)}
                    disabled={!selectable}
                    title={blockReason ? PROCESS_BLOCK_REASON_TEXT[blockReason] : "Selectable for preview"}
                    onChange={() => onToggle(it.id)}
                  />
                </td>
                <td>
                  <button type="button" className="finding-title" onClick={() => onOpen(it)}>
                    {it.display_name}
                  </button>
                </td>
                <td className="muted">{itemTypeLabel(it)}</td>
                <td>{PROCESS_CATEGORY_LABEL[pc.category] ?? pc.category}</td>
                <td className="muted">{PROCESS_ACTION_POLICY_LABEL[pc.action_policy] ?? pc.action_policy}</td>
                <td>{formatMb(it.metrics?.memory_mb)}</td>
                <td>{formatCpu(it.metrics?.cpu_percent)}</td>
                <td className="muted">{pidOf(it) ?? "—"}</td>
                <td className="muted">{it.vendor ?? "—"}</td>
                <td>
                  <ProcessSafetyBadge item={it} />
                </td>
                <td className="muted process-reason-cell">{reasonPreview(it)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
