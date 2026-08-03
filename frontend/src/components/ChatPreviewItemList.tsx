import type { ChatCommandPreviewItem, ChatCommandPreviewItemStatus } from "../api";

const STATUS_LABEL: Record<ChatCommandPreviewItemStatus, string> = {
  would_allow: "Preview available",
  blocked: "Locked",
  informational: "Informational",
};

const STATUS_TONE: Record<ChatCommandPreviewItemStatus, string> = {
  would_allow: "preview",
  blocked: "locked",
  informational: "report",
};

export function ChatPreviewItemList({ title, items }: { title: string; items: ChatCommandPreviewItem[] }) {
  if (items.length === 0) return null;
  return (
    <div className="chat-item-list">
      <h4>{title}</h4>
      <ul>
        {items.map((it) => (
          <li key={it.id} className="chat-item-row">
            <div className="chat-item-row-header">
              <span>{it.display_name}</span>
              <span className={`pill process-safety-${STATUS_TONE[it.status]}`}>{STATUS_LABEL[it.status]}</span>
            </div>
            <p className="muted">{it.blocked_reason || it.user_visible_summary || it.reason}</p>
            {it.fps_impact ? <p className="muted">FPS impact: {it.fps_impact}</p> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
