export type Surface = "processes" | "fps" | "chat";

const LINKS: Record<Surface, { label: string; target: Surface }[]> = {
  processes: [
    { label: "Preview gaming session", target: "fps" },
    { label: "Ask what can be previewed", target: "chat" },
  ],
  fps: [
    { label: "Review full inventory", target: "processes" },
    { label: "Ask what can be previewed", target: "chat" },
  ],
  chat: [
    { label: "Review full inventory", target: "processes" },
    { label: "Preview gaming session", target: "fps" },
  ],
};

type Props = {
  current: Surface;
  onNavigate?: (target: Surface) => void;
};

/** Cross-links between Process Control, FPS Optimizer, and Ask OpenCleaner. */
export function SurfaceCrossLinks({ current, onNavigate }: Props) {
  return (
    <div className="surface-cross-links">
      {LINKS[current].map((link) => (
        <button
          key={link.target}
          type="button"
          className="surface-cross-link"
          onClick={() => onNavigate?.(link.target)}
        >
          {link.label} →
        </button>
      ))}
    </div>
  );
}
