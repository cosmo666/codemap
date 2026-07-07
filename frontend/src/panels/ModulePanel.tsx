import { useEffect, useState } from 'react';
import { fetchModule } from '../api/client';
import type { ModuleDetail } from '../api/types';
import { useStore } from '../store/store';

export default function ModulePanel() {
  const selectedId = useStore((s) => s.selectedId);
  const flyTo = useStore((s) => s.flyTo);
  const [detail, setDetail] = useState<ModuleDetail | null>(null);

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

  if (!selectedId) return null;
  const showing = detail && detail.node.id === selectedId ? detail : null;
  return (
    <aside className="module-panel">
      <h2>{selectedId}</h2>
      {showing ? (
        <>
          <p className="explanation">{showing.node.explanation ?? 'Unexplained (LLM failed; re-run analysis).'}</p>
          <h3>Depends on</h3>
          <ul>{showing.dependencies.map((d) => <li key={d} onClick={() => flyTo(d)}>{d}</li>)}</ul>
          <h3>Used by</h3>
          <ul>{showing.dependents.map((d) => <li key={d} onClick={() => flyTo(d)}>{d}</li>)}</ul>
        </>
      ) : (
        <p>loading…</p>
      )}
    </aside>
  );
}
