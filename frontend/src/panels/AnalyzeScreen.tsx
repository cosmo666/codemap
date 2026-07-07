import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { MessageSquare, ScanSearch, Sparkles } from 'lucide-react';
import { fetchGraph, fetchRecents, startAnalyze, subscribeProgress } from '../api/client';
import type { RecentEntry } from '../api/types';
import { useStore } from '../store/store';
import { FolderBrowser } from '../components/FolderBrowser';
import { relativeTime } from '../lib/relativeTime';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';

const STAGE_LABELS: Record<string, string> = {
  parsing: 'PARSING',
  explaining: 'EXPLAINING',
  indexing: 'INDEXING',
};

const HOW_IT_WORKS = [
  { icon: ScanSearch, title: 'Parse', body: 'Every file becomes a star.' },
  { icon: Sparkles, title: 'Explain', body: 'The model describes each module.' },
  { icon: MessageSquare, title: 'Explore', body: 'Ask questions, fly to answers.' },
];

function failureMessage(detail: string): string {
  return `Analysis failed: ${detail}. Check the path and try again.`;
}

function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <p className="font-display text-[11px] tracking-[0.2em] uppercase text-muted-foreground">
      {children}
    </p>
  );
}

function RecentCard({ entry, onOpen }: { entry: RecentEntry; onOpen: (path: string) => void }) {
  const languages = entry.languages.slice(0, 3).map((l) => l.toUpperCase());
  return (
    <button
      type="button"
      onClick={() => onOpen(entry.repo_path)}
      className="flex min-h-20 flex-col gap-1.5 rounded-lg border border-border bg-card/60 p-4 text-left outline-none transition-colors hover:border-primary focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
    >
      <span className="truncate font-mono text-sm font-medium text-primary">{entry.name}</span>
      <span title={entry.repo_path} className="truncate text-xs text-muted-foreground">
        {entry.repo_path}
      </span>
      <span className="mt-1 flex items-center justify-between gap-3 font-mono text-[11px] tabular-nums text-muted-foreground">
        <span className="truncate">
          {entry.modules} MODULES · {entry.packages} PKGS
          {languages.length > 0 ? ` · ${languages.join(', ')}` : ''}
        </span>
        <span className="shrink-0">{relativeTime(entry.analyzed_at)}</span>
      </span>
    </button>
  );
}

function HowItWorks() {
  return (
    <div className="grid grid-cols-1 gap-5 sm:grid-cols-3">
      {HOW_IT_WORKS.map(({ icon: Icon, title, body }) => (
        <div key={title} className="flex flex-col items-start gap-1.5">
          <Icon aria-hidden="true" className="size-4 text-primary" />
          <p className="font-display text-[11px] tracking-[0.2em] uppercase text-muted-foreground">
            {title}
          </p>
          <p className="text-sm leading-relaxed text-muted-foreground">{body}</p>
        </div>
      ))}
    </div>
  );
}

export default function AnalyzeScreen() {
  const [repoPath, setRepoPath] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [recents, setRecents] = useState<RecentEntry[]>([]);
  const phase = useStore((s) => s.phase);
  const progress = useStore((s) => s.progress);
  const { setPhase, pushProgress, setGraph } = useStore.getState();

  // Best-effort: an empty list (fetch failed or there simply are none) just
  // means the recents section stays hidden — never a visible error here.
  useEffect(() => {
    let cancelled = false;
    fetchRecents()
      .then((entries) => {
        if (!cancelled) setRecents(entries);
      })
      .catch(() => {
        /* recents are optional chrome, not a failure worth surfacing */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const start = async (pathOverride?: string) => {
    const target = (pathOverride ?? repoPath).trim();
    if (!target) return;
    setError(null);
    try {
      const id = await startAnalyze(target);
      setPhase('analyzing');
      subscribeProgress(id, (event) => {
        pushProgress(event);
        if (event.stage === 'done')
          fetchGraph()
            .then(setGraph)
            .catch((e) => {
              setError(failureMessage(e instanceof Error ? e.message : String(e)));
              setPhase('welcome');
            });
        if (event.stage === 'error') {
          setError(failureMessage(event.detail ?? 'unknown error'));
          setPhase('welcome');
        }
      });
    } catch (e) {
      setError(failureMessage(e instanceof Error ? e.message : String(e)));
    }
  };

  const openRecent = (path: string) => {
    setRepoPath(path);
    void start(path);
  };

  const stage = progress?.stage ?? 'parsing';
  const stageLabel = STAGE_LABELS[stage] ?? 'PARSING';
  const determinate = progress?.stage === 'explaining' && progress.current != null && progress.total;
  const counts =
    progress?.current != null && progress.total != null
      ? ` - ${progress.current}/${progress.total}`
      : '';
  const ticker = progress
    ? `${stage}${progress.detail ? ` ${progress.detail}` : ''}${counts}`
    : 'starting analysis';

  return (
    <div className="starfield relative h-full overflow-y-auto">
      <div aria-hidden="true" className="starfield-layer starfield-layer-a motion-safe:animate-drift-a" />
      <div aria-hidden="true" className="starfield-layer starfield-layer-b motion-safe:animate-drift-b" />
      <div
        className={
          phase === 'welcome'
            ? 'relative z-10 flex min-h-full flex-col items-center gap-10 px-6 py-16'
            : 'relative z-10 flex h-full items-center justify-center p-6'
        }
      >
        <Card className="w-full max-w-md shadow-2xl shadow-black/50 motion-safe:animate-panel-in">
          <CardContent className="flex flex-col gap-6 p-8">
            <div className="flex flex-col gap-2">
              <h1 className="font-display text-2xl font-medium tracking-[0.35em] text-foreground">
                CODEMAP
              </h1>
              <p className="text-sm leading-relaxed text-muted-foreground">
                Chart a repository as a navigable map of its modules.
              </p>
            </div>

            {phase === 'welcome' && (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void start();
                }}
                className="flex flex-col gap-3"
              >
                <div className="flex gap-2">
                  <Input
                    autoFocus
                    value={repoPath}
                    onChange={(e) => setRepoPath(e.target.value)}
                    placeholder="C:\path\to\repo"
                    aria-label="Repository path"
                    className="font-mono text-sm"
                  />
                  <FolderBrowser onUseFolder={setRepoPath} />
                </div>
                <Button type="submit" disabled={!repoPath.trim()}>
                  Analyze repository
                </Button>
              </form>
            )}

            {phase === 'analyzing' && (
              <div className="flex flex-col gap-3">
                <p className="font-display text-[11px] tracking-[0.2em] uppercase text-muted-foreground">
                  {stageLabel}
                </p>
                {determinate ? (
                  <Progress value={((progress?.current ?? 0) / (progress?.total ?? 1)) * 100} />
                ) : (
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                    <div className="h-full w-full bg-primary/60 motion-safe:animate-pulse" />
                  </div>
                )}
                <p
                  aria-live="polite"
                  className="truncate font-mono text-xs tabular-nums text-muted-foreground"
                >
                  {ticker}
                </p>
              </div>
            )}

            {error && (
              <div
                role="alert"
                className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm leading-relaxed text-destructive"
              >
                {error}
              </div>
            )}
          </CardContent>
        </Card>

        {phase === 'welcome' && recents.length > 0 && (
          <section className="flex w-full max-w-3xl flex-col gap-3">
            <Eyebrow>Recent maps</Eyebrow>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {recents.map((entry) => (
                <RecentCard key={entry.repo_path} entry={entry} onOpen={openRecent} />
              ))}
            </div>
          </section>
        )}

        {phase === 'welcome' && (
          <section className="w-full max-w-3xl">
            <HowItWorks />
          </section>
        )}
      </div>
    </div>
  );
}
