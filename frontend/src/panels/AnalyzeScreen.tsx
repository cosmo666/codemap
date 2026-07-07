import { useState } from 'react';
import { fetchGraph, startAnalyze, subscribeProgress } from '../api/client';
import { useStore } from '../store/store';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';

const STAGE_LABELS: Record<string, string> = {
  parsing: 'PARSING',
  explaining: 'EXPLAINING',
  indexing: 'INDEXING',
};

function failureMessage(detail: string): string {
  return `Analysis failed: ${detail}. Check the path and try again.`;
}

export default function AnalyzeScreen() {
  const [repoPath, setRepoPath] = useState('');
  const [error, setError] = useState<string | null>(null);
  const phase = useStore((s) => s.phase);
  const progress = useStore((s) => s.progress);
  const { setPhase, pushProgress, setGraph } = useStore.getState();

  const start = async () => {
    if (!repoPath.trim()) return;
    setError(null);
    try {
      const id = await startAnalyze(repoPath);
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
    <div className="starfield flex h-full items-center justify-center p-6">
      <Card className="w-full max-w-md rounded-lg shadow-2xl shadow-black/50 motion-safe:animate-panel-in">
        <CardContent className="flex flex-col gap-6 p-8">
          <div className="flex flex-col gap-2">
            <h1 className="font-display text-2xl font-medium tracking-[0.35em] text-foreground">
              CODEMAP
            </h1>
            <p className="text-sm leading-relaxed text-muted-foreground">
              Chart a Python repository as a navigable map of its modules.
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
              <Input
                autoFocus
                value={repoPath}
                onChange={(e) => setRepoPath(e.target.value)}
                placeholder="C:\path\to\repo"
                aria-label="Repository path"
                className="font-mono text-sm"
              />
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
    </div>
  );
}
