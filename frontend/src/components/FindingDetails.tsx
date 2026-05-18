import type { ExplainResponse, ScanItem } from "../api";
import { safetySummary } from "../selection";
import { getIntel, itemName, itemReasoning, itemTypeLabel, vendorCategoryLine } from "../scanItem";
import { RiskBadge } from "./RiskBadge";

type Props = {
  item: ScanItem | null;
  explain: ExplainResponse | null;
  loading: boolean;
};

export function FindingDetails({ item, explain, loading }: Props) {
  if (!item) {
    return (
      <div className="panel finding-details">
        <div className="panel-header">
          <h2>Details</h2>
        </div>
        <p className="muted" style={{ padding: 12 }}>
          Select a finding to see a plain-English explanation.
        </p>
      </div>
    );
  }

  const intel = getIntel(item);

  return (
    <div className="panel finding-details">
      <div className="panel-header">
        <h2>{itemName(item)}</h2>
        <RiskBadge item={item} />
      </div>
      <div className="explain">
        <p className="muted">{itemTypeLabel(item)} · {vendorCategoryLine(item)}</p>
        <h3>Why flagged</h3>
        <p>{itemReasoning(item)}</p>
        <h3>Safety summary</h3>
        <p>{safetySummary(item)}</p>
        {intel.recommended_action ? (
          <>
            <h3>Recommended action</h3>
            <p>{intel.recommended_action}</p>
          </>
        ) : null}
        {loading ? <p className="muted">Loading full explanation…</p> : null}
        {explain ? (
          <>
            <h3>What it does</h3>
            <p>{explain.what_it_does}</p>
            <h3>Safe to change?</h3>
            <p>{explain.safe_to_disable_or_remove}</p>
            <h3>What could break</h3>
            <p>{explain.what_could_break}</p>
          </>
        ) : null}
      </div>
    </div>
  );
}
