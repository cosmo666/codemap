import { useState } from 'react';
import { fetchGraph, startAnalyze, subscribeProgress } from '../api/client';
import { useStore } from '../store/store';

export default function AnalyzeScreen() {
  const [repoPath, setRepoPath] = useState('');
  const [error, setError] = useState<string | null>(null);
  const phase = useStore((s) => s.phase);
  const progress = useStore((s) => s.progress);
  const { setPhase, pushProgress, setGraph } = useStore.getState();

  const start = async () => {
    setError(null);
    try {
      const id = await startAnalyze(repoPath);
      setPhase('analyzing');
      subscribeProgress(id, (event) => {
        pushProgress(event);
        if (event.stage === 'done') fetchGraph().then(setGraph).catch((e) => setError(String(e)));
        if (event.stage === 'error') {
          setError(event.detail ?? 'analysis failed');
          setPhase('welcome');
        }
      });
    } catch (e) {
      setError(String(e));
    }
  };

  const label =
    progress?.stage === 'explaining' && progress.total
      ? `explaining ${progress.detail ?? ''} … ${progress.current}/${progress.total}`
      : (progress?.stage ?? 'ready');

  return (
    <div className="analyze-screen">
      <h1>CodeMap</h1>
      <p>Point me at a Python repository.</p>
      {phase === 'welcome' && (
        <div className="analyze-form">
          <input
            value={repoPath}
            onChange={(e) => setRepoPath(e.target.value)}
            placeholder="C:\path\to\repo"
            onKeyDown={(e) => e.key === 'Enter' && void start()}
          />
          <button onClick={() => void start()}>Analyze</button>
        </div>
      )}
      {phase === 'analyzing' && <p className="ticker">{label}</p>}
      {error && <p className="error">{error}</p>}
    </div>
  );
}
