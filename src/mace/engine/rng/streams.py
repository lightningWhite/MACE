"""Named random streams, and the service that hands them out.

Every subsystem draws from its own stream, so a fight that runs forty exchanges
instead of twelve does not change which encounter the player meets an hour
later. That independence is what makes golden replay tests maintainable and
what a shared world would need to resolve two players' events without
desyncing. See ADR-0004.

    weather               weather.fronts        world.events
    encounters.<routeId>  combat.<combatId>     loot
    ambient               entity.<instanceId>

A new subsystem takes a new stream and documents it here.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import TypeVar

from mace.engine.rng.pcg import Pcg64, derive_seed

__all__ = ["RandomSource", "RandomStream", "StreamSnapshot"]

T = TypeVar("T")

#: Weights are author-written decimals, but choosing by them must be identical
#: on every platform, so they are scaled to integers and the arithmetic is
#: integer arithmetic. Six places is far finer than any authored weight.
WEIGHT_SCALE = 1_000_000

#: One stream's position: its name, and the generator state to resume from.
StreamSnapshot = tuple[str, int, int, int]


class RandomStream:
    """One named stream of random numbers.

    Parameters
    ----------
    name : str
        The stream's name, for snapshots and debugging.
    generator : Pcg64
        The underlying generator.
    """

    __slots__ = ("_generator", "name")

    def __init__(self, name: str, generator: Pcg64) -> None:
        self.name = name
        self._generator = generator

    @property
    def position(self) -> int:
        """How far into the stream we are.

        Returns
        -------
        int
            The number of values drawn so far.
        """
        return self._generator.draws

    def uint64(self) -> int:
        """Draw a raw 64-bit value.

        Returns
        -------
        int
            A value in [0, 2**64).
        """
        return self._generator.next_uint64()

    def fraction(self) -> float:
        """Draw a value in [0, 1).

        Uses the top 53 bits, which is exactly a double's mantissa, so the
        result is representable without rounding on any IEEE-754 platform.

        Returns
        -------
        float
            A value in [0, 1).
        """
        return (self._generator.next_uint64() >> 11) * (2.0**-53)

    def below(self, bound: int) -> int:
        """Draw an integer in [0, bound).

        Rejection-sampled rather than taken modulo, because modulo would favour
        the low end of the range — slightly, invisibly, and forever.

        Parameters
        ----------
        bound : int
            The exclusive upper bound. Must be positive.

        Returns
        -------
        int
            A value in [0, bound).

        Raises
        ------
        ValueError
            If the bound is not positive.
        """
        if bound <= 0:
            raise ValueError(f"bound must be positive, got {bound}")
        threshold = (-bound) % bound
        while True:
            drawn = self._generator.next_uint64()
            if drawn >= threshold:
                return drawn % bound

    def between(self, low: int, high: int) -> int:
        """Draw an integer in [low, high], inclusive at both ends.

        Parameters
        ----------
        low, high : int
            The bounds. `low` must not exceed `high`.

        Returns
        -------
        int
            A value in [low, high].

        Raises
        ------
        ValueError
            If the range is empty.
        """
        if low > high:
            raise ValueError(f"empty range: {low} to {high}")
        return low + self.below(high - low + 1)

    def chance(self, probability: float) -> bool:
        """Decide something that happens with a given probability.

        Parameters
        ----------
        probability : float
            0 never happens, 1 always does. Values outside [0, 1] are clamped,
            because a content mistake should not consume a draw differently.

        Returns
        -------
        bool
            Whether it happened.
        """
        if probability <= 0.0:
            return False
        if probability >= 1.0:
            return True
        threshold = round(probability * WEIGHT_SCALE)
        return self.below(WEIGHT_SCALE) < threshold

    def choice(self, options: Sequence[T]) -> T:
        """Pick one of several equally likely options.

        Parameters
        ----------
        options : sequence
            What to choose from. Order matters: it is part of the seed's
            meaning, so a stable order is the caller's responsibility.

        Returns
        -------
        object
            One element.

        Raises
        ------
        ValueError
            If there is nothing to choose from.
        """
        if not options:
            raise ValueError("nothing to choose from")
        return options[self.below(len(options))]

    def weighted(self, options: Sequence[tuple[T, float]]) -> T:
        """Pick one option, in proportion to its weight.

        Weights are scaled to integers first: an encounter table that resolves
        one way in Python and another in a browser is not a table anyone can
        balance.

        Parameters
        ----------
        options : sequence of (object, float)
            Options and their relative weights. Non-positive weights are
            ignored rather than treated as an error — an entry weighted 0 is a
            legitimate way to disable one.

        Returns
        -------
        object
            The chosen option.

        Raises
        ------
        ValueError
            If nothing has a positive weight.
        """
        scaled = [
            (option, round(weight * WEIGHT_SCALE))
            for option, weight in options
            if weight > 0
        ]
        scaled = [(option, weight) for option, weight in scaled if weight > 0]
        total = sum(weight for _option, weight in scaled)
        if total <= 0:
            raise ValueError("no option has a positive weight")

        roll = self.below(total)
        for option, weight in scaled:
            if roll < weight:
                return option
            roll -= weight
        return scaled[-1][0]  # pragma: no cover — unreachable while total is exact

    def shuffled(self, items: Iterable[T]) -> list[T]:
        """Return the items in a random order.

        A Fisher-Yates shuffle, written out rather than borrowed, so a port can
        match it draw for draw.

        Parameters
        ----------
        items : iterable
            What to shuffle. Not modified.

        Returns
        -------
        list
            A new list in shuffled order.
        """
        shuffled = list(items)
        for index in range(len(shuffled) - 1, 0, -1):
            swap = self.below(index + 1)
            shuffled[index], shuffled[swap] = shuffled[swap], shuffled[index]
        return shuffled

    def snapshot(self) -> StreamSnapshot:
        """Capture the stream's position.

        Returns
        -------
        tuple
            The name and generator state, for a save file.
        """
        return (self.name, *self._generator.state)


class RandomSource:
    """The seeded service every stream comes from.

    Streams are made on first use and kept, so asking for `weather` twice in one
    session gets the same stream at the position it was left at — not a fresh
    one replaying the same numbers.

    Parameters
    ----------
    seed : str
        The session seed. Anything printable; it is hashed with the stream name.
    """

    __slots__ = ("_streams", "seed")

    def __init__(self, seed: str) -> None:
        self.seed = seed
        self._streams: dict[str, RandomStream] = {}

    def stream(self, name: str) -> RandomStream:
        """Get a named stream, making it if this is its first use.

        Parameters
        ----------
        name : str
            The stream's name. Dotted, by convention: `encounters.north-road`.

        Returns
        -------
        RandomStream
            The stream, at whatever position it has reached.
        """
        existing = self._streams.get(name)
        if existing is not None:
            return existing

        initial_state, sequence = derive_seed(self.seed, name)
        stream = RandomStream(name, Pcg64.seeded(initial_state, sequence))
        self._streams[name] = stream
        return stream

    @property
    def names(self) -> tuple[str, ...]:
        """The streams used so far.

        Returns
        -------
        tuple of str
            Names, sorted, so a snapshot never depends on use order.
        """
        return tuple(sorted(self._streams))

    def snapshot(self) -> tuple[StreamSnapshot, ...]:
        """Capture every stream's position.

        Returns
        -------
        tuple
            One entry per stream used, sorted by name.
        """
        return tuple(self._streams[name].snapshot() for name in self.names)

    @classmethod
    def restore(cls, seed: str, snapshot: Iterable[StreamSnapshot]) -> RandomSource:
        """Rebuild a source from a save file.

        Parameters
        ----------
        seed : str
            The session seed.
        snapshot : iterable
            Entries from `snapshot`.

        Returns
        -------
        RandomSource
            A source whose streams carry on where they left off.
        """
        source = cls(seed)
        for name, state, increment, draws in snapshot:
            source._streams[name] = RandomStream(
                name, Pcg64.restore((state, increment, draws))
            )
        return source

    def positions(self) -> Mapping[str, int]:
        """How far each stream has been drawn from.

        Useful in tests: it is the cheapest way to prove one subsystem's rolls
        did not disturb another's.

        Returns
        -------
        mapping
            Stream name to draw count.
        """
        return {name: self._streams[name].position for name in self.names}
