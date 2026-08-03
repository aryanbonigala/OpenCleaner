const CATEGORY_ORDER = ["essential", "important", "non_essential", "gaming_fps_impact", "unknown"] as const;

const CATEGORY_COPY: Record<(typeof CATEGORY_ORDER)[number], { title: string; description: string }> = {
  essential: {
    title: "Essential",
    description: "Locked. Core OS, security, drivers, audio, networking, anti-cheat.",
  },
  important: {
    title: "Important",
    description: "Usually leave running. May affect apps, shell, browser, or user session.",
  },
  non_essential: {
    title: "Non-essential",
    description: "Likely user-level helpers. Preview required before any action.",
  },
  gaming_fps_impact: {
    title: "Gaming / FPS impact",
    description: "May affect overlays, memory, background sync, launchers, or recordings.",
  },
  unknown: {
    title: "Unknown",
    description: "Not enough confidence. Report-only by default.",
  },
};

export function ProcessCategorySummary({ counts }: { counts: Record<string, number> }) {
  return (
    <div className="process-category-grid">
      {CATEGORY_ORDER.map((key) => {
        const copy = CATEGORY_COPY[key];
        return (
          <div key={key} className={`card process-category-card process-category-${key}`}>
            <span className="muted">{copy.title}</span>
            <strong>{counts[key] ?? 0}</strong>
            <span className="muted process-category-desc">{copy.description}</span>
          </div>
        );
      })}
    </div>
  );
}
