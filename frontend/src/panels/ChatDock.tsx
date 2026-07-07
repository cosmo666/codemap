import { useEffect, useRef, useState } from 'react';
import { streamChat } from '../api/client';
import { useStore } from '../store/store';
import { ModuleChip } from '../components/ModuleChip';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';

export default function ChatDock() {
  const [input, setInput] = useState('');
  // Completion status for the header's aria-live region — set once per answer
  // (never cleared back to '') so screen readers hear that streaming finished.
  const [liveStatus, setLiveStatus] = useState('');
  const chat = useStore((s) => s.chat);
  const streaming = useStore((s) => s.streaming);
  const flyTo = useStore((s) => s.flyTo);
  const rootRef = useRef<HTMLDivElement>(null);
  // Whether the list should stay pinned to the newest message. Updated on every
  // user scroll; auto-scroll only fires while the user is already near the bottom.
  const stickRef = useRef(true);

  useEffect(() => {
    const viewport = rootRef.current?.querySelector<HTMLDivElement>(
      '[data-slot="scroll-area-viewport"]',
    );
    if (!viewport) return;
    const onScroll = () => {
      stickRef.current = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight < 48;
    };
    viewport.addEventListener('scroll', onScroll, { passive: true });
    return () => viewport.removeEventListener('scroll', onScroll);
  }, []);

  useEffect(() => {
    const viewport = rootRef.current?.querySelector<HTMLDivElement>(
      '[data-slot="scroll-area-viewport"]',
    );
    if (viewport && stickRef.current) viewport.scrollTop = viewport.scrollHeight;
  }, [chat]);

  const send = async () => {
    const question = input.trim();
    if (!question || streaming) return;
    setInput('');
    const { addUserMessage, appendAssistantToken, addCitation, finishAssistant } =
      useStore.getState();
    const history = useStore.getState().chat;
    addUserMessage(question);
    // Sentence-case failure copy stating cause and fix, appended after whatever
    // partial answer already streamed in (hence the conditional joining space).
    const appendFailure = (text: string) => {
      const partial = useStore.getState().chat.at(-1)?.content;
      appendAssistantToken(partial ? ` ${text}` : text);
      finishAssistant();
      setLiveStatus('error receiving answer');
    };
    try {
      await streamChat(question, history, {
        onToken: appendAssistantToken,
        onCitation: (path) => {
          addCitation(path);
          flyTo(path); // the answer physically navigates the map
        },
        onDone: () => {
          finishAssistant();
          setLiveStatus('answer ready');
        },
        onError: (detail) => {
          appendFailure(`Couldn't answer that: ${detail}. Try rephrasing the question.`);
        },
      });
    } catch {
      appendFailure("Lost the connection to the server. Check it's running and ask again.");
    }
  };

  return (
    <Card
      ref={rootRef}
      className="fixed bottom-4 left-4 z-20 flex max-h-[60vh] w-110 flex-col overflow-hidden shadow-2xl shadow-black/50 motion-safe:animate-panel-in"
    >
      <header className="flex items-center justify-between border-b border-border px-4 py-2.5">
        <h2 className="font-display text-[11px] tracking-[0.2em] uppercase text-muted-foreground">
          ASK THE MAP
        </h2>
        <span aria-live="polite" className="font-mono text-[11px] text-muted-foreground">
          {streaming ? 'answering' : liveStatus}
        </span>
      </header>
      <ScrollArea className="min-h-0 flex-1">
        <ul className="flex flex-col gap-3 p-4">
          {chat.length === 0 && (
            <li className="py-6 text-center text-sm leading-relaxed text-muted-foreground">
              Ask where anything lives - answers cite modules and fly the camera.
            </li>
          )}
          {chat.map((message, i) => (
            <li
              key={i}
              className={cn('max-w-[85%]', message.role === 'user' ? 'self-end' : 'self-start')}
            >
              <p
                className={cn(
                  'text-sm leading-relaxed whitespace-pre-wrap',
                  message.role === 'user' ? 'text-right text-primary/90' : 'text-foreground',
                )}
              >
                {message.content}
              </p>
              {message.citations && message.citations.length > 0 && (
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {message.citations.map((c) => (
                    <ModuleChip key={c} path={c} onFly={flyTo} className="text-[11px]" />
                  ))}
                </div>
              )}
            </li>
          ))}
        </ul>
      </ScrollArea>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
        className="flex gap-2 border-t border-border p-3"
      >
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about this codebase"
          aria-label="Ask about this codebase"
        />
        <Button type="submit" disabled={streaming}>
          Ask
        </Button>
      </form>
    </Card>
  );
}
