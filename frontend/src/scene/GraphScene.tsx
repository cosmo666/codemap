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
type SceneLink = LinkObject<GraphNode>;

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

  const data = useMemo((): { nodes: SceneNode[]; links: SceneLink[] } => {
    if (!graph) return { nodes: [], links: [] };
    return {
      nodes: graph.nodes.map((n) => ({ ...n })),
      links: graph.edges.map((e) => ({ source: e.source, target: e.target })),
    };
  }, [graph]);

  useEffect(() => {
    nodesRef.current = data.nodes;
  }, [data]);

  const neighborhood = useMemo(() => {
    const set = new Set<string>();
    if (selectedId && graph) {
      set.add(selectedId);
      for (const e of graph.edges) {
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
    // slow orbital establishing shot
    let angle = 0;
    const orbit = setInterval(() => {
      if (engaged.current || useStore.getState().selectedId) {
        engaged.current = true; // latch off permanently at first selection
        return;
      }
      angle += 0.002;
      fg.cameraPosition({ x: 420 * Math.sin(angle), y: 60, z: 420 * Math.cos(angle) });
    }, 40);
    // Fully undo the scene additions: under StrictMode (dev double-invokes mount
    // effects) and HMR, a cleanup that only clears the interval would stack bloom
    // passes and starfields on every re-run. Also disposes the starfield's GPU
    // resources, which scene.remove() alone does not free.
    return () => {
      clearInterval(orbit);
      fg.postProcessingComposer().removePass(bloom);
      fg.scene().remove(starfield);
      starfield.geometry.dispose();
      (starfield.material as THREE.Material).dispose();
    };
  }, []);

  // Selection dimming is computed inside `nodeThreeObject`, which the library only
  // re-invokes when its own inputs change — not on every render — so an explicit
  // refresh() is needed whenever the highlighted neighborhood changes.
  useEffect(() => {
    fgRef.current?.refresh();
  }, [neighborhood]);

  const flyToNode = useCallback((node: SceneNode) => {
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
      1400,
    );
  }, []);

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

  return (
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
      linkColor={() => '#3a4a7a'}
      linkOpacity={0.35}
      linkDirectionalParticles={2}
      linkDirectionalParticleSpeed={0.006}
      linkDirectionalParticleWidth={1.6}
      onNodeClick={(node) => {
        select(node.id);
        flyToNode(node);
      }}
      onBackgroundClick={() => select(null)}
    />
  );
}
