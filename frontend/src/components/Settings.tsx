import type { PermissionMode } from "../api";

type Props = {
  mode: PermissionMode;
  advancedMode: boolean;
  includeRecycleBin: boolean;
  onModeChange: (m: PermissionMode) => void;
  onAdvancedChange: (v: boolean) => void;
  onRecycleBinChange: (v: boolean) => void;
  busy: boolean;
};

export function Settings({
  mode,
  advancedMode,
  includeRecycleBin,
  onModeChange,
  onAdvancedChange,
  onRecycleBinChange,
  busy,
}: Props) {
  return (
    <div className="settings panel">
      <div className="panel-header">
        <h2>Settings</h2>
      </div>
      <div className="settings-body">
        <label>
          Permission mode
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
        <p className="muted">
          Assisted mode is required before quarantining files. Read-only mode cannot change files.
        </p>

        <label>
          <input
            type="checkbox"
            checked={advancedMode}
            onChange={(e) => onAdvancedChange(e.target.checked)}
          />{" "}
          Advanced mode — allow selecting unknown / review-needed files for cleanup preview
        </label>

        <label>
          <input
            type="checkbox"
            checked={includeRecycleBin}
            onChange={(e) => onRecycleBinChange(e.target.checked)}
          />{" "}
          Include empty Recycle Bin in cleanup preview (requires separate permanent confirmation)
        </label>

        <div className="warn-box">
          <strong>Current limitations</strong>
          <ul>
            <li>Cleanup only quarantines files — not services, startup entries, or registry.</li>
            <li>No cloud lookup, telemetry, or automatic deletion without your confirmation.</li>
            <li>Performance mode does not delete files; it may suspend processes after preview.</li>
            <li>Unknown items stay unselected unless Advanced mode is on.</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
