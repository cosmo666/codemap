const PALETTE = [
  '#4fc3f7', '#b388ff', '#69f0ae', '#ffd54f', '#ff8a80',
  '#80deea', '#f48fb1', '#c5e1a5', '#ffab91', '#90caf9',
];

export function packageColor(pkg: string): string {
  let hash = 0;
  for (const ch of pkg) hash = (hash * 31 + ch.charCodeAt(0)) | 0;
  return PALETTE[Math.abs(hash) % PALETTE.length];
}

export const ERROR_COLOR = '#7f1d1d';
