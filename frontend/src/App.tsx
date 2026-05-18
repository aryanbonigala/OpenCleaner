import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ScanResult, ScanItem, client, ExplainResponse, PermissionMode, RiskBucket } from "./api";
import {
  getIntel,
  itemBucket,
  itemName,
  itemReasoning,
  itemTypeLabel,
  knownLabel,
  normalizedRisk,
  rankDeletion,
  rankGaming,
  rankMemory,
  vendorCategoryLine,
} from "./scanItem";

function matchesKnownFilter(it: ScanItem, f: "all" | "known" | "unknown"): boolean {
  if (f === "all") return true;
  const k = knownLabel(it);
  if (k === "n/a") return true;
  return f === "known" ? k === "known" : k === "unknown";
}

function matchesRiskFilter(it: ScanItem, f: string): boolean {
  if (f === "all") return true;
  return normalizedRisk(it) === f;
}

function matchesGamingFilter(it: ScanItem, f: string): boolean {
  if (f === "all") return true;
  const intel = getIntel(it);
  const g = (intel.gaming_impact || "").toLowerCase();
  if (g) {
    if (f === "very_high" && (g === "very_high" || g === "critical")) return true;
    return g === f;
  }
  const r = rankGaming(it) ?? 0;
  if (f === "critical" || f === "very_high") return r >= 75;
  if (f === "high") return r >= 55 && r < 75;
  if (f === "medium") return r >= 35 && r < 55;
  if (f === "variable") return r >= 25 && r < 70;
  if (f === "low") return r < 35;
  return true;
}

function matchesStartupFilter(it: ScanItem, f: string): boolean {
  if (f === "all") return true;
  const intel = getIntel(it);
  const s = (intel.startup_impact || "").toLowerCase();
  if (s) return s === f || (f === "boot-critical" && s.includes("boot"));
  const r = it.metrics?.rank_startup_impact ?? 0;
  if (f === "high") return r >= 55;
  if (f === "medium") return r >= 30 && r < 55;
  if (f === "low") return r < 30;
  return true;
}

type SortKey =
  | "name"
  | "item_type"
  | "bucket"
  | "rank_memory_impact"
  | "rank_gaming_impact"
  | "rank_deletion_risk";

function knownPill(it: ScanItem) {
  const k = knownLabel(it);
  if (k === "n/a") {
    return (
      <span className="pill intel-na" title="Intelligence DB does not classify this item type">
        n/a
      </span>
    );
  }
  if (k === "known") return <span className="pill intel-known">Known</span>;
  return <span className="pill intel-unknown">Unknown</span>;
}

function bucketPill(bucket: RiskBucket) {
  const risky = bucket === "risky_system_critical";
  const safe = bucket === "safe_to_remove" || bucket === "probably_safe";
  const cls = risky ? "pill risky" : safe ? "pill safe" : "pill";
  return <span className={cls}>{bucket.replaceAll("_", " ")}</span>;
}

export default function App() {
  const [mode, setMode] = useState<PermissionMode>("read_only");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scan, setScan] = useState<ScanResult | null>(null);
  const [selected, setSelected] = useState<ScanItem | null>(null);
  const [explain, setExplain] = useState<ExplainResponse | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("rank_memory_impact");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [metrics, setMetrics] = useState<{ cpu: number; mem: number } | null>(null);
  const [confirmMedium, setConfirmMedium] = useState(false);
  const [recycleBin, setRecycleBin] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Record<string, boolean>>({});
  const [safety, setSafety] = useState<Awaited<ReturnType<typeof client.safetySummary>> | null>(null);
  const [perfPreview, setPerfPreview] = useState<Record<string, unknown> | null>(null);
  const [perfPreset, setPerfPreset] = useState<string | null>(null);
  const [perfTargets, setPerfTargets] = useState("");
  const [perfConfirm, setPerfConfirm] = useState(false);
  const [filterKnown, setFilterKnown] = useState<"all" | "known" | "unknown">("all");
  const [filterGaming, setFilterGaming] = useState<string>("all");
  const [filterStartup, setFilterStartup] = useState<string>("all");
  const [filterRisk, setFilterRisk] = useState<string>("all");

  useEffect(() => {
    client
      .getMode()
      .then((m) => setMode(m.mode))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    client
      .latest()
      .then((s) => setScan(s))
      .catch(() => undefined);
  }, []);

  async function loadSafety() {
    try {
      const s = await client.safetySummary();
      setSafety(s);
    } catch {
      setSafety(null);
    }
  }

  useEffect(() => {
    void loadSafety();
    const t = window.setInterval(() => void loadSafety(), 8000);
    return () => window.clearInterval(t);
  }, [mode, scan?.summary.scan_id]);

  useEffect(() => {
    const id = window.setInterval(() => {
      client
        .metrics()
        .then((m) => setMetrics({ cpu: m.cpu_percent, mem: m.memory.percent }))
        .catch(() => undefined);
    }, 1500);
    client
      .metrics()
      .then((m) => setMetrics({ cpu: m.cpu_percent, mem: m.memory.percent }))
      .catch(() => undefined);
    return () => window.clearInterval(id);
  }, []);

  const sortedItems = useMemo(() => {
    const items = scan?.items ?? [];
    const dir = sortDir === "asc" ? 1 : -1;
    const val = (it: ScanItem) => {
      switch (sortKey) {
        case "name":
          return itemName(it).toLowerCase();
        case "item_type":
          return it.item_type;
        case "bucket":
          return itemBucket(it);
        case "rank_memory_impact":
          return rankMemory(it) ?? 0;
        case "rank_gaming_impact":
          return rankGaming(it) ?? 0;
        case "rank_deletion_risk":
          return rankDeletion(it) ?? 0;
        default:
          return 0;
      }
    };
    return [...items].sort((a, b) => {
      const va = val(a);
      const vb = val(b);
      if (typeof va === "string" && typeof vb === "string") {
        return va.localeCompare(vb) * dir;
      }
      return ((va as number) - (vb as number)) * dir;
    });
  }, [scan, sortDir, sortKey]);

  const displayedItems = useMemo(() => {
    return sortedItems.filter((it) => {
      if (!matchesKnownFilter(it, filterKnown)) return false;
      if (!matchesGamingFilter(it, filterGaming)) return false;
      if (!matchesStartupFilter(it, filterStartup)) return false;
      if (!matchesRiskFilter(it, filterRisk)) return false;
      return true;
    });
  }, [sortedItems, filterKnown, filterGaming, filterStartup, filterRisk]);

  const bucketChart = useMemo(() => {
    const b = scan?.summary.buckets ?? {};
    return Object.entries(b).map(([name, value]) => ({ name, value }));
  }, [scan]);

  async function refreshMode(next: PermissionMode) {
    setBusy(true);
    setError(null);
    try {
      await client.setMode(next);
      setMode(next);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function runScan() {
    setBusy(true);
    setError(null);
    try {
      const s = await client.scan();
      setScan(s);
      void loadSafety();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function runExplain(it: ScanItem) {
    setSelected(it);
    setBusy(true);
    setError(null);
    try {
      const ex = await client.explain(it);
      setExplain(ex);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function runCleanup() {
    const ids = Object.entries(selectedIds)
      .filter(([, v]) => v)
      .map(([k]) => k);
    if (ids.length === 0) {
      setError("Select at least one item (checkbox) to clean.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await client.cleanup(ids, confirmMedium, recycleBin);
      const s = await client.latest();
      setScan(s);
      void loadSafety();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function restoreFirst() {
    setBusy(true);
    setError(null);
    try {
      const q = await client.quarantineList();
      const entries = q.entries as Array<{ id: string }>;
      if (!entries.length) {
        setError("Quarantine is empty.");
      } else {
        await client.restore(entries[0].id);
      }
      void loadSafety();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function runPerfPreview(preset: string) {
    setBusy(true);
    setError(null);
    setPerfConfirm(false);
    try {
      const targets = perfTargets
        .split(/[\s,]+/)
        .map((x) => x.trim())
        .filter(Boolean);
      const prev = await client.perfPreview(preset, targets);
      setPerfPreview(prev);
      setPerfPreset(preset);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function applyPerf() {
    if (!perfPreset || !perfPreview) {
      setError("Run a preview for a preset first.");
      return;
    }
    if (!perfConfirm) {
      setError("Check the box confirming you reviewed the preview and accept suspending those processes.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const targets = perfTargets
        .split(/[\s,]+/)
        .map((x) => x.trim())
        .filter(Boolean);
      await client.perfStart(perfPreset, targets, true);
      void loadSafety();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function stopPerf() {
    setBusy(true);
    setError(null);
    try {
      await client.perfStop();
      void loadSafety();
      setPerfPreview(null);
      setPerfPreset(null);
      setPerfConfirm(false);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  function toggleSort(k: SortKey) {
    if (sortKey === k) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(k);
      setSortDir("desc");
    }
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <strong>OpenCleaner AI</strong>
          <span>Local-first optimizer — transparency over speed</span>
        </div>
        <div className="controls">
          <label className="muted">
            Mode
            <select
              value={mode}
              disabled={busy}
              onChange={(e) => refreshMode(e.target.value as PermissionMode)}
              style={{ marginLeft: 8 }}
            >
              <option value="read_only">Read-only (scan + explain)</option>
              <option value="assisted">Assisted cleanup (quarantine)</option>
              <option value="performance">Performance / gaming</option>
            </select>
          </label>
          <button className="primary" disabled={busy} onClick={runScan}>
            Run scan
          </button>
          <a href={client.exportReportUrl("md")} target="_blank" rel="noreferrer">
            <button disabled={!scan}>Export MD</button>
          </a>
          <a href={client.exportReportUrl("json")} target="_blank" rel="noreferrer">
            <button disabled={!scan}>Export JSON</button>
          </a>
        </div>
      </header>

      <main className="layout">
        <section className="panel">
          <div className="panel-header">
            <h2>System inventory</h2>
            <span className="muted">
              {scan
                ? `${displayedItems.length} shown / ${scan.summary.items_count} items — ${scan.summary.platform}`
                : "No scan yet"}
            </span>
          </div>
          <div
            className="inventory-filters"
            style={{
              padding: "8px 12px",
              display: "flex",
              flexWrap: "wrap",
              gap: 12,
              alignItems: "center",
              borderBottom: "1px solid var(--border)",
            }}
          >
            <span className="muted" style={{ fontSize: 12 }}>
              Filters
            </span>
            <label className="muted" style={{ fontSize: 12 }}>
              Known
              <select
                value={filterKnown}
                onChange={(e) => setFilterKnown(e.target.value as "all" | "known" | "unknown")}
                style={{ marginLeft: 6 }}
              >
                <option value="all">All</option>
                <option value="known">Known only</option>
                <option value="unknown">Unknown only</option>
              </select>
            </label>
            <label className="muted" style={{ fontSize: 12 }}>
              Gaming (intel / rank)
              <select value={filterGaming} onChange={(e) => setFilterGaming(e.target.value)} style={{ marginLeft: 6 }}>
                <option value="all">All</option>
                <option value="critical">critical</option>
                <option value="high">high</option>
                <option value="medium">medium</option>
                <option value="low">low</option>
                <option value="variable">variable</option>
              </select>
            </label>
            <label className="muted" style={{ fontSize: 12 }}>
              Startup (intel / rank)
              <select value={filterStartup} onChange={(e) => setFilterStartup(e.target.value)} style={{ marginLeft: 6 }}>
                <option value="all">All</option>
                <option value="boot-critical">boot-critical</option>
                <option value="high">high</option>
                <option value="medium">medium</option>
                <option value="low">low</option>
              </select>
            </label>
            <label className="muted" style={{ fontSize: 12 }}>
              Risk (intel / bucket)
              <select value={filterRisk} onChange={(e) => setFilterRisk(e.target.value)} style={{ marginLeft: 6 }}>
                <option value="all">All</option>
                <option value="critical">critical</option>
                <option value="high">high</option>
                <option value="medium">medium</option>
                <option value="low">low</option>
                <option value="unknown">unknown</option>
                <option value="other">other</option>
              </select>
            </label>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th></th>
                  <th>Intel</th>
                  <th onClick={() => toggleSort("name")}>Name</th>
                  <th>Vendor / category</th>
                  <th onClick={() => toggleSort("item_type")}>Type</th>
                  <th onClick={() => toggleSort("bucket")}>Bucket</th>
                  <th onClick={() => toggleSort("rank_memory_impact")}>RAM Δ</th>
                  <th onClick={() => toggleSort("rank_gaming_impact")}>Gaming</th>
                  <th onClick={() => toggleSort("rank_deletion_risk")}>Risk</th>
                  <th>Why flagged</th>
                </tr>
              </thead>
              <tbody>
                {displayedItems.map((it) => {
                  const intel = getIntel(it);
                  const unkSvc = it.item_type === "service" && knownLabel(it) === "unknown";
                  const vendorLine = vendorCategoryLine(it);
                  return (
                    <tr
                      key={it.id}
                      className={unkSvc ? "row-unknown-svc" : undefined}
                      onDoubleClick={() => runExplain(it)}
                    >
                      <td>
                        {it.item_type === "file_or_folder" ? (
                          <input
                            type="checkbox"
                            checked={!!selectedIds[it.id]}
                            onChange={(e) =>
                              setSelectedIds((s) => ({ ...s, [it.id]: e.target.checked }))
                            }
                          />
                        ) : (
                          <span className="muted">—</span>
                        )}
                      </td>
                      <td>{knownPill(it)}</td>
                      <td>
                        <button
                          style={{
                            background: "transparent",
                            border: "none",
                            padding: 0,
                            color: "inherit",
                          }}
                          onClick={() => runExplain(it)}
                        >
                          {itemName(it)}
                        </button>
                        {unkSvc ? (
                          <div className="warn-inline" style={{ marginTop: 4 }}>
                            Unknown service — identify in Services console before disabling.
                          </div>
                        ) : null}
                        {it.path ? (
                          <div className="muted" style={{ marginTop: 4 }}>
                            {it.path}
                          </div>
                        ) : null}
                      </td>
                      <td>
                        <span style={{ fontSize: 12 }}>{vendorLine}</span>
                        {intel.gaming_impact ? (
                          <div className="muted" style={{ fontSize: 11 }}>
                            gaming: {intel.gaming_impact}
                          </div>
                        ) : null}
                      </td>
                      <td>{itemTypeLabel(it)}</td>
                      <td>{bucketPill(itemBucket(it))}</td>
                      <td>{rankMemory(it)?.toFixed(0) ?? "—"}</td>
                      <td>{rankGaming(it)?.toFixed(0) ?? "—"}</td>
                      <td>{rankDeletion(it)?.toFixed(0) ?? "—"}</td>
                      <td>{itemReasoning(it)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="actions">
            {mode === "assisted" ? (
              <>
                <div className="warn-box" style={{ flex: "1 1 100%" }}>
                  <strong>Assisted cleanup</strong> moves selected files to a local quarantine folder first (not immediate
                  deletion). Core system paths are blocked. Medium-risk items require the checkbox below. Machine learning
                  does not delete anything; only you confirm actions.
                </div>
                <label className="muted">
                  <input
                    type="checkbox"
                    checked={confirmMedium}
                    onChange={(e) => setConfirmMedium(e.target.checked)}
                  />{" "}
                  Allow medium-risk cleanup paths (still no system dirs)
                </label>
                <label className="muted">
                  <input
                    type="checkbox"
                    checked={recycleBin}
                    onChange={(e) => setRecycleBin(e.target.checked)}
                  />{" "}
                  Empty Recycle Bin (Windows)
                </label>
                <button className="danger" disabled={busy} onClick={runCleanup}>
                  Quarantine selected files
                </button>
                <button disabled={busy} onClick={restoreFirst}>
                  Restore latest quarantine entry
                </button>
              </>
            ) : null}

            {mode === "performance" ? (
              <>
                <div className="warn-box" style={{ flex: "1 1 100%" }}>
                  <strong>Performance mode</strong> can <em>suspend</em> eligible background processes (never browsers or
                  shells unless you list them explicitly below). You must <strong>Preview</strong> first, then apply with
                  confirmation. Stop session resumes suspended PIDs. This is not a substitute for closing games properly,
                  and some power profile steps may need administrator rights on Windows.
                </div>
                <label className="muted" style={{ flex: "1 1 100%" }}>
                  Extra process basenames (optional, comma-separated), e.g. <code>chrome.exe</code>,{" "}
                  <code>spotify.exe</code>
                  <input
                    type="text"
                    value={perfTargets}
                    onChange={(e) => setPerfTargets(e.target.value)}
                    placeholder="chrome.exe, Spotify.exe"
                    style={{
                      display: "block",
                      width: "100%",
                      marginTop: 6,
                      padding: 8,
                      borderRadius: 8,
                      border: "1px solid var(--border)",
                      background: "var(--panel)",
                      color: "var(--text)",
                    }}
                  />
                </label>
                <button disabled={busy} onClick={() => runPerfPreview("max_fps")}>
                  Preview: Max FPS
                </button>
                <button disabled={busy} onClick={() => runPerfPreview("min_ram")}>
                  Preview: Min RAM
                </button>
                <button disabled={busy} onClick={() => runPerfPreview("streaming")}>
                  Preview: Streaming
                </button>
                <button disabled={busy} onClick={() => runPerfPreview("battery_saver")}>
                  Preview: Battery saver
                </button>
                {perfPreview ? (
                  <div className="pre-small" style={{ flex: "1 1 100%" }}>
                    {String(perfPreview["disclaimer"] ?? "")}
                    {"\n"}
                    would_suspend: {String(perfPreview["would_suspend_count"] ?? "?")}, protected_skipped:{" "}
                    {String(perfPreview["skipped_protected_count"] ?? "?")}
                    {"\n"}
                    {JSON.stringify(perfPreview["would_suspend"], null, 0).slice(0, 2000)}
                  </div>
                ) : null}
                <label className="muted">
                  <input
                    type="checkbox"
                    checked={perfConfirm}
                    onChange={(e) => setPerfConfirm(e.target.checked)}
                  />{" "}
                  I reviewed the preview and accept applying suspends for the listed processes.
                </label>
                <button className="danger" disabled={busy || !perfPreview} onClick={() => void applyPerf()}>
                  Apply previewed plan
                </button>
                <button className="danger" disabled={busy} onClick={() => void stopPerf()}>
                  Stop / rollback session
                </button>
              </>
            ) : null}
          </div>
          <div className="footer-note">
            Double-click a row (or click the name) for <strong>Explain This</strong>. Sort columns by clicking headers.
            Read-only mode never mutates disk or processes. Assisted cleanup uses quarantine. Performance mode requires
            preview plus explicit confirmation before suspend.
          </div>
        </section>

        <aside className="side">
          <section className="panel metrics">
            <div className="panel-header">
              <h2>Safety Center</h2>
              <span className="muted">local-only</span>
            </div>
            <div className="safety-grid" style={{ padding: "10px 12px" }}>
              {safety ? (
                <>
                  <dl>
                    <dt>Mode</dt>
                    <dd>{safety.permission_mode}</dd>
                    <dt>Quarantine (active)</dt>
                    <dd>
                      {String((safety.quarantine as { entries_active?: number }).entries_active ?? "—")} entries,{" "}
                      {String((safety.quarantine as { active_mb?: number }).active_mb ?? "—")} MB tracked
                    </dd>
                    <dt>Rollback session</dt>
                    <dd>
                      {safety.performance_session && (safety.performance_session as { active?: boolean }).active
                        ? `active (${String((safety.performance_session as { suspended_count?: number }).suspended_count ?? "?")} suspended)`
                        : "none"}
                    </dd>
                    <dt>Protected patterns (registry)</dt>
                    <dd>{safety.protected_registry_rules}</dd>
                    <dt>Running proc. matching guards</dt>
                    <dd>{safety.running_processes_matching_protection}</dd>
                    <dt>Telemetry default</dt>
                    <dd>{safety.telemetry}</dd>
                  </dl>
                  <div className="muted" style={{ fontSize: 11 }}>
                    Recent actions (audit log):{" "}
                    {(safety.recent_actions as object[]).length
                      ? (safety.recent_actions as { action: string }[])
                          .slice(0, 4)
                          .map((a) => a.action)
                          .join(", ")
                      : "none"}
                  </div>
                </>
              ) : (
                <span className="muted">Loading safety summary…</span>
              )}
            </div>
          </section>

          <section className="panel metrics">
            <div className="panel-header">
              <h2>Resource snapshot</h2>
              <span className="muted">updates ~1.5s</span>
            </div>
            <div className="metric-grid">
              <div className="card">
                <div className="muted">CPU</div>
                <div style={{ fontSize: 22 }}>{metrics ? `${metrics.cpu.toFixed(1)}%` : "—"}</div>
              </div>
              <div className="card">
                <div className="muted">RAM used</div>
                <div style={{ fontSize: 22 }}>{metrics ? `${metrics.mem.toFixed(1)}%` : "—"}</div>
              </div>
            </div>
            <div style={{ height: 180, marginTop: 10 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={bucketChart}>
                  <XAxis dataKey="name" tick={{ fill: "#8b98a8", fontSize: 10 }} />
                  <YAxis tick={{ fill: "#8b98a8", fontSize: 10 }} />
                  <Tooltip
                    contentStyle={{ background: "#141a22", border: "1px solid #223042" }}
                    labelStyle={{ color: "#e8f0ff" }}
                  />
                  <Bar dataKey="value" fill="#6dd3ff" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </section>

          <section className="panel">
            <div className="panel-header">
              <h2>Explain This</h2>
              <span className="muted">{selected ? itemName(selected) : "Select an item"}</span>
            </div>
            <div className="explain">
              {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}
              {!explain ? (
                <p className="muted">Pick an item to see plain-English reasoning (local rules + local ML ranking).</p>
              ) : (
                <>
                  <h3>What it does</h3>
                  <p>{explain.what_it_does}</p>
                  <h3>Importance</h3>
                  <p>{explain.importance}</p>
                  <h3>Installer guess</h3>
                  <p>{explain.installer_guess}</p>
                  <h3>Gaming</h3>
                  <p>{explain.gaming_impact}</p>
                  <h3>Startup</h3>
                  <p>{explain.startup_impact}</p>
                  <h3>Safe to remove/disable</h3>
                  <p>{explain.safe_to_disable_or_remove}</p>
                  <h3>What could break</h3>
                  <p>{explain.what_could_break}</p>
                  <h3>Local ML note</h3>
                  <p>{explain.local_ml_note}</p>
                  <div className="actions" style={{ border: "none", paddingLeft: 0 }}>
                    <button
                      disabled={!selected || busy}
                      onClick={async () => {
                        if (!selected) return;
                        setBusy(true);
                        try {
                          await client.feedback(selected, "keep");
                        } catch (e) {
                          setError(String(e));
                        } finally {
                          setBusy(false);
                        }
                      }}
                    >
                      Learn: prefer keep
                    </button>
                    <button
                      disabled={!selected || busy}
                      onClick={async () => {
                        if (!selected) return;
                        setBusy(true);
                        try {
                          await client.feedback(selected, "remove");
                        } catch (e) {
                          setError(String(e));
                        } finally {
                          setBusy(false);
                        }
                      }}
                    >
                      Learn: prefer remove
                    </button>
                  </div>
                </>
              )}
            </div>
          </section>
        </aside>
      </main>
    </div>
  );
}
