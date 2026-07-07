import GraphScene from './scene/GraphScene';
import AnalyzeScreen from './panels/AnalyzeScreen';
import ChatDock from './panels/ChatDock';
import ModulePanel from './panels/ModulePanel';
import { useStore } from './store/store';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';

function BrandPlate() {
  const overview = useStore((s) => s.graph?.overview ?? null);
  return (
    <header className="fixed top-4 left-4 z-20 flex max-w-md flex-col gap-1 rounded-lg border border-border bg-card px-4 py-3 text-card-foreground shadow-lg shadow-black/30 backdrop-blur-md motion-safe:animate-panel-in">
      <h1 className="font-display text-sm font-medium tracking-[0.35em] text-foreground">CODEMAP</h1>
      {overview && (
        <Tooltip>
          <TooltipTrigger asChild>
            <p
              tabIndex={0}
              className="max-w-sm truncate rounded-sm text-xs text-muted-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {overview}
            </p>
          </TooltipTrigger>
          <TooltipContent side="bottom" align="start">
            {overview}
          </TooltipContent>
        </Tooltip>
      )}
    </header>
  );
}

export default function App() {
  const phase = useStore((s) => s.phase);
  return (
    <div className="relative h-full">
      {phase === 'ready' ? (
        <>
          <GraphScene />
          <BrandPlate />
          <ModulePanel />
          <ChatDock />
        </>
      ) : (
        <AnalyzeScreen />
      )}
    </div>
  );
}
