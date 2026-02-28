// components/ChatBubble.jsx
// A single conversation turn.
//   - User messages: right-aligned, orange
//   - Assistant messages: left-aligned, dark surface, with JobSathi avatar
//   - Supports an "audio replay" button on assistant messages
//   - Typing indicator variant (animated dots)

export default function ChatBubble({ message, onReplayAudio }) {
  const { role, text, audio_base64, timestamp, isTyping } = message;
  const isAssistant = role === 'assistant';

  const formattedTime = timestamp
    ? new Date(timestamp).toLocaleTimeString('en-IN', {
        hour: '2-digit',
        minute: '2-digit',
        hour12: true,
      })
    : null;

  return (
    <div className={`bubble-row bubble-row--${role}`}>
      {isAssistant && (
        <div className="bubble-avatar" aria-hidden="true">JS</div>
      )}

      <div className={`bubble bubble--${role}`}>
        {isTyping ? (
          <TypingDots />
        ) : (
          <>
            <p className="bubble-text">{text}</p>
            <div className="bubble-meta">
              {formattedTime && (
                <span className="bubble-time">{formattedTime}</span>
              )}
              {isAssistant && audio_base64 && onReplayAudio && (
                <button
                  className="replay-btn"
                  onClick={() => onReplayAudio(audio_base64)}
                  aria-label="Replay audio"
                  title="Replay"
                >
                  <svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor">
                    <polygon points="5,3 19,12 5,21" />
                  </svg>
                </button>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function TypingDots() {
  return (
    <div className="typing-dots" aria-label="JobSathi is typing">
      <span /><span /><span />
    </div>
  );
}
