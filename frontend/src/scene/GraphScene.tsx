import { useCallback, useEffect, useMemo, useRef } from 'react';
import type { ComponentType, MutableRefObject } from 'react';
import ForceGraph3D from 'react-force-graph-3d';
import type { ForceGraphMethods, ForceGraphProps, LinkObject, NodeObject } from 'react-force-graph-3d';
import * as THREE from 'three';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';
import type { GraphNode } from '../api/types';
import { useStore } from '../store/store';
import { ERROR_COLOR, packageColor } from './colors';

type SceneNode = NodeObject<GraphNode>;
// LinkObject's generic only parameterizes source/target node typing; the extra
// `kind` field we send is preserved by 3d-force-graph as a pass-through
// property, so it's added here via intersection rather than fighting the
// library's link-data generics.
type SceneLink = LinkObject<GraphNode> & { kind: 'import' | 'structural' };

// react-force-graph-3d's default export is a generic function component (see its
// `FCwithRef` type), but its exported prop/ref types wrap the NodeType parameter in an
// extra `NodeObject<...>` layer that JSX's generic-inference can't cleanly pin down
// against a concrete `GraphNode` shape (it infers `NodeObject<NodeObject<GraphNode>>`
// and friends). The underlying runtime component isn't actually generic — 3d-force-graph
// is duck-typed at runtime — so instead of scattering casts through the JSX below, we
// narrow the component to one concrete, well-defined props/ref shape here, once.
const Graph3D = ForceGraph3D as unknown as ComponentType<
  ForceGraphProps<GraphNode> & { ref?: MutableRefObject<ForceGraphMethods<GraphNode> | undefined> }
>;

function makeStarfield(): THREE.Points {
  const positions = new Float32Array(1500 * 3);
  for (let i = 0; i < positions.length; i++) positions[i] = (Math.random() - 0.5) * 4000;
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  const material = new THREE.PointsMaterial({ color: 0x8899bb, size: 0.9, sizeAttenuation: true });
  return new THREE.Points(geometry, material);
}

export default function GraphScene() {
  const fgRef = useRef<ForceGraphMethods<GraphNode> | undefined>(undefined);
  // 3d-force-graph mutates the node objects it's given in place (adding x/y/z as the
  // simulation runs), so keeping our own ref to the latest `data.nodes` array lets us
  // look up live positions without depending on a `graphData()` getter — the react
  // wrapper's `ForceGraphMethods` type doesn't expose one (only the untyped inner
  // 3d-force-graph instance does), unlike what a naive read of the library might suggest.
  const nodesRef = useRef<SceneNode[]>([]);
  const graph = useStore((s) => s.graph);
  const selectedId = useStore((s) => s.selectedId);
  const flyTarget = useStore((s) => s.flyTarget);
  const select = useStore((s) => s.select);
  const flyTo = useStore((s) => s.flyTo);
  // Tailwind's motion-safe: variant can't reach this imperative three.js code,
  // so the reduced-motion preference is checked here and gates the orbit,
  // camera flights, and link particles below.
  const reduceMotion = useMemo(
    () => window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    [],
  );

  const data = useMemo((): { nodes: SceneNode[]; links: SceneLink[] } => {
    if (!graph) return { nodes: [], links: [] };
    return {
      nodes: graph.nodes.map((n) => ({ ...n })),
      links: graph.edges.map((e) => ({ source: e.source, target: e.target, kind: e.kind })),
    };
  }, [graph]);

  useEffect(() => {
    nodesRef.current = data.nodes;
  }, [data]);

  const neighborhood = useMemo(() => {
    const set = new Set<string>();
    if (selectedId && graph) {
      set.add(selectedId);
      // Only real dependencies spotlight on selection - folder-sibling
      // "structural" edges are connective tissue, not a relationship worth
      // highlighting (and would dilute the "what does this depend on" signal).
      for (const e of graph.edges) {
        if (e.kind !== 'import') continue;
        if (e.source === selectedId) set.add(e.target);
        if (e.target === selectedId) set.add(e.source);
      }
    }
    return set;
  }, [selectedId, graph]);

  // One-way latch: once the user selects a node, the orbital establishing shot stops
  // for the lifetime of this mount — deselecting must NOT resume the orbit and hijack
  // manual camera controls. A ref resets naturally on remount, restoring the orbit.
  const engaged = useRef(false);

  useEffect(() => {
    const fg = fgRef.current;
    if (!fg) return;
    const bloom = new UnrealBloomPass(new THREE.Vector2(window.innerWidth, window.innerHeight), 1.6, 0.8, 0.1);
    fg.postProcessingComposer().addPass(bloom);
    const starfield = makeStarfield();
    fg.scene().add(starfield);
    // Slow orbital establishing shot. Reduced-motion users get the fixed
    // default framing instead of an auto-playing camera move; everyone else
    // can stop the orbit at any time (WCAG 2.2.2) — any pointer interaction
    // with the scene, or selecting a module, latches it off permanently.
    let orbit: ReturnType<typeof setInterval> | undefined;
    if (reduceMotion) {
      fg.cameraPosition({ x: 0, y: 60, z: 420 });
    } else {
      let angle = 0;
      orbit = setInterval(() => {
        if (engaged.current || useStore.getState().selectedId) {
          engaged.current = true; // latch off permanently at first selection
          return;
        }
        angle += 0.002;
        fg.cameraPosition({ x: 420 * Math.sin(angle), y: 60, z: 420 * Math.cos(angle) });
      }, 40);
    }
    // Fully undo the scene additions: under StrictMode (dev double-invokes mount
    // effects) and HMR, a cleanup that only clears the interval would stack bloom
    // passes and starfields on every re-run. Also disposes the starfield's GPU
    // resources, which scene.remove() alone does not free.
    return () => {
      if (orbit !== undefined) clearInterval(orbit);
      fg.postProcessingComposer().removePass(bloom);
      fg.scene().remove(starfield);
      starfield.geometry.dispose();
      (starfield.material as THREE.Material).dispose();
    };
  }, [reduceMotion]);

  // Selection dimming is computed inside `nodeThreeObject`, which the library only
  // re-invokes when its own inputs change — not on every render — so an explicit
  // refresh() is needed whenever the highlighted neighborhood changes.
  useEffect(() => {
    fgRef.current?.refresh();
  }, [neighborhood]);

  const flyToNode = useCallback(
    (node: SceneNode) => {
      const fg = fgRef.current;
      // Pre-simulation (x still undefined) we simply no-op rather than flying to the
      // origin or queuing the shot — an acceptable tradeoff since node click targets
      // are unreachable until the force simulation has placed them anyway.
      if (!fg || node.x === undefined) return;
      const distance = 90;
      // Clamp the denominator so a node sitting at (or very near) the origin doesn't
      // blow up the ratio (division by ~0) and send the camera to infinity.
      const dist = Math.max(Math.hypot(node.x, node.y ?? 0, node.z ?? 0), 1);
      const ratio = 1 + distance / dist;
      fg.cameraPosition(
        { x: node.x * ratio, y: (node.y ?? 0) * ratio, z: (node.z ?? 0) * ratio },
        { x: node.x, y: node.y ?? 0, z: node.z ?? 0 },
        reduceMotion ? 0 : 1400,
      );
    },
    [reduceMotion],
  );

  useEffect(() => {
    if (!flyTarget) return;
    const node = nodesRef.current.find((n) => n.id === flyTarget);
    if (node) {
      select(flyTarget);
      flyToNode(node);
    }
    flyTo(null);
  }, [flyTarget, select, flyTo, flyToNode]);

  const dimmed = (node: SceneNode) => neighborhood.size > 0 && !neighborhood.has(node.id);

  const sortedNodes = useMemo(
    () => (graph ? [...graph.nodes].sort((a, b) => a.module.localeCompare(b.module)) : []),
    [graph],
  );

  return (
    <div
      className="h-full"
      // Any pointer interaction with the scene permanently ends the establishing
      // shot — the pointer-level stop mechanism for the auto-orbit (and it keeps
      // the interval from fighting a manual camera drag).
      onPointerDown={() => {
        engaged.current = true;
      }}
    >
      {/* Keyboard-operable proxy for node clicks: the WebGL canvas isn't in the
          tab order, so this visually-hidden (visible on focus) select lets any
          module be reached and selected without a mouse. It drives the same
          flyTo -> select/flyToNode path as onNodeClick. */}
      <label htmlFor="module-jump" className="sr-only">
        Jump to module
      </label>
      <select
        id="module-jump"
        value=""
        onChange={(e) => {
          if (e.target.value) flyTo(e.target.value);
        }}
        className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-1/2 focus:z-30 focus:h-9 focus:w-80 focus:-translate-x-1/2 focus:rounded-md focus:border focus:border-border focus:bg-popover focus:px-3 focus:font-mono focus:text-xs focus:text-popover-foreground focus:outline-none focus:ring-2 focus:ring-ring"
      >
        <option value="" disabled>
          Jump to module…
        </option>
        {sortedNodes.map((n) => (
          <option key={n.id} value={n.id}>
            {n.module}
          </option>
        ))}
      </select>
      <Graph3D
        ref={fgRef}
        graphData={data}
        backgroundColor="#04040c"
        nodeThreeObject={(node) => {
          const radius = 3 + node.centrality * 40;
          const color = node.status === 'parse_error' ? ERROR_COLOR : packageColor(node.package);
          const material = new THREE.MeshBasicMaterial({
            color,
            transparent: true,
            opacity: dimmed(node) ? 0.12 : node.status === 'parse_error' ? 0.5 : 0.95,
          });
          return new THREE.Mesh(new THREE.SphereGeometry(radius, 24, 24), material);
        }}
        nodeThreeObjectExtend={false}
        nodeLabel={(node) => node.module}
        // Import edges are bright, particle-animated dependency lines; structural
        // (folder-sibling) edges are dim, static connective tissue - present so the
        // map never reads as a disconnected point cloud, but never mistaken for a
        // claimed dependency (no particles = no implied direction of data flow).
        linkColor={(link) => ((link as SceneLink).kind === 'structural' ? '#1c2442' : '#3a4a7a')}
        linkOpacity={0.35}
        linkDirectionalParticles={(link) =>
          reduceMotion || (link as SceneLink).kind === 'structural' ? 0 : 2
        }
        linkDirectionalParticleSpeed={reduceMotion ? 0 : 0.006}
        linkDirectionalParticleWidth={1.6}
        onNodeClick={(node) => {
          select(node.id);
          flyToNode(node);
        }}
        onBackgroundClick={() => select(null)}
      />
    </div>
  );
}
