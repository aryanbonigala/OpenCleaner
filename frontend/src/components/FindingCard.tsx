import type { ScanItem } from "../api";
import { canSelectForCleanup, formatBytes, safetySummary, selectBlockReason } from "../selection";
import { getIntel, itemName, itemTypeLabel, knownLabel, vendorCategoryLine } from "../scanItem";
import { RiskBadge } from "./RiskBadge";

type Props = {
  item: ScanItem;
  selected: boolean;
  advancedMode: boolean;
  onToggle: (id: string) => void;
  onOpen: (item: ScanItem) => void;
};

export function FindingCard({ item, selected, advancedMode, onToggle, onOpen }: Props) {
  const selectable = canSelectForCleanup(item, advancedMode);
  const block = selectBlockReason(item, advancedMode);
  const intel = getIntel(item);
  const sizeMb = item.metrics?.size_mb;
  const sizeBytes =
    typeof sizeMb === "number" ? Math.round(sizeMb * 1024 * 1024) : undefined;

  return (
    <article className={`finding-card ${selected ? "selected" : ""} ${!selectable ? "disabled" : ""}`}>
      <div className="finding-card-top">
        <label className="finding-check">
          <input
            type="checkbox"
            checked={selected}
            disabled={!selectable}
            onChange={() => onToggle(item.id)}
          />
          <span className="sr-only">Select {itemName(item)}</span>
        </label>
        <button type="button" className="finding-title" onClick={() => onOpen(item)}>
          {itemName(item)}
        </button>
        <RiskBadge item={item} />
        <span className={`pill intel-${knownLabel(item) === "known" ? "known" : knownLabel(item) === "unknown" ? "unknown" : "na"}`}>
          {knownLabel(item) === "known" ? "Known" : knownLabel(item) === "unknown" ? "Unknown" : "n/a"}
        </span>
      </div>
      <div className="finding-meta muted">
        <span>{itemTypeLabel(item)}</span>
        <span>·</span>
        <span>{vendorCategoryLine(item)}</span>
        {sizeBytes !== undefined ? (
          <>
            <span>·</span>
            <span>{formatBytes(sizeBytes)}</span>
          </>
        ) : null}
      </div>
      <p className="finding-why">{safetySummary(item)}</p>
      {block ? (
        <p className="finding-block muted">
          Not selectable:{" "}
          {block === "not_file"
            ? "only files can be quarantined"
            : block === "protected"
              ? "protected item"
              : block === "critical"
                ? "system-critical"
                : block === "unknown"
                  ? "unknown risk (enable Advanced mode)"
                  : block === "ask_user"
                    ? "needs review (enable Advanced mode)"
                    : "not cleanup-eligible"}
        </p>
      ) : null}
      {intel.warning_if_changed ? <p className="warn-inline">{intel.warning_if_changed}</p> : null}
    </article>
  );
}
