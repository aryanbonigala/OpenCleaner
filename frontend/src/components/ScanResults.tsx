import { useMemo, useState } from "react";
import type { ScanItem, ScanResult } from "../api";
import { itemBucket } from "../scanItem";
import { EmptyState } from "./EmptyState";
import { FindingCard } from "./FindingCard";

type Props = {
  scan: ScanResult;
  selectedIds: Set<string>;
  advancedMode: boolean;
  onToggle: (id: string) => void;
  onSelectAllEligible: () => void;
  onClearSelection: () => void;
  onOpenItem: (item: ScanItem) => void;
  onPreviewCleanup: () => void;
  showCleanupOnly: boolean;
  onShowCleanupOnlyChange: (v: boolean) => void;
  confirmMedium: boolean;
  onConfirmMediumChange: (v: boolean) => void;
  canEmptyRecycle: boolean;
  includeRecycleBin: boolean;
  onIncludeRecycleBinChange: (v: boolean) => void;
  advancedRisk: boolean;
};

export function ScanResults({
  scan,
  selectedIds,
  advancedMode,
  onToggle,
  onSelectAllEligible,
  onClearSelection,
  onOpenItem,
  onPreviewCleanup,
  showCleanupOnly,
  onShowCleanupOnlyChange,
  confirmMedium,
  onConfirmMediumChange,
  canEmptyRecycle,
  includeRecycleBin,
  onIncludeRecycleBinChange,
  advancedRisk,
}: Props) {
  const [filter, setFilter] = useState<"all" | "files" | "safe">("files");

  const items = useMemo(() => {
    let list = scan.items;
    if (showCleanupOnly) list = list.filter((i) => i.item_type === "file_or_folder");
    if (filter === "files") list = list.filter((i) => i.item_type === "file_or_folder");
    if (filter === "safe") list = list.filter((i) => itemBucket(i) === "safe_to_remove");
    if (!advancedRisk) {
      list = list.filter((i) => {
        const b = itemBucket(i);
        return b !== "unknown" && b !== "ask_user" && b !== "risky_system_critical";
      });
    }
    return list;
  }, [scan.items, filter, showCleanupOnly, advancedRisk]);

  const warnings = scan.summary.scanner_warnings ?? [];

  return (
    <div className="scan-results">
      {warnings.length > 0 ? (
        <div className="warn-box">
          <strong>Some scanners did not finish</strong>
          <ul>
            {warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="results-toolbar">
        <label className="muted">
          Show
          <select value={filter} onChange={(e) => setFilter(e.target.value as typeof filter)}>
            <option value="files">Files only</option>
            <option value="safe">Low-risk files</option>
            <option value="all">All item types</option>
          </select>
        </label>
        <label className="muted">
          <input
            type="checkbox"
            checked={showCleanupOnly}
            onChange={(e) => onShowCleanupOnlyChange(e.target.checked)}
          />{" "}
          Cleanup candidates only
        </label>
        {advancedRisk ? (
          <label className="muted">
            <input
              type="checkbox"
              checked={confirmMedium}
              onChange={(e) => onConfirmMediumChange(e.target.checked)}
            />{" "}
            Allow medium-risk files in preview
          </label>
        ) : null}
        {canEmptyRecycle ? (
          <label className="muted">
            <input
              type="checkbox"
              checked={includeRecycleBin}
              onChange={(e) => onIncludeRecycleBinChange(e.target.checked)}
            />{" "}
            Include Recycle Bin in preview (permanent; extra confirmation required)
          </label>
        ) : null}
        <button type="button" onClick={onSelectAllEligible}>
          Select eligible low-risk files
        </button>
        <button type="button" onClick={onClearSelection}>
          Clear selection
        </button>
        <button
          type="button"
          className="primary"
          disabled={selectedIds.size === 0}
          onClick={onPreviewCleanup}
        >
          Preview cleanup ({selectedIds.size})
        </button>
      </div>

      {items.length === 0 ? (
        <EmptyState
          title="No findings match this filter"
          description="Try another filter or run a new scan."
        />
      ) : (
        <div className="finding-list">
          {items.map((it) => (
            <FindingCard
              key={it.id}
              item={it}
              selected={selectedIds.has(it.id)}
              advancedMode={advancedMode}
              onToggle={onToggle}
              onOpen={onOpenItem}
            />
          ))}
        </div>
      )}
    </div>
  );
}
