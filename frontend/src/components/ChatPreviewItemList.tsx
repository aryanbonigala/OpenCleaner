import { useState } from "react";
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

const DEFAULT_VISIBLE = 25;
const SCROLL_CAP_THRESHOLD = 100;

export function ChatPreviewItemList({ title, items }: { title: string; items: ChatCommandPreviewItem[] }) {
  const [expanded, setExpanded] = useState(false);
  if (items.length === 0) return null;

  const hasMore = items.length > DEFAULT_VISIBLE;
  const visible = expanded ? items : items.slice(0, DEFAULT_VISIBLE);
  const capScroll = expanded && items.length > SCROLL_CAP_THRESHOLD;

  return (
    <div className="chat-item-list">
      <h4>{title}</h4>
      {hasMore ? (
        <p className="muted chat-item-list-count">
          Showing {visible.length} of {items.length}
        </p>
      ) : null}
      <ul className={capScroll ? "chat-item-list-scroll" : undefined}>
        {visible.map((it) => (
          <li key={it.id} className="chat-item-row">
            <div className="chat-item-row-header">
              <span className="flex-long-text">{it.display_name}</span>
              <span className={`pill process-safety-${STATUS_TONE[it.status]}`}>{STATUS_LABEL[it.status]}</span>
            </div>
            <p className="muted">{it.blocked_reason || it.user_visible_summary || it.reason}</p>
            {it.fps_impact ? <p className="muted">FPS impact: {it.fps_impact}</p> : null}
          </li>
        ))}
      </ul>
      {capScroll ? <p className="muted footer-note">Large inventories are capped for readability.</p> : null}
      {hasMore ? (
        <div className="chat-item-list-controls">
          <button type="button" onClick={() => setExpanded((v) => !v)}>
            {expanded ? "Show less" : "Show more"}
          </button>
        </div>
      ) : null}
    </div>
  );
}
