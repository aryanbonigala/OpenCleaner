import type {
  CleanupMode,
  LoggingMode,
  PermissionMode,
  QuarantineRetention,
  RiskVisibility,
  UserSettings,
  UserSettingsPatch,
} from "../api";

type Props = {
  mode: PermissionMode;
  settings: UserSettings;
  busy: boolean;
  onModeChange: (m: PermissionMode) => void;
  onSaveSettings: (patch: UserSettingsPatch) => void;
  onResetSettings: () => void;
};

export function Settings({
  mode,
  settings,
  busy,
  onModeChange,
  onSaveSettings,
  onResetSettings,
}: Props) {
  const advanced = settings.risk_visibility === "advanced";
  const allowsPermanent = settings.cleanup_mode === "manual_permanent_delete_only";

  return (
    <div className="settings panel">
      <div className="panel-header">
        <h2>Settings</h2>
        <button type="button" className="secondary" disabled={busy} onClick={onResetSettings}>
          Reset to safe defaults
        </button>
      </div>
      <div className="settings-body">
        <section className="settings-section">
          <h3>Permission mode</h3>
          <label>
            Active mode
            <select
              value={mode}
              disabled={busy}
              onChange={(e) => onModeChange(e.target.value as PermissionMode)}
            >
              <option value="read_only">Read-only — scan and explain only</option>
              <option value="assisted">Assisted — quarantine selected files</option>
              <option value="performance">Performance — preview suspend (advanced)</option>
            </select>
          </label>
          <p className="muted">Assisted mode is required before quarantining files.</p>
        </section>

        <section className="settings-section">
          <h3>Cleanup mode</h3>
          <label>
            <input
              type="radio"
              name="cleanup_mode"
              checked={settings.cleanup_mode === "quarantine_only"}
              disabled={busy}
              onChange={() => onSaveSettings({ cleanup_mode: "quarantine_only" as CleanupMode })}
            />{" "}
            Quarantine only (default) — files move to local quarantine; no automatic permanent delete
          </label>
          <label>
            <input
              type="radio"
              name="cleanup_mode"
              checked={settings.cleanup_mode === "manual_permanent_delete_only"}
              disabled={busy}
              onChange={() =>
                onSaveSettings({ cleanup_mode: "manual_permanent_delete_only" as CleanupMode })
              }
            />{" "}
            Manual permanent delete only — allows optional Recycle Bin emptying after explicit confirmation
          </label>
          {!allowsPermanent ? (
            <p className="muted">Recycle Bin emptying is unavailable in quarantine-only mode.</p>
          ) : null}
        </section>

        <section className="settings-section">
          <h3>Risk visibility</h3>
          <label>
            <input
              type="radio"
              name="risk_visibility"
              checked={settings.risk_visibility === "basic"}
              disabled={busy}
              onChange={() => onSaveSettings({ risk_visibility: "basic" as RiskVisibility })}
            />{" "}
            Basic (default) — only low-risk cleanup candidates are easy to select; unknown items stay hidden
          </label>
          <label>
            <input
              type="radio"
              name="risk_visibility"
              checked={settings.risk_visibility === "advanced"}
              disabled={busy}
              onChange={() => onSaveSettings({ risk_visibility: "advanced" as RiskVisibility })}
            />{" "}
            Advanced — show unknown and review-needed items; you must still confirm each cleanup
          </label>
          {advanced ? (
            <div className="warn-box">
              <strong>Advanced visibility is on</strong>
              <p>
                You can see and manually select higher-risk items. OpenCleaner will never auto-select unknown,
                protected, or critical paths. Core safety rules still apply.
              </p>
            </div>
          ) : null}
        </section>

        <section className="settings-section">
          <h3>Scanner groups</h3>
          <p className="muted">Disable groups you do not want in the next scan. At least one should stay enabled.</p>
          {(
            [
              ["files", "Files — temp, downloads, duplicates, large files"],
              ["browser", "Browser — profile size scans"],
              ["startup", "Startup — services and startup entries"],
              ["tasks", "Tasks — scheduled tasks"],
              ["performance", "Performance — running processes"],
            ] as const
          ).map(([key, label]) => (
            <label key={key}>
              <input
                type="checkbox"
                checked={settings.scanner_toggles[key]}
                disabled={busy}
                onChange={(e) =>
                  onSaveSettings({
                    scanner_toggles: { ...settings.scanner_toggles, [key]: e.target.checked },
                  })
                }
              />{" "}
              {label}
            </label>
          ))}
        </section>

        <section className="settings-section">
          <h3>Quarantine retention</h3>
          <label>
            Policy
            <select
              value={settings.quarantine_retention}
              disabled={busy}
              onChange={(e) =>
                onSaveSettings({ quarantine_retention: e.target.value as QuarantineRetention })
              }
            >
              <option value="manual_only">Manual only — never auto-delete quarantined files</option>
              <option value="7_days">7 days — purge quarantine entries older than 7 days</option>
              <option value="14_days">14 days</option>
              <option value="30_days">30 days</option>
            </select>
          </label>
          <p className="muted">Retention runs at the start of each scan. Restore important files before they expire.</p>
        </section>

        <section className="settings-section">
          <h3>Logging mode</h3>
          <label>
            Audit log detail
            <select
              value={settings.logging_mode}
              disabled={busy}
              onChange={(e) => onSaveSettings({ logging_mode: e.target.value as LoggingMode })}
            >
              <option value="redacted_paths">Redacted paths (default) — hashes instead of full paths in audit log</option>
              <option value="normal">Normal — full paths in local audit log only</option>
              <option value="minimal">Minimal — action types only, no paths</option>
            </select>
          </label>
          <p className="muted">Logs stay on your machine. No telemetry is sent.</p>
        </section>

        <div className="warn-box">
          <strong>Safety limits (cannot be changed)</strong>
          <ul>
            <li>Protected system paths are always blocked from cleanup.</li>
            <li>Unknown and critical items are never auto-selected.</li>
            <li>Settings cannot disable the rules engine or path protections.</li>
            <li>No cloud APIs or telemetry.</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
