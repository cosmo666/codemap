import { packageColor } from '../scene/colors';
import { useStore } from '../store/store';
import { cn } from '@/lib/utils';

/**
 * A miniature designation plate, shared by ModulePanel's dependency lists and
 * ChatDock's citation chips: violet package dot (same tint function as the 3D
 * scene), mono module path, and a destructive-red flag when the target module
 * failed to parse.
 */
export function ModuleChip({
  path,
  onFly,
  className,
}: {
  path: string;
  onFly: (path: string) => void;
  className?: string;
}) {
  const node = useStore((s) => s.graph?.nodes.find((n) => n.id === path) ?? null);
  const broken = node?.status === 'parse_error';
  return (
    <button
      type="button"
      onClick={() => onFly(path)}
      className={cn(
        'inline-flex h-9 max-w-full items-center gap-1.5 rounded-md border border-border bg-background/40 px-2.5 font-mono text-xs text-muted-foreground transition-colors outline-none hover:border-primary hover:text-primary focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
        className,
      )}
    >
      <span
        aria-hidden="true"
        className="size-1.5 shrink-0 rounded-full"
        style={{ backgroundColor: node ? packageColor(node.package) : 'var(--violet)' }}
      />
      <span className="truncate">{path}</span>
      {broken && (
        <span className="shrink-0 font-display text-[9px] tracking-[0.15em] text-destructive">
          ERR<span className="sr-only"> — parse error</span>
        </span>
      )}
    </button>
  );
}
