import { create } from 'zustand';
import type { ChatMessage, GraphData, PipelineEvent } from '../api/types';

export type Phase = 'welcome' | 'analyzing' | 'ready';

interface State {
  phase: Phase;
  graph: GraphData | null;
  selectedId: string | null;
  progress: PipelineEvent | null;
  chat: ChatMessage[];
  streaming: boolean;
  flyTarget: string | null;
  setPhase: (phase: Phase) => void;
  setGraph: (graph: GraphData) => void;
  select: (id: string | null) => void;
  pushProgress: (event: PipelineEvent) => void;
  addUserMessage: (content: string) => void;
  appendAssistantToken: (token: string) => void;
  addCitation: (path: string) => void;
  finishAssistant: () => void;
  flyTo: (id: string | null) => void;
}

export const useStore = create<State>((set) => ({
  phase: 'welcome',
  graph: null,
  selectedId: null,
  progress: null,
  chat: [],
  streaming: false,
  flyTarget: null,
  setPhase: (phase) => set({ phase }),
  setGraph: (graph) => set({ graph, phase: 'ready' }),
  select: (selectedId) => set({ selectedId }),
  pushProgress: (progress) => set({ progress }),
  addUserMessage: (content) =>
    set((s) => ({
      chat: [...s.chat, { role: 'user', content }, { role: 'assistant', content: '', citations: [] }],
      streaming: true,
    })),
  appendAssistantToken: (token) =>
    set((s) => {
      const chat = [...s.chat];
      const last = chat[chat.length - 1];
      chat[chat.length - 1] = { ...last, content: last.content + token };
      return { chat };
    }),
  addCitation: (path) =>
    set((s) => {
      const chat = [...s.chat];
      const last = chat[chat.length - 1];
      chat[chat.length - 1] = { ...last, citations: [...(last.citations ?? []), path] };
      return { chat };
    }),
  finishAssistant: () => set({ streaming: false }),
  flyTo: (flyTarget) => set({ flyTarget }),
}));
