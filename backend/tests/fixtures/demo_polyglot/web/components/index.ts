import { slugify } from '../util';

export const DEFAULT_TITLE = 'CodeMap';

/** A rectangular UI region. */
export class Panel {
  label: string;

  constructor(label: string) {
    this.label = slugify(label);
  }
}
