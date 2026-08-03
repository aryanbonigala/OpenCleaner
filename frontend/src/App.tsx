import { useCallback, useEffect, useState } from "react";
import {
  CleanupExecuteResult,
  CleanupPreviewResponse,
  ExplainResponse,
  PermissionMode,
  ScanItem,
  ScanResult,
  UserSettings,
  UserSettingsPatch,
  client,
  parseApiError,
} from "./api";
import { CleanupProgress } from "./components/CleanupProgress";
import { CleanupReview } from "./components/CleanupReview";
import { CleanupSummary } from "./components/CleanupSummary";
import { Dashboard } from "./components/Dashboard";
import { ErrorBanner } from "./components/ErrorBanner";
import { FindingDetails } from "./components/FindingDetails";
import { ProcessControlDashboard } from "./components/ProcessControlDashboard";
import { QuarantineManager, QuarantineEntry } from "./components/QuarantineManager";
import { ScanProgress } from "./components/ScanProgress";
import { ScanResults } from "./components/ScanResults";
import { Settings } from "./components/Settings";
import { defaultSelectedIds } from "./selection";

type View =
  | "processes"
  | "dashboard"
  | "results"
  | "cleanup_review"
  | "cleanup_summary"
  | "quarantine"
  | "settings";

export default function App() {
  const [view, setView] = useState<View>("processes");
  const [mode, setMode] = useState<PermissionMode>("read_only");
  const [userSettings, setUserSettings] = useState<UserSettings | null>(null);
  const [version, setVersion] = useState<string | null>(null);

  const [includeRecycleBin, setIncludeRecycleBin] = useState(false);
  const advancedMode = userSettings?.risk_visibility === "advanced";
  const canEmptyRecycle = userSettings?.cleanup_mode === "manual_permanent_delete_only";

  const [scan, setScan] = useState<ScanResult | null>(null);
  const [scanning, setScanning] = useState(false);
  const [cleaning, setCleaning] = useState(false);

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [showCleanupOnly, setShowCleanupOnly] = useState(true);
  const [confirmMedium, setConfirmMedium] = useState(false);

  const [preview, setPreview] = useState<CleanupPreviewResponse | null>(null);
  const [confirmCleanup, setConfirmCleanup] = useState(false);
  const [confirmPermanent, setConfirmPermanent] = useState(false);
  const [cleanupResult, setCleanupResult] = useState<CleanupExecuteResult | null>(null);

  const [detailItem, setDetailItem] = useState<ScanItem | null>(null);
  const [explain, setExplain] = useState<ExplainResponse | null>(null);
  const [explainLoading, setExplainLoading] = useState(false);

  const [quarantine, setQuarantine] = useState<QuarantineEntry[]>([]);
  const [quarantineLoading, setQuarantineLoading] = useState(false);
  const [restoreBusy, setRestoreBusy] = useState<string | null>(null);

  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadQuarantine = useCallback(async () => {
    setQuarantineLoading(true);
    try {
      const q = await client.quarantineList();
      setQuarantine((q.entries as QuarantineEntry[]) ?? []);
    } catch (e) {
      setError(parseApiError(e));
    } finally {
      setQuarantineLoading(false);
    }
  }, []);

  useEffect(() => {
    client
      .health()
      .then((h) => setVersion(h.version))
      .catch(() => undefined);
    client
      .getMode()
      .then((m) => setMode(m.mode))
      .catch(() => undefined);
    client
      .getSettings()
      .then((s) => setUserSettings(s))
      .catch(() => undefined);
    client
      .latest()
      .then((s) => {
        if (s) {
          setScan(s);
          setSelectedIds(defaultSelectedIds(s.items, false));
        }
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (view === "quarantine") void loadQuarantine();
  }, [view, loadQuarantine]);

  async function ensureAssistedMode(): Promise<boolean> {
    if (mode === "assisted") return true;
    setBusy(true);
    try {
      await client.setMode("assisted");
      setMode("assisted");
      return true;
    } catch (e) {
      setError(parseApiError(e));
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function runScan(afterView: View = "results") {
    setError(null);
    setScanning(true);
    setPreview(null);
    setCleanupResult(null);
    try {
      const s = await client.scan();
      setScan(s);
      setSelectedIds(defaultSelectedIds(s.items, advancedMode));
      setView(afterView);
    } catch (e) {
      setError(parseApiError(e));
    } finally {
      setScanning(false);
    }
  }

  function toggleSelection(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function selectAllEligible() {
    if (!scan) return;
    setSelectedIds(defaultSelectedIds(scan.items, advancedMode ?? false));
  }

  async function patchSettings(patch: UserSettingsPatch) {
    setBusy(true);
    setError(null);
    try {
      const next = await client.saveSettings(patch);
      setUserSettings(next);
      if (scan && next.risk_visibility === "basic") {
        setSelectedIds(defaultSelectedIds(scan.items, false));
      }
    } catch (e) {
      setError(parseApiError(e));
    } finally {
      setBusy(false);
    }
  }

  async function resetSettings() {
    setBusy(true);
    setError(null);
    try {
      const next = await client.resetSettings();
      setUserSettings(next);
      if (scan) setSelectedIds(defaultSelectedIds(scan.items, false));
      setConfirmMedium(false);
    } catch (e) {
      setError(parseApiError(e));
    } finally {
      setBusy(false);
    }
  }

  async function openItem(item: ScanItem) {
    setDetailItem(item);
    setExplain(null);
    setExplainLoading(true);
    try {
      const ex = await client.explain(item);
      setExplain(ex);
    } catch (e) {
      setError(parseApiError(e));
    } finally {
      setExplainLoading(false);
    }
  }

  async function runPreview() {
    if (!scan || selectedIds.size === 0) {
      setError("Select at least one file to preview cleanup.");
      return;
    }
    setError(null);
    if (!(await ensureAssistedMode())) return;
    setBusy(true);
    try {
      const p = await client.cleanupPreview(
        [...selectedIds],
        confirmMedium,
        canEmptyRecycle && includeRecycleBin
      );
      setPreview(p);
      setConfirmCleanup(false);
      setConfirmPermanent(false);
      setView("cleanup_review");
    } catch (e) {
      setError(parseApiError(e));
    } finally {
      setBusy(false);
    }
  }

  async function runExecute() {
    if (!preview) {
      setError("Run preview first.");
      return;
    }
    setError(null);
    setCleaning(true);
    try {
      const result = await client.cleanupExecute({
        preview_id: preview.preview_id,
        item_ids: [...selectedIds],
        confirm_medium_risk: confirmMedium,
        include_recycle_bin: canEmptyRecycle && includeRecycleBin,
        confirm_permanent_delete: confirmPermanent,
      });
      setCleanupResult(result);
      setPreview(null);
      setView("cleanup_summary");
      const latest = await client.latest();
      if (latest) setScan(latest);
      void loadQuarantine();
    } catch (e) {
      setError(parseApiError(e));
    } finally {
      setCleaning(false);
    }
  }

  async function restoreEntry(id: string) {
    setRestoreBusy(id);
    setError(null);
    try {
      await client.restore(id);
      await loadQuarantine();
    } catch (e) {
      setError(parseApiError(e));
    } finally {
      setRestoreBusy(null);
    }
  }

  async function changeMode(next: PermissionMode) {
    setBusy(true);
    setError(null);
    try {
      await client.setMode(next);
      setMode(next);
    } catch (e) {
      setError(parseApiError(e));
    } finally {
      setBusy(false);
    }
  }

  const navDisabled = scanning || cleaning;

  return (
    <div className="app flow-app">
      <header className="topbar">
        <div className="brand">
          <strong>OpenCleaner</strong>
          <span>Local review · quarantine-first cleanup</span>
        </div>
        <nav className="main-nav">
          <button type="button" disabled={navDisabled} className={view === "processes" ? "active" : ""} onClick={() => setView("processes")}>
            Process Control
          </button>
          <button type="button" disabled={navDisabled} className={view === "dashboard" ? "active" : ""} onClick={() => setView("dashboard")}>
            Dashboard
          </button>
          <button
            type="button"
            disabled={navDisabled || !scan}
            className={view === "results" ? "active" : ""}
            onClick={() => setView("results")}
          >
            Findings
          </button>
          <button type="button" disabled={navDisabled} className={view === "quarantine" ? "active" : ""} onClick={() => setView("quarantine")}>
            Quarantine
          </button>
          <button type="button" disabled={navDisabled} className={view === "settings" ? "active" : ""} onClick={() => setView("settings")}>
            Settings
          </button>
        </nav>
      </header>

      <ErrorBanner message={error} onDismiss={() => setError(null)} />

      {scanning ? <ScanProgress /> : null}
      {cleaning ? <CleanupProgress /> : null}

      <main className="flow-main">
        {view === "processes" ? (
          <ProcessControlDashboard scan={scan} scanning={scanning} onRunScan={() => void runScan("processes")} />
        ) : null}

        {view === "dashboard" ? (
          <Dashboard
            scan={scan}
            version={version}
            scanning={scanning}
            onRunScan={() => void runScan()}
            onViewResults={() => setView("results")}
            onQuarantine={() => setView("quarantine")}
          />
        ) : null}

        {view === "results" && scan ? (
          <div className="results-layout">
            <ScanResults
              scan={scan}
              selectedIds={selectedIds}
              advancedMode={advancedMode}
              onToggle={toggleSelection}
              onSelectAllEligible={selectAllEligible}
              onClearSelection={() => setSelectedIds(new Set())}
              onOpenItem={openItem}
              onPreviewCleanup={runPreview}
              showCleanupOnly={showCleanupOnly}
              onShowCleanupOnlyChange={setShowCleanupOnly}
              confirmMedium={confirmMedium}
              onConfirmMediumChange={setConfirmMedium}
              canEmptyRecycle={canEmptyRecycle}
              includeRecycleBin={includeRecycleBin}
              onIncludeRecycleBinChange={setIncludeRecycleBin}
              advancedRisk={advancedMode ?? false}
            />
            <FindingDetails item={detailItem} explain={explain} loading={explainLoading} />
          </div>
        ) : null}

        {view === "cleanup_review" && preview ? (
          <CleanupReview
            preview={preview}
            confirmCleanup={confirmCleanup}
            confirmMedium={confirmMedium}
            confirmPermanent={confirmPermanent}
            onConfirmCleanup={setConfirmCleanup}
            onConfirmMedium={setConfirmMedium}
            onConfirmPermanent={setConfirmPermanent}
            onBack={() => setView("results")}
            onExecute={runExecute}
          />
        ) : null}

        {view === "cleanup_summary" && cleanupResult?.summary ? (
          <CleanupSummary
            result={cleanupResult.summary}
            onViewQuarantine={() => setView("quarantine")}
            onDone={() => setView("dashboard")}
          />
        ) : null}

        {view === "quarantine" ? (
          <QuarantineManager
            entries={quarantine}
            loading={quarantineLoading}
            onRestore={restoreEntry}
            busyId={restoreBusy}
          />
        ) : null}

        {view === "settings" && userSettings ? (
          <Settings
            mode={mode}
            settings={userSettings}
            onModeChange={changeMode}
            onSaveSettings={patchSettings}
            onResetSettings={resetSettings}
            busy={busy}
          />
        ) : view === "settings" ? (
          <p className="muted" style={{ padding: 12 }}>
            Loading settings…
          </p>
        ) : null}
      </main>
    </div>
  );
}
