const PROMPTS = [
  "What can I close before gaming?",
  "What can I safely suspend?",
  "Explain Chrome",
  "Why is this locked?",
  "What is unknown?",
  "Show FPS-impacting apps",
];

export function ChatSuggestedPrompts({ onSelect }: { onSelect: (prompt: string) => void }) {
  return (
    <div className="chat-suggested-prompts">
      {PROMPTS.map((prompt) => (
        <button key={prompt} type="button" className="chat-prompt-chip" onClick={() => onSelect(prompt)}>
          {prompt}
        </button>
      ))}
    </div>
  );
}
