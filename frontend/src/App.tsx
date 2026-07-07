import { useEffect, useRef } from 'react';
import GraphScene from './scene/GraphScene';
import AnalyzeScreen from './panels/AnalyzeScreen';
import ChatDock from './panels/ChatDock';
import ModulePanel from './panels/ModulePanel';
import { useStore } from './store/store';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';

function BrandPlate() {
  const overview = useStore((s) => s.graph?.overview ?? null);
  const moduleCount = useStore((s) => s.graph?.nodes.length ?? 0);
  const headingRef = useRef<HTMLHeadingElement>(null);

  // BrandPlate mounts at the moment the app swaps AnalyzeScreen for the graph,
  // so land focus on the heading here — otherwise keyboard/screen-reader users
  // are dropped onto <body> with no indication the graph is ready.
  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  return (
    <header className="fixed top-4 left-4 z-20 flex max-w-md flex-col gap-1 rounded-lg border border-border bg-card px-4 py-3 text-card-foreground shadow-lg shadow-black/30 backdrop-blur-md motion-safe:animate-panel-in">
      <h1
        ref={headingRef}
        tabIndex={-1}
        className="font-display text-sm font-medium tracking-[0.35em] text-foreground outline-none"
      >
        CODEMAP
      </h1>
      <p role="status" className="sr-only">
        Graph ready — {moduleCount} modules mapped.
      </p>
      {overview && (
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              className="-mx-2 flex min-h-9 max-w-sm items-center rounded-sm px-2 text-left text-xs text-muted-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <span className="min-w-0 truncate">{overview}</span>
            </button>
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
