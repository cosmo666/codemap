import { useCallback, useEffect, useRef, useState } from 'react';
import { CornerUpLeft, Folder, FolderOpen } from 'lucide-react';
import { fetchFs } from '../api/client';
import type { FsListing } from '../api/types';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

/**
 * Server-side directory navigator: a "Browse" ghost button that opens a
 * popover panel listing the backend filesystem (the browser can't yield
 * absolute paths, so this is the only way to fill the repo-path input by
 * clicking rather than typing). Read-only, directories only.
 */
export function FolderBrowser({ onUseFolder }: { onUseFolder: (path: string) => void }) {
  const [open, setOpen] = useState(false);
  const [listing, setListing] = useState<FsListing | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const loadedOnceRef = useRef(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async (path?: string) => {
    setLoading(true);
    setError(null);
    try {
      const next = await fetchFs(path);
      setListing(next);
    } catch {
      // Quiet and reversible: keep whatever listing was already showing.
      setError("Can't open that folder.");
    } finally {
      setLoading(false);
    }
  }, []);

  const close = useCallback(() => {
    setOpen(false);
    containerRef.current?.querySelector<HTMLButtonElement>('[data-slot="button"]')?.focus();
  }, []);

  const openPanel = () => {
    setOpen(true);
    if (!loadedOnceRef.current) {
      loadedOnceRef.current = true;
      void load(listing?.path);
    }
  };

  useEffect(() => {
    if (!open) return;
    panelRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close();
    };
    const onPointerDown = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) close();
    };
    window.addEventListener('keydown', onKey);
    window.addEventListener('mousedown', onPointerDown);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('mousedown', onPointerDown);
    };
  }, [open, close]);

  const hasListing = listing != null;

  return (
    <div ref={containerRef} className="relative shrink-0">
      <Button
        type="button"
        variant="ghost"
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => (open ? close() : openPanel())}
      >
        <FolderOpen aria-hidden="true" />
        Browse
      </Button>
      {open && (
        <Card
          ref={panelRef}
          tabIndex={-1}
          role="dialog"
          aria-label="Choose a folder"
          className="absolute right-0 top-full z-30 mt-2 w-80 max-w-[90vw] shadow-2xl shadow-black/50 outline-none motion-safe:animate-panel-in"
        >
          <div className="flex flex-col gap-2 p-3">
            <p
              title={listing?.path ?? ''}
              className="truncate-start font-mono text-xs text-muted-foreground"
            >
              {listing?.path ?? (loading ? 'Loading…' : '')}
            </p>
            <span aria-live="polite" className="sr-only">
              {loading ? 'Loading folder contents' : ''}
            </span>
            <ScrollArea className="h-56 rounded-md border border-border">
              <div className={cn('flex flex-col p-1', loading && hasListing && 'pointer-events-none opacity-50')}>
                <button
                  type="button"
                  disabled={!listing?.parent}
                  onClick={() => listing?.parent && void load(listing.parent)}
                  className="flex h-9 items-center gap-2 rounded-sm px-2 text-left font-mono text-xs text-muted-foreground outline-none hover:bg-accent/60 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-40"
                >
                  <CornerUpLeft aria-hidden="true" className="size-3.5 shrink-0" />
                  ..
                </button>
                {loading && !hasListing ? (
                  <div className="flex flex-col gap-1 p-1" aria-hidden="true">
                    <Skeleton className="h-8 w-full" />
                    <Skeleton className="h-8 w-full" />
                    <Skeleton className="h-8 w-full" />
                  </div>
                ) : (
                  listing?.dirs.map((dir) => (
                    <button
                      key={dir.path}
                      type="button"
                      onClick={() => void load(dir.path)}
                      className="flex h-9 items-center gap-2 rounded-sm px-2 text-left font-mono text-xs text-foreground outline-none hover:bg-accent/60 hover:text-primary focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      <Folder aria-hidden="true" className="size-3.5 shrink-0 text-muted-foreground" />
                      <span className="truncate">{dir.name}</span>
                    </button>
                  ))
                )}
                {!loading && listing && listing.dirs.length === 0 && (
                  <p className="px-2 py-3 text-xs text-muted-foreground">No subfolders.</p>
                )}
              </div>
            </ScrollArea>
            {error && (
              <p role="alert" className="text-xs leading-relaxed text-destructive">
                {error}
              </p>
            )}
            <Button
              type="button"
              size="sm"
              disabled={!listing}
              onClick={() => {
                if (listing) {
                  onUseFolder(listing.path);
                  close();
                }
              }}
            >
              Use this folder
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}
