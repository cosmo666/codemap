export interface GraphNode {
  id: string;
  module: string;
  package: string;
  loc: number;
  status: 'ok' | 'parse_error';
  centrality: number;
  explanation: string | null;
}

export interface GraphEdge {
  source: string;
  target: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  packages: string[];
  overview: string | null;
}

export interface PipelineEvent {
  stage: 'parsing' | 'explaining' | 'indexing' | 'done' | 'error';
  current: number | null;
  total: number | null;
  detail: string | null;
}

export interface ModuleDetail {
  node: GraphNode;
  dependencies: string[];
  dependents: string[];
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  citations?: string[];
}

export type ChatEvent =
  | { type: 'token'; content: string }
  | { type: 'citation'; path: string }
  | { type: 'done' };
