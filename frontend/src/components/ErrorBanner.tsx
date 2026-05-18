type Props = {
  message: string | null;
  onDismiss?: () => void;
};

export function ErrorBanner({ message, onDismiss }: Props) {
  if (!message) return null;
  return (
    <div className="error-banner" role="alert">
      <div>
        <strong>Something went wrong</strong>
        <p>{message}</p>
      </div>
      {onDismiss ? (
        <button type="button" onClick={onDismiss}>
          Dismiss
        </button>
      ) : null}
    </div>
  );
}
