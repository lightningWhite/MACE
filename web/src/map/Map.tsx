/**
 * The map.
 *
 * docs/10 calls it "the single highest-value graphical element, and the
 * reason a web client is worth building at all", and everything on it comes
 * from the atlas: nodes are the places the player knows about, edges are the
 * roads between two of them, lengths come from `ticks`, and the sky over each
 * region is the sky the player last saw there.
 *
 * Fog of war is not applied here. A place the player has not heard of is
 * absent from the projection, so there is nothing on this side to hide — the
 * three states that do reach it are drawn as three *shapes*, hollow to solid
 * as the player learns a place, because a map that is only legible in colour
 * is not legible.
 *
 * **On the accessible version of this.** The nodes are clickable but not
 * focusable, and the SVG describes itself as one image. That is deliberate:
 * every journey the map offers is also a button in the choices list beside
 * it, with a longer and better label written by the author. Duplicating those
 * as bare place names inside a graphic would give a screen-reader user two
 * ways to do the same thing and make the worse one come first.
 */

import type { Atlas, Place } from "../protocol";
import { fit, isAuthored, layout, type Positions } from "./layout";

/** Room around the outermost node, for its label. */
const PAD = 46;

/** How far a region's tint reaches past the places in it. */
const REGION_PAD = 34;

function centre(positions: Positions, places: Place[]) {
  const points = places.flatMap((place) => {
    const at = positions[place.location];
    return at === undefined ? [] : [at];
  });
  if (points.length === 0) return null;
  const x = points.reduce((sum, point) => sum + point.x, 0) / points.length;
  const y = points.reduce((sum, point) => sum + point.y, 0) / points.length;
  const reach = Math.max(
    ...points.map((point) => Math.hypot(point.x - x, point.y - y)),
  );
  return { x, y, radius: reach + REGION_PAD };
}

/** One shape per standing, hollow to solid as the player learns a place. */
function Node({ place, at }: { place: Place; at: { x: number; y: number } }) {
  if (place.standing === "here") {
    return (
      <>
        <circle cx={at.x} cy={at.y} r={9} className="node-halo" />
        <circle cx={at.x} cy={at.y} r={5} className="node-here" />
      </>
    );
  }
  if (place.standing === "visited") {
    return (
      <>
        <circle cx={at.x} cy={at.y} r={5.5} className="node-ring" />
        <circle cx={at.x} cy={at.y} r={2.5} className="node-here" />
      </>
    );
  }
  return <circle cx={at.x} cy={at.y} r={5.5} className="node-ring" />;
}

export function MapView({
  atlas,
  onTravel,
  busy,
}: {
  atlas: Atlas;
  onTravel: (choice: number) => void;
  busy: boolean;
}) {
  if (atlas.places.length === 0) {
    return (
      <section className="panel" aria-labelledby="map-heading">
        <h2 id="map-heading">Map</h2>
        <p className="empty">You have no idea where you are.</p>
      </section>
    );
  }

  const positions = layout(atlas);
  const box = fit(positions, PAD);
  const authored = isAuthored(atlas.places);

  const byRegion = new Map<string, Place[]>();
  for (const place of atlas.places) {
    if (place.region === null) continue;
    byRegion.set(place.region, [...(byRegion.get(place.region) ?? []), place]);
  }

  const here = atlas.places.find((place) => place.location === atlas.here);
  const known = atlas.places.filter((place) => place.standing === "known").length;
  const label =
    `A map of ${atlas.places.length} places. ` +
    (here === undefined ? "" : `You are at ${here.name}. `) +
    (known === 0 ? "" : `${known} you have only heard of.`);

  return (
    <section className="panel map-panel" aria-labelledby="map-heading">
      <h2 id="map-heading">Map</h2>
      <svg
        className="map"
        viewBox={`${box.minX} ${box.minY} ${box.width} ${box.height}`}
        role="img"
        aria-label={label}
      >
        {/* Weather, per region, named rather than merely tinted. */}
        {[...byRegion].map(([region, places]) => {
          const blob = centre(positions, places);
          const sky = places.find((place) => place.sky !== null)?.sky ?? null;
          if (blob === null) return null;
          const mine = places.some((place) => place.location === atlas.here);
          return (
            <g key={region} className={mine ? "region region-here" : "region"}>
              <circle cx={blob.x} cy={blob.y} r={blob.radius} />
              {sky !== null && (
                <text x={blob.x} y={blob.y - blob.radius + 12} className="region-sky">
                  {sky}
                </text>
              )}
            </g>
          );
        })}

        {atlas.roads.map((road) => {
          const from = positions[road.from];
          const to = positions[road.to];
          if (from === undefined || to === undefined) return null;
          return (
            <g key={road.route} className={road.closed ? "road road-shut" : "road"}>
              <line x1={from.x} y1={from.y} x2={to.x} y2={to.y} />
              <text
                x={(from.x + to.x) / 2}
                y={(from.y + to.y) / 2 - 4}
                className="road-ticks"
              >
                {road.ticks}
              </text>
            </g>
          );
        })}

        {/* A road part-walked, drawn as far as the player has got. */}
        {atlas.journey !== null &&
          (() => {
            const from = positions[atlas.journey.from];
            const to = positions[atlas.journey.to];
            if (from === undefined || to === undefined) return null;
            const along =
              atlas.journey.ticks > 0
                ? Math.min(1, atlas.journey.walked / atlas.journey.ticks)
                : 0;
            return (
              <g className="journey">
                <line
                  x1={from.x}
                  y1={from.y}
                  x2={from.x + (to.x - from.x) * along}
                  y2={from.y + (to.y - from.y) * along}
                />
                <circle
                  cx={from.x + (to.x - from.x) * along}
                  cy={from.y + (to.y - from.y) * along}
                  r={4}
                />
              </g>
            );
          })()}

        {atlas.places.map((place) => {
          const at = positions[place.location];
          if (at === undefined) return null;
          const reachable = place.choice !== null && !busy;
          return (
            <g
              key={place.location}
              className={`place place-${place.standing}${
                reachable ? " place-reachable" : ""
              }`}
              aria-hidden="true"
              onClick={
                reachable ? () => onTravel(place.choice as number) : undefined
              }
            >
              {reachable && (
                <circle cx={at.x} cy={at.y} r={14} className="node-target" />
              )}
              <Node place={place} at={at} />
              <text x={at.x + 10} y={at.y + 4} className="place-name">
                {place.name}
              </text>
            </g>
          );
        })}
      </svg>

      <p className="legend">
        <span className="dim">
          {authored ? "as the author drew it" : "roads to scale"}
        </span>
      </p>
    </section>
  );
}
