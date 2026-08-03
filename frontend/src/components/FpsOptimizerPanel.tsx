import { useEffect, useState } from "react";
import type { ProcessPreviewEndResponse, ScanItem, ScanResult } from "../api";
import { client, parseApiError } from "../api";
import { PREVIEW_ONLY_NOTICE } from "../copy";
import { canPreviewProcess } from "../processSelection";
import { useProcessInventory } from "../useProcessInventory";
import { EmptyState } from "./EmptyState";
import { FpsCandidateList } from "./FpsCandidateList";
import { FpsImpactSummary } from "./FpsImpactSummary";
import { ProcessPreviewPanel } from "./ProcessPreviewPanel";
import { SurfaceCrossLinks, type Surface } from "./SurfaceCrossLinks";

type Props = {
  scan: ScanResult | null;
  scanning: boolean;
  onRunScan: () => void;
  onNavigate?: (target: Surface) => void;
};

function isFpsCandidate(it: ScanItem): boolean {
  return it.item_type === "process" && it.process_control.category === "gaming_fps_impact";
}

export function FpsOptimizerPanel({ scan, scanning, onRunScan, onNavigate }: Props) {
  const { inventory, loading, error, noScan, reload: loadInventory } = useProcessInventory(scan);

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [confirmExplicitSelection, setConfirmExplicitSelection] = useState(false);

  const [previewResult, setPreviewResult] = useState<ProcessPreviewEndResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const candidates: ScanItem[] = inventory?.items.filter(isFpsCandidate) ?? [];

  useEffect(() => {
    setSelectedIds((prev) => {
      const next = new Set<string>();
      for (const id of prev) {
        const it = candidates.find((i) => i.id === id);
        if (it && canPreviewProcess(it, confirmExplicitSelection)) next.add(id);
      }
      return next;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [confirmExplicitSelection, inventory]);

  function toggleSelection(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function runPreview() {
    if (selectedIds.size === 0) return;
    setPreviewLoading(true);
    setPreviewError(null);
    try {
      const res = await client.previewEndProcesses([...selectedIds], confirmExplicitSelection);
      setPreviewResult(res);
    } catch (e) {
      setPreviewError(parseApiError(e));
    } finally {
      setPreviewLoading(false);
    }
  }

  const selectableCount = candidates.filter((it) => canPreviewProcess(it, confirmExplicitSelection)).length;
  const memoryMb = candidates.reduce((sum, it) => sum + (it.metrics?.memory_mb ?? 0), 0);
  const policyCounts: Record<string, number> = {};
  for (const it of candidates) {
    const key = it.process_control.action_policy;
    policyCounts[key] = (policyCounts[key] ?? 0) + 1;
  }

  return (
    <div className="process-dashboard">
      <div className="panel-header process-dashboard-header">
        <div>
          <h2>Preview gaming session</h2>
          <p className="muted">
            Reversible suspend candidates from your process inventory that may affect FPS — overlays, memory,
            CPU, browsers, sync tools, launchers, and background helpers.
          </p>
          <p className="muted">
            OpenCleaner will not touch essential, unknown, security, driver, browser, or shell processes
            automatically.
          </p>
          <p className="muted">{PREVIEW_ONLY_NOTICE}</p>
          <SurfaceCrossLinks current="fps" onNavigate={onNavigate} />
        </div>
        <div className="dashboard-actions">
          <button type="button" disabled={loading} onClick={() => void loadInventory()}>
            Refresh from latest scan
          </button>
          <button type="button" className="primary" disabled={scanning} onClick={onRunScan}>
            {scanning ? "Scanning…" : "Run scan"}
          </button>
        </div>
      </div>

      {error ? (
        <p className="warn-inline" style={{ padding: "0 12px" }}>
          {error}
        </p>
      ) : null}

      {noScan ? (
        <EmptyState
          title="Run a scan first to build a process inventory."
          description={inventory?.message ?? "No scan available yet."}
          action={
            <button type="button" className="primary" disabled={scanning} onClick={onRunScan}>
              {scanning ? "Scanning…" : "Run scan"}
            </button>
          }
        />
      ) : !inventory || loading ? (
        <p className="muted" style={{ padding: 12 }}>
          Loading process inventory…
        </p>
      ) : (
        <>
          <FpsImpactSummary
            totalInventoryCount={inventory.items_count}
            candidateCount={candidates.length}
            selectableCount={selectableCount}
            memoryMb={memoryMb}
            policyCounts={policyCounts}
          />
          <div className="process-dashboard-layout process-dashboard-main">
            <FpsCandidateList
              items={candidates}
              selectedIds={selectedIds}
              confirmExplicitSelection={confirmExplicitSelection}
              onToggle={toggleSelection}
            />
            <ProcessPreviewPanel
              selectedCount={selectedIds.size}
              confirmExplicitSelection={confirmExplicitSelection}
              onConfirmExplicitSelectionChange={setConfirmExplicitSelection}
              onRunPreview={() => void runPreview()}
              loading={previewLoading}
              result={previewResult}
            />
            {previewError ? <p className="warn-inline">{previewError}</p> : null}
          </div>
        </>
      )}
    </div>
  );
}
