import { formatMb, PROCESS_ACTION_POLICY_LABEL } from "../processItem";

type Props = {
  totalInventoryCount: number;
  candidateCount: number;
  selectableCount: number;
  memoryMb: number;
  policyCounts: Record<string, number>;
};

export function FpsImpactSummary({
  totalInventoryCount,
  candidateCount,
  selectableCount,
  memoryMb,
  policyCounts,
}: Props) {
  return (
    <div className="dashboard-stats">
      <div className="card">
        <span className="muted">Total process inventory</span>
        <strong>{totalInventoryCount}</strong>
        <span className="muted">from the latest scan</span>
      </div>
      <div className="card">
        <span className="muted">FPS-impact candidates</span>
        <strong>{candidateCount}</strong>
        <span className="muted">
          {selectableCount} selectable now, {candidateCount - selectableCount} locked
        </span>
      </div>
      <div className="card">
        <span className="muted">Estimated memory represented</span>
        <strong>{formatMb(memoryMb)}</strong>
        <span className="muted">summed across FPS-impact candidates</span>
      </div>
      {Object.entries(policyCounts).map(([policy, count]) => (
        <div className="card" key={policy}>
          <span className="muted">{PROCESS_ACTION_POLICY_LABEL[policy] ?? policy}</span>
          <strong>{count}</strong>
          <span className="muted">candidates under this policy</span>
        </div>
      ))}
    </div>
  );
}
