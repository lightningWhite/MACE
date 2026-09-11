/**
 * The scene graph, and the question it exists to answer.
 *
 * Nothing here writes. It is not an authoring *step* — it is the thing an
 * author cannot hold in their head past about a dozen scenes, and the one
 * question worth asking of a pack that size: **is there any way in?**
 *
 * Reachability is not computed here. It comes down from the wizard, which
 * works it out the same way `mace validate` does, so the graph and the problem
 * list can never disagree about whether a scene is orphaned. A client that
 * walked the edges itself would be a second implementation of the rule, and
 * the first thing a second implementation does is drift.
 *
 * The layout is columns by depth from an entrance rather than a force
 * simulation. A story is a thing with a beginning, and an author looking for
 * the way into a scene wants to read left to right; a force layout would look
 * more impressive and answer the question worse.
 */

import { useEffect, useRef, useState } from "react";

import * as api from "./api";
import { StudioError } from "./api";
import { useSvgPanZoom } from "./panzoom";
import type { Graph, Node } from "./protocol";

/** Space between columns and between rows. */
const COLUMN = 190;
const ROW = 34;

interface Laid {
  node: Node;
  depth: number;
  row: number;
}

/**
 * How far each scene is from the nearest way in.
 *
 * Unreachable scenes get a column of their own past the end, together, which
 * is exactly how they should read: a set of islands, off to one side, with
 * nothing pointing at them.
 */
function laid(graph: Graph): Laid[] {
  const depth = new Map<string, number>();
  let frontier = graph.entrances;
  let level = 0;
  for (const id of frontier) depth.set(id, 0);

  const leads = new Map(graph.scenes.map((one) => [one.id, one.leadsTo]));
  while (frontier.length > 0 && level < graph.scenes.length) {
    level += 1;
    const next: string[] = [];
    for (const id of frontier) {
      for (const onward of leads.get(id) ?? []) {
        if (depth.has(onward)) continue;
        depth.set(onward, level);
        next.push(onward);
      }
    }
    frontier = next;
  }

  const orphaned = Math.max(0, ...[...depth.values()]) + 1;
  const rows = new Map<number, number>();
  return graph.scenes.map((node) => {
    const column = depth.get(node.id) ?? orphaned;
    const row = rows.get(column) ?? 0;
    rows.set(column, row + 1);
    return { node, depth: column, row };
  });
}

export function SceneGraph({ onOpen }: { onOpen: (id: string) => void }) {
  const [graph, setGraph] = useState<Graph | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const surface = useRef<SVGSVGElement | null>(null);

  useEffect(() => {
    void api
      .graph()
      .then(setGraph)
      .catch((error: unknown) => {
        setFailure(error instanceof StudioError ? error.message : "no graph");
      });
  }, []);

  // Computed unconditionally — see MapEditor's own note by its pan/zoom hook
  // call — so an empty or not-yet-loaded graph still gives the hook a box.
  const nodes = graph === null ? [] : laid(graph);
  const width = (Math.max(0, ...nodes.map((one) => one.depth)) + 1) * COLUMN;
  const height = (Math.max(0, ...nodes.map((one) => one.row)) + 1) * ROW + 20;
  const pan = useSvgPanZoom(surface, { x: 0, y: 0, w: width, h: height });

  if (failure !== null) return <p className="studio-failure">{failure}</p>;
  if (graph === null) return <p className="dim">Working out what leads where…</p>;
  if (graph.scenes.length === 0) return null;

  const at = new Map(nodes.map((one) => [one.node.id, one]));
  const orphans = graph.scenes.filter((one) => !one.reachable);

  const point = (one: Laid) => ({ x: one.depth * COLUMN + 10, y: one.row * ROW + 20 });

  return (
    <div className="scene-graph">
      <p className="dim">
        {graph.entrances.length} way{graph.entrances.length === 1 ? "" : "s"} in,
        left to right.{" "}
        {orphans.length === 0
          ? "Every scene can be reached."
          : `${orphans.length} cannot be reached from anywhere.`}
      </p>

      {graph.dropped.length === 0 ? null : (
        <p className="studio-failure">
          Not on the graph, because they will not build:{" "}
          {graph.dropped.join(", ")}.
        </p>
      )}

      {pan.zoomed ? (
        <button type="button" className="link-button graph-reset" onClick={pan.reset}>
          reset view
        </button>
      ) : null}

      <svg
        ref={surface}
        className="graph"
        viewBox={pan.viewBox}
        role="img"
        aria-label={
          `${graph.scenes.length} scenes. ` +
          (orphans.length === 0
            ? "All of them can be reached."
            : `These cannot be reached from anywhere: ${orphans
                .map((one) => one.id)
                .join(", ")}.`)
        }
        {...pan.background}
      >
        {nodes.flatMap((one) =>
          one.node.leadsTo.flatMap((onward) => {
            const other = at.get(onward);
            if (other === undefined) return [];
            const from = point(one);
            const to = point(other);
            return [
              <line
                key={`${one.node.id}->${onward}`}
                className="graph-edge"
                x1={from.x + 4}
                y1={from.y}
                x2={to.x - 4}
                y2={to.y}
              />,
            ];
          }),
        )}

        {nodes.map((one) => {
          const { x, y } = point(one);
          return (
            <g
              key={one.node.id}
              className={
                "graph-node" +
                (one.node.reachable ? "" : " graph-orphan") +
                (one.node.entrance ? " graph-entrance" : "")
              }
              onClick={() => onOpen(one.node.id)}
            >
              <circle cx={x} cy={y} r={4} />
              <text x={x + 8} y={y + 3.5}>
                {one.node.id}
              </text>
              {/* Said as well as drawn: an orphan that were only a colour
                  would be invisible to a third of the people reading this. */}
              {one.node.reachable ? null : (
                <text x={x + 8} y={y + 12} className="graph-note">
                  no way in
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
