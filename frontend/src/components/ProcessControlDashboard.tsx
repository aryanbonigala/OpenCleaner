import { useCallback, useEffect, useState } from "react";
import type { ProcessDetailResponse, ProcessInventoryResponse, ProcessPreviewEndResponse, ScanItem, ScanResult } from "../api";
import { client, parseApiError } from "../api";
import { canPreviewProcess } from "../processSelection";
import { pidOf } from "../processItem";
import { EmptyState } from "./EmptyState";
import { ProcessCategorySummary } from "./ProcessCategorySummary";
import { ProcessControlDetails } from "./ProcessControlDetails";
import { ProcessControlTable } from "./ProcessControlTable";
import { ProcessPreviewPanel } from "./ProcessPreviewPanel";

type Props = {
  scan: ScanResult | null;
  scanning: boolean;
  onRunScan: () => void;
};

export function ProcessControlDashboard({ scan, scanning, onRunScan }: Props) {
  const [inventory, setInventory] = useState<ProcessInventoryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [selectedItem, setSelectedItem] = useState<ScanItem | null>(null);
  const [detail, setDetail] = useState<ProcessDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [confirmExplicitSelection, setConfirmExplicitSelection] = useState(false);

  const [previewResult, setPreviewResult] = useState<ProcessPreviewEndResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const loadInventory = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await client.getProcesses();
      setInventory(res);
    } catch (e) {
      setError(parseApiError(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadInventory();
    // Reload whenever a new scan lands (App.tsx's `scan` reference changes).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scan]);

  useEffect(() => {
    if (!inventory) return;
    setSelectedIds((prev) => {
      const next = new Set<string>();
      for (const id of prev) {
        const it = inventory.items.find((i) => i.id === id);
        if (it && canPreviewProcess(it, confirmExplicitSelection)) next.add(id);
      }
      return next;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [confirmExplicitSelection]);

  function toggleSelection(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function openItem(item: ScanItem) {
    setSelectedItem(item);
    setDetail(null);
    const pid = pidOf(item);
    if (item.item_type !== "process" || pid === null) return;
    setDetailLoading(true);
    try {
      const res = await client.getProcessByPid(pid);
      setDetail(res);
    } catch (e) {
      setError(parseApiError(e));
    } finally {
      setDetailLoading(false);
    }
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

  const noScan = !loading && inventory && !!inventory.message;

  return (
    <div className="process-dashboard">
      <div className="panel-header process-dashboard-header">
        <div>
          <h2>Process Control</h2>
          <p className="muted">Understand what&rsquo;s running and what OpenCleaner will refuse to touch.</p>
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

      {error ? <p className="warn-inline" style={{ padding: "0 12px" }}>{error}</p> : null}

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
          <ProcessCategorySummary counts={inventory.counts} />
          <div className="results-layout process-dashboard-layout">
            <div className="process-dashboard-main">
              <ProcessControlTable
                items={inventory.items}
                selectedIds={selectedIds}
                confirmExplicitSelection={confirmExplicitSelection}
                onToggle={toggleSelection}
                onOpen={(item) => void openItem(item)}
                openId={selectedItem?.id}
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
            <ProcessControlDetails item={selectedItem} detail={detail} loading={detailLoading} />
          </div>
        </>
      )}
    </div>
  );
}
