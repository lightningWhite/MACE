"""The map, drawn in characters.

The web client will render the atlas as SVG, and this renders the same atlas
as text. That is the point of it: docs/10 calls the terminal "the one that
keeps the project honest, since anything the terminal can render is provably
engine data rather than UI logic". A map that only the browser can draw would
be a map made of UI logic.

Nothing here decides what the player knows. Fog of war is already applied by
`mace.session.view` — a place the player has not heard of is not in the atlas
at all — so this file's whole job is choosing glyphs and pushing them onto a
grid.

Authors get a plotted map for free where they set `mapPosition`, and a legible
list where they have not. Force-directed layout, which is what would let the
second case look like the first, is the web client's to do: it needs a canvas
that can hold a node anywhere, and this one has 64 columns.
"""

from __future__ import annotations

from mace.session.view import Atlas, Place, Road

__all__ = ["GLYPHS", "draw"]

#: How a place's standing shows up on the map. Three shapes rather than three
#: colors, because a map that is only legible in color is not legible.
GLYPHS = {"here": "●", "visited": "◍", "known": "○"}

#: The map's shape in characters. Wide enough for a label beside a node,
#: short enough to sit above a menu without scrolling it away.
WIDTH = 64
HEIGHT = 13

#: A node needs somewhere to put its name, and a plot with no room for names
#: is a plot of anonymous circles. Below this, the listing is more use.
MIN_PLOT = 12


def draw(atlas: Atlas) -> list[str]:
    """Render the map.

    Parameters
    ----------
    atlas : Atlas
        The projection, fog of war already applied.

    Returns
    -------
    list of str
        Lines to print, without trailing newlines.
    """
    if not atlas.places:
        return ["  You have no idea where you are."]

    lines = _plot(atlas) or []
    if lines:
        lines.append("")
        lines.append(
            f"  {GLYPHS['here']} here   {GLYPHS['visited']} been there   "
            f"{GLYPHS['known']} heard of"
        )
    lines.extend(_listing(atlas))
    return lines


def _plot(atlas: Atlas) -> list[str] | None:
    """Draw the places that have authored coordinates.

    Parameters
    ----------
    atlas : Atlas
        The projection.

    Returns
    -------
    list of str or None
        The grid, or None where there is nothing to plot on it.
    """
    placed = [
        place for place in atlas.places if place.x is not None and place.y is not None
    ]
    if len(placed) < 2:
        return None

    longest = max(len(place.name) for place in placed)
    usable = WIDTH - longest - 3
    if usable < MIN_PLOT:
        return None

    columns = {
        place.location: _scale(
            float(place.x or 0.0),
            min(float(one.x or 0.0) for one in placed),
            max(float(one.x or 0.0) for one in placed),
            usable - 1,
        )
        for place in placed
    }
    rows = {
        place.location: _scale(
            float(place.y or 0.0),
            min(float(one.y or 0.0) for one in placed),
            max(float(one.y or 0.0) for one in placed),
            HEIGHT - 1,
        )
        for place in placed
    }

    grid = [[" "] * WIDTH for _ in range(HEIGHT)]
    for road in atlas.roads:
        if road.origin in columns and road.destination in columns:
            _road(grid, columns, rows, road)
    for place in placed:
        _place(grid, columns[place.location], rows[place.location], place)

    drawn = [f"  {''.join(row).rstrip()}" for row in grid]
    while drawn and not drawn[0].strip():
        drawn.pop(0)
    while drawn and not drawn[-1].strip():
        drawn.pop()
    return drawn


def _scale(value: float, low: float, high: float, span: int) -> int:
    """Put an authored coordinate on the grid.

    Parameters
    ----------
    value : float
        The coordinate.
    low, high : float
        The range every plotted place falls in.
    span : int
        The last index available.

    Returns
    -------
    int
        A grid index. Everything collapses to the middle where the whole map
        shares one coordinate, which is the honest picture of a map drawn in a
        straight line.
    """
    if high <= low:
        return span // 2
    return round((value - low) / (high - low) * span)


def _road(
    grid: list[list[str]],
    columns: dict[str, int],
    rows: dict[str, int],
    road: Road,
) -> None:
    """Draw one route between two plotted places.

    Parameters
    ----------
    grid : list of list of str
        The canvas, written in place.
    columns, rows : dict
        Location id to grid position.
    road : Road
        The route.
    """
    x0, y0 = columns[road.origin], rows[road.origin]
    x1, y1 = columns[road.destination], rows[road.destination]
    across, down = abs(x1 - x0), abs(y1 - y0)

    if road.closed:
        mark = "×"
    elif down * 2 <= across:
        mark = "─"
    elif across * 2 <= down:
        mark = "│"
    else:
        mark = "╲" if (x1 - x0) * (y1 - y0) > 0 else "╱"

    for x, y in _between(x0, y0, x1, y1):
        if grid[y][x] == " ":
            grid[y][x] = mark

    label = f"{road.ticks}"
    at_x, at_y = (x0 + x1) // 2, (y0 + y1) // 2
    if mark != "│" and at_x + len(label) < len(grid[0]):
        for offset, character in enumerate(label):
            grid[at_y][at_x + offset] = character


def _between(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    """The cells a straight line passes through, endpoints excluded.

    Bresenham, because a road drawn by rounding a float per column skips cells
    on a steep slope and leaves a dotted line.

    Parameters
    ----------
    x0, y0 : int
        One end.
    x1, y1 : int
        The other.

    Returns
    -------
    list of tuple of (int, int)
        Grid cells, in order.
    """
    across, down = abs(x1 - x0), -abs(y1 - y0)
    step_x, step_y = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    error = across + down

    cells = []
    x, y = x0, y0
    while (x, y) != (x1, y1):
        doubled = 2 * error
        if doubled >= down:
            error += down
            x += step_x
        if doubled <= across:
            error += across
            y += step_y
        if (x, y) != (x1, y1):
            cells.append((x, y))
    return cells


def _place(grid: list[list[str]], x: int, y: int, place: Place) -> None:
    """Put one place and its name on the grid.

    Parameters
    ----------
    grid : list of list of str
        The canvas, written in place.
    x, y : int
        Where it goes.
    place : Place
        The node.
    """
    grid[y][x] = GLYPHS[place.standing]
    for offset, character in enumerate(f" {place.name}"):
        at = x + 1 + offset
        if at < len(grid[y]):
            grid[y][at] = character


def _listing(atlas: Atlas) -> list[str]:
    """Say in words what the plot cannot: weather, and where a road goes.

    Parameters
    ----------
    atlas : Atlas
        The projection.

    Returns
    -------
    list of str
        Lines to print.
    """
    named = {place.location: place for place in atlas.places}
    lines = [""]

    if atlas.journey is not None:
        walked = atlas.journey.walked
        lines.append(
            f"  On the road to {_name(named, atlas.journey.destination)} — "
            f"{walked:.0f} of {atlas.journey.ticks} ticks walked."
        )
        lines.append("")

    reachable: set[str] = set()
    here = named.get(atlas.here or "")
    if here is not None:
        lines.append(f"  {here.name}{_sky(here)}")
        for road in atlas.roads:
            other = _other_end(road, here.location)
            if other is None:
                continue
            reachable.add(other)
            far = named.get(other)
            shut = "  (closed)" if road.closed else ""
            lines.append(
                f"    {road.ticks:>2} ticks  {_name(named, other)}"
                f"{'' if far is None else _sky(far)}{shut}"
            )

    # Somewhere the player has been told about but cannot set off for is worth
    # its own line; somewhere a road already leads to has just had one.
    elsewhere = [
        place
        for place in atlas.places
        if place.location != atlas.here and place.location not in reachable
    ]
    if elsewhere:
        lines.append("")
        lines.append("  Elsewhere you know of:")
        for place in elsewhere:
            lines.append(f"    {place.name}")
    return lines


def _other_end(road: Road, here: str) -> str | None:
    """Which end of a road is not the one you are standing on.

    Parameters
    ----------
    road : Road
        The route.
    here : str
        Where the player is.

    Returns
    -------
    str or None
        The far end, or None if this road does not touch here — or touches it
        only the wrong way down a one-way road.
    """
    if road.origin == here:
        return road.destination
    if road.destination == here and road.bidirectional:
        return road.origin
    return None


def _name(named: dict[str, Place], location: str) -> str:
    """What to call a place.

    Parameters
    ----------
    named : dict
        Location id to place.
    location : str
        The id.

    Returns
    -------
    str
        Its name, or the bare id for somewhere not on the map.
    """
    place = named.get(location)
    return location if place is None else place.name


def _sky(place: Place) -> str:
    """The weather over a place, parenthesised, or nothing.

    Parameters
    ----------
    place : Place
        The node.

    Returns
    -------
    str
        Something to append to a line.
    """
    return "" if place.sky is None else f" — {place.sky}"
