// Tiny "2h ago"-style relative timestamp — deliberately no date library since
// recents only ever needs coarse, one-shot buckets, not full formatting.
const UNITS: { limit: number; div: number; label: string }[] = [
  { limit: 3600, div: 60, label: 'm' },
  { limit: 86400, div: 3600, label: 'h' },
  { limit: 604800, div: 86400, label: 'd' },
  { limit: 2629800, div: 604800, label: 'w' },
  { limit: 31557600, div: 2629800, label: 'mo' },
];

export function relativeTime(iso: string): string {
  // Python's isoformat() emits microseconds; some engines reject more than
  // three fractional digits, so truncate to milliseconds before parsing.
  const then = new Date(iso.replace(/(\.\d{3})\d+/, '$1')).getTime();
  if (Number.isNaN(then)) return '';
  const diffSeconds = Math.max(0, (Date.now() - then) / 1000);
  if (diffSeconds < 60) return 'just now';
  for (const { limit, div, label } of UNITS) {
    if (diffSeconds < limit) return `${Math.floor(diffSeconds / div)}${label} ago`;
  }
  return `${Math.floor(diffSeconds / 31557600)}y ago`;
}
