type Props = {
  value: string;
  onChange: (value: string) => void;
  confirmExplicitSelection: boolean;
  onConfirmExplicitSelectionChange: (value: boolean) => void;
  onSubmit: () => void;
  loading: boolean;
};

export function ChatCommandInput({
  value,
  onChange,
  confirmExplicitSelection,
  onConfirmExplicitSelectionChange,
  onSubmit,
  loading,
}: Props) {
  return (
    <form
      className="chat-input-row"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      <textarea
        className="chat-textarea"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Ask what's running, what's locked, or what can be previewed before gaming…"
        rows={3}
      />
      <div className="confirm-box">
        <label>
          <input
            type="checkbox"
            checked={confirmExplicitSelection}
            onChange={(e) => onConfirmExplicitSelectionChange(e.target.checked)}
          />
          I understand this may include browser or shell processes that require explicit selection.
        </label>
      </div>
      <div className="chat-actions-row">
        <button type="submit" className="primary" disabled={loading || !value.trim()}>
          {loading ? "Previewing…" : "Preview answer"}
        </button>
      </div>
    </form>
  );
}
