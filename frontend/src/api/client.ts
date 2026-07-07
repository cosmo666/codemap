import type { ChatEvent, ChatMessage, GraphData, ModuleDetail, PipelineEvent } from './types';

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) throw new Error(`${response.status}: ${await response.text()}`);
  return (await response.json()) as T;
}

export const fetchGraph = (): Promise<GraphData> => fetch('/graph').then((r) => json<GraphData>(r));

export const fetchModule = (path: string): Promise<ModuleDetail> =>
  fetch(`/module/${path}`).then((r) => json<ModuleDetail>(r));

export async function startAnalyze(repoPath: string): Promise<string> {
  const r = await fetch('/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ repo_path: repoPath }),
  });
  const body = await json<{ analysis_id: string }>(r);
  return body.analysis_id;
}

export function subscribeProgress(id: string, onEvent: (e: PipelineEvent) => void): () => void {
  const source = new EventSource(`/analyze/${id}/events`);
  let finished = false;
  source.onmessage = (message) => {
    const event = JSON.parse(message.data as string) as PipelineEvent;
    onEvent(event);
    if (event.stage === 'done' || event.stage === 'error') {
      finished = true;
      source.close();
    }
  };
  source.onerror = () => {
    source.close();
    if (!finished) {
      finished = true;
      onEvent({ stage: 'error', current: null, total: null, detail: 'connection lost' });
    }
  };
  return () => source.close();
}

export async function streamChat(
  question: string,
  history: ChatMessage[],
  handlers: { onToken: (t: string) => void; onCitation: (p: string) => void; onDone: () => void },
): Promise<void> {
  const response = await fetch('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question,
      history: history.map(({ role, content }) => ({ role, content })),
    }),
  });
  if (!response.ok || !response.body) throw new Error(`chat failed: ${response.status}`);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      if (!line.startsWith('data:')) continue;
      const event = JSON.parse(line.slice(5).trim()) as ChatEvent;
      if (event.type === 'token') handlers.onToken(event.content);
      else if (event.type === 'citation') handlers.onCitation(event.path);
      else handlers.onDone();
    }
  }
}
