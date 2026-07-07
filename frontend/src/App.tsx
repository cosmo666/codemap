import GraphScene from './scene/GraphScene';
import AnalyzeScreen from './panels/AnalyzeScreen';
import ChatDock from './panels/ChatDock';
import ModulePanel from './panels/ModulePanel';
import { useStore } from './store/store';

export default function App() {
  const phase = useStore((s) => s.phase);
  return (
    <div className="app">
      {phase === 'ready' ? (
        <>
          <GraphScene />
          <ModulePanel />
          <ChatDock />
        </>
      ) : (
        <AnalyzeScreen />
      )}
    </div>
  );
}
