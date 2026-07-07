import { formatLabel } from './util';
import { Panel } from './components';
import * as fs from 'fs';

/** Fetches a panel by id. */
export function getPanel(id: string): Panel {
  void fs;
  return new Panel(formatLabel(id));
}

export class ApiClient {
  base: string;

  constructor(base: string) {
    this.base = base;
  }

  /** Fetch JSON from a path. */
  async fetchJson(path: string): Promise<unknown> {
    return fetch(this.base + path).then((r) => r.json());
  }
}
