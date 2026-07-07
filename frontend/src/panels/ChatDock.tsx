import { useState } from 'react';
import { streamChat } from '../api/client';
import { useStore } from '../store/store';

export default function ChatDock() {
  const [input, setInput] = useState('');
  const chat = useStore((s) => s.chat);
  const streaming = useStore((s) => s.streaming);
  const flyTo = useStore((s) => s.flyTo);

  const send = async () => {
    const question = input.trim();
    if (!question || streaming) return;
    setInput('');
    const { addUserMessage, appendAssistantToken, addCitation, finishAssistant } =
      useStore.getState();
    const history = useStore.getState().chat;
    addUserMessage(question);
    try {
      await streamChat(question, history, {
        onToken: appendAssistantToken,
        onCitation: (path) => {
          addCitation(path);
          flyTo(path); // the answer physically navigates the map
        },
        onDone: finishAssistant,
        onError: (detail) => {
          appendAssistantToken(` [error: ${detail}]`);
          finishAssistant();
        },
      });
    } catch {
      appendAssistantToken(' [connection lost]');
      finishAssistant();
    }
  };

  return (
    <div className="chat-dock">
      <div className="chat-messages">
        {chat.map((message, i) => (
          <div key={i} className={`msg ${message.role}`}>
            <p>{message.content}</p>
            {message.citations && message.citations.length > 0 && (
              <div className="citations">
                {message.citations.map((c) => (
                  <button key={c} onClick={() => flyTo(c)}>{c}</button>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
      <div className="chat-input">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about this codebase…"
          onKeyDown={(e) => e.key === 'Enter' && void send()}
        />
        <button disabled={streaming} onClick={() => void send()}>Send</button>
      </div>
    </div>
  );
}
