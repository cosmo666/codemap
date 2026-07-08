export interface GraphNode {
  id: string;
  module: string;
  package: string;
  loc: number;
  status: 'ok' | 'parse_error';
  centrality: number;
  explanation: string | null;
  language: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  /** "import": a real resolved dependency. "structural": folder-sibling
   * connectivity with no resolvable import - keeps the map from reading as a
   * disconnected point cloud without claiming a dependency that isn't there. */
  kind: 'import' | 'structural';
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
  | { type: 'error'; detail: string }
  | { type: 'done' };

export interface RecentEntry {
  repo_path: string;
  name: string;
  analyzed_at: string;
  modules: number;
  packages: number;
  languages: string[];
}

export interface FsDirEntry {
  name: string;
  path: string;
}

export interface FsListing {
  path: string;
  parent: string | null;
  dirs: FsDirEntry[];
}
