import GraphScene from './scene/GraphScene';
import { useStore } from './store/store';

export default function App() {
  const phase = useStore((s) => s.phase);
  return (
    <div className="app">
      {phase === 'ready' && <GraphScene />}
      {phase !== 'ready' && <div className="app">CodeMap — phase: {phase}</div>}
    </div>
  );
}
