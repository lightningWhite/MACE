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
 *
 * The price overlay is the one thing here a player switches on, and it draws
 * **only what they have personally been quoted** — `place.prices` holds the
 * journal, not the engine's answer. A map that shaded every market would be a
 * map that told the player where to go, and the whole intended experience is
 * that they work out there is money in carrying salt north on their own.
 * Prices are drawn as numbers as well as shades for the usual reason: a map
 * legible only in colour is not legible.
 *
 * Elevation is different: it's geography, not a discovery, so it rides the
 * same always-drawn region blob the weather does — a tint from `place.elevation`
 * (higher regions shade darker) plus the number itself, for the same reason
 * prices are.
 */

import { useRef, useState } from "react";

import type { Atlas, Carried, Place } from "../protocol";
import { useSvgPanZoom } from "../panzoom";
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

/** Which goods the player has ever been quoted a price for, in name order. */
function priced(atlas: Atlas, carried: Carried[]): Array<[string, string]> {
  const seen = new Map<string, string>();
  for (const place of atlas.places) {
    for (const good of Object.keys(place.prices)) {
      // The good's id and the item's are the same word often enough to be
      // worth trying, and the pack is the only place a readable name lives.
      const named = carried.find((stack) => stack.item === good);
      seen.set(good, named?.name ?? good.split(":").pop() ?? good);
    }
  }
  return [...seen].sort((one, two) => one[1].localeCompare(two[1]));
}

export function MapView({
  atlas,
  carried = [],
  onTravel,
  busy,
  heading = "Map",
}: {
  atlas: Atlas;
  /** The player's pack, only so a good can be named rather than id'd. */
  carried?: Carried[];
  onTravel: (choice: number) => void;
  busy: boolean;
  /** What to call this map — lets a second, smaller map sit beside it. */
  heading?: string;
}) {
  const [shading, setShading] = useState<string | null>(null);
  const headingId = `map-heading-${heading.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
  const surface = useRef<SVGSVGElement | null>(null);

  // Computed unconditionally, empty atlas or not, because the pan/zoom hook
  // below has to be called on every render regardless of what this returns —
  // `layout`/`fit` are both already safe on an empty atlas (MapEditor and
  // SceneGraph share this same shape for the same reason).
  const positions = layout(atlas);
  const box = fit(positions, PAD);
  const pan = useSvgPanZoom(surface, {
    x: box.minX,
    y: box.minY,
    w: box.width,
    h: box.height,
  });

  if (atlas.places.length === 0) {
    return (
      <section className="panel" aria-labelledby={headingId}>
        <h2 id={headingId}>{heading}</h2>
        <p className="empty">You have no idea where you are.</p>
      </section>
    );
  }

  const goods = priced(atlas, carried);
  const showing = shading !== null && goods.some(([good]) => good === shading);
  const quoted = showing
    ? atlas.places.flatMap((place) => {
        const price = place.prices[shading];
        return price === undefined ? [] : [price];
      })
    : [];
  const cheapest = quoted.length > 0 ? Math.min(...quoted) : 0;
  const dearest = quoted.length > 0 ? Math.max(...quoted) : 0;

  const elevations = atlas.places.flatMap((place) =>
    place.elevation === null ? [] : [place.elevation],
  );
  const lowest = elevations.length > 0 ? Math.min(...elevations) : 0;
  const highest = elevations.length > 0 ? Math.max(...elevations) : 0;
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
    <section className="panel map-panel" aria-labelledby={headingId}>
      <h2 id={headingId}>{heading}</h2>
      {pan.zoomed ? (
        <button type="button" className="link-button map-reset" onClick={pan.reset}>
          reset view
        </button>
      ) : null}
      <svg
        ref={surface}
        className="map"
        viewBox={pan.viewBox}
        role="img"
        aria-label={label}
        {...pan.background}
      >
        {/* Weather, per region, named rather than merely tinted. Elevation
            rides the same blob, as a tint plus a printed number — it's a
            geographic fact rather than a spoiler, so it's always shown. */}
        {[...byRegion].map(([region, places]) => {
          const blob = centre(positions, places);
          const sky = places.find((place) => place.sky !== null)?.sky ?? null;
          const elevation =
            places.find((place) => place.elevation !== null)?.elevation ?? null;
          if (blob === null) return null;
          const mine = places.some((place) => place.location === atlas.here);
          const risen =
            elevation !== null && highest > lowest
              ? (elevation - lowest) / (highest - lowest)
              : null;
          return (
            <g key={region} className={mine ? "region region-here" : "region"}>
              <circle
                cx={blob.x}
                cy={blob.y}
                r={blob.radius}
                style={risen === null ? undefined : { opacity: 0.05 + risen * 0.22 }}
              />
              {sky !== null && (
                <text x={blob.x} y={blob.y - blob.radius + 12} className="region-sky">
                  {sky}
                </text>
              )}
              {elevation !== null && (
                <text
                  x={blob.x}
                  y={blob.y + blob.radius - 6}
                  className="region-elevation"
                >
                  {elevation}
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
              {/* Shut is dashed *and* said. Colour alone would leave the
                  only difference between a road and a closed one invisible
                  to a third of the people who might read this map. */}
              <text
                x={(from.x + to.x) / 2}
                y={(from.y + to.y) / 2 - 4}
                className="road-ticks"
              >
                {road.closed ? "shut" : road.ticks}
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
              {showing && place.prices[shading] !== undefined && (
                <>
                  <circle
                    cx={at.x}
                    cy={at.y}
                    r={16}
                    className={
                      dearest === cheapest
                        ? "price-blob"
                        : place.prices[shading] === cheapest
                          ? "price-blob price-cheap"
                          : place.prices[shading] === dearest
                            ? "price-blob price-dear"
                            : "price-blob"
                    }
                  />
                  <text x={at.x + 10} y={at.y + 16} className="price-mark">
                    {place.prices[shading]}
                  </text>
                </>
              )}
            </g>
          );
        })}
      </svg>

      <p className="legend">
        <span className="dim">
          {authored ? "as the author drew it" : "roads to scale"}
        </span>
        {goods.length === 0 ? null : (
          <label className="price-picker">
            <span className="dim">prices seen for</span>
            <select
              value={shading ?? ""}
              aria-label="Shade the map by the price of"
              onChange={(event) =>
                setShading(event.target.value === "" ? null : event.target.value)
              }
            >
              <option value="">— nothing —</option>
              {goods.map(([good, name]) => (
                <option key={good} value={good}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        )}
      </p>
    </section>
  );
}
