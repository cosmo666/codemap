import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { X } from 'lucide-react';
import { fetchModule } from '../api/client';
import type { ModuleDetail } from '../api/types';
import { useStore } from '../store/store';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';

function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <h3 className="font-display text-[11px] tracking-[0.2em] uppercase text-muted-foreground">
      {children}
    </h3>
  );
}

function ChipList({ paths, onFly }: { paths: string[]; onFly: (path: string) => void }) {
  if (paths.length === 0) {
    return <p className="font-mono text-xs text-muted-foreground">None</p>;
  }
  return (
    <ul className="flex flex-wrap gap-1.5">
      {paths.map((path) => (
        <li key={path} className="max-w-full">
          <button
            type="button"
            onClick={() => onFly(path)}
            className="inline-flex h-9 max-w-full items-center rounded-md border border-border bg-background/40 px-2.5 font-mono text-xs text-muted-foreground transition-colors outline-none hover:border-primary hover:text-primary focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          >
            <span className="truncate">{path}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

export default function ModulePanel() {
  const selectedId = useStore((s) => s.selectedId);
  const graph = useStore((s) => s.graph);
  const flyTo = useStore((s) => s.flyTo);
  const select = useStore((s) => s.select);
  const [detail, setDetail] = useState<ModuleDetail | null>(null);
  const panelRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!selectedId) return;
    let cancelled = false;
    fetchModule(selectedId)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch(() => {
        if (!cancelled) setDetail(null);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  // Move focus into the panel when it opens (and when the selection changes).
  useEffect(() => {
    if (selectedId) panelRef.current?.focus();
  }, [selectedId]);

  // Escape closes the panel.
  useEffect(() => {
    if (!selectedId) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') select(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selectedId, select]);

  if (!selectedId) return null;

  const node = graph?.nodes.find((n) => n.id === selectedId) ?? null;
  const showing = detail && detail.node.id === selectedId ? detail : null;
  const dependentsCount = showing
    ? showing.dependents.length
    : (graph?.edges.filter((e) => e.target === selectedId).length ?? 0);

  return (
    <aside
      ref={panelRef}
      tabIndex={-1}
      aria-label="Module details"
      className="fixed inset-y-0 right-0 z-20 flex h-full w-90 flex-col border-l border-border bg-card text-card-foreground shadow-2xl shadow-black/50 outline-none backdrop-blur-md motion-safe:animate-panel-in-right"
    >
      <header className="flex items-start justify-between gap-2 p-5 pb-4">
        {/* Designation plate — the star-catalog entry for the selected module. */}
        <div className="flex min-w-0 flex-col gap-1.5">
          <p className="font-display text-[11px] tracking-[0.2em] uppercase text-muted-foreground">
            MODULE — {node?.package ?? 'unknown'}
          </p>
          <h2
            title={node?.module ?? selectedId}
            className="truncate font-mono text-sm font-medium tracking-wide uppercase text-primary"
          >
            {node?.module ?? selectedId}
          </h2>
          <p className="flex items-center gap-2 font-mono text-[11px] tabular-nums text-muted-foreground">
            <span>{node?.loc ?? 0} LOC</span>
            <span aria-hidden="true" className="h-3 w-px bg-border" />
            <span>MASS {(node?.centrality ?? 0).toFixed(3)}</span>
            <span aria-hidden="true" className="h-3 w-px bg-border" />
            <span>{dependentsCount} DEPENDENTS</span>
          </p>
          {node?.status === 'parse_error' && (
            <Badge variant="destructive" className="font-mono text-[11px] tracking-wide">
              PARSE ERROR
            </Badge>
          )}
        </div>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Close module panel"
          onClick={() => select(null)}
        >
          <X />
        </Button>
      </header>
      <Separator />
      <ScrollArea className="min-h-0 flex-1">
        <div className="flex flex-col gap-5 p-5">
          {showing ? (
            <>
              <p className="text-sm leading-relaxed text-foreground/90">
                {showing.node.explanation ??
                  'Unexplained - the model could not describe this module. Re-run analysis to fill the gap.'}
              </p>
              <section className="flex flex-col gap-2">
                <Eyebrow>Depends on</Eyebrow>
                <ChipList paths={showing.dependencies} onFly={flyTo} />
              </section>
              <section className="flex flex-col gap-2">
                <Eyebrow>Used by</Eyebrow>
                <ChipList paths={showing.dependents} onFly={flyTo} />
              </section>
            </>
          ) : (
            <div className="flex flex-col gap-2">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          )}
        </div>
      </ScrollArea>
    </aside>
  );
}
