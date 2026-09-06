"""PCG64, written out in full because a second implementation has to match it.

The engine may not call `random`: Python's Mersenne Twister is an
implementation detail of one runtime, and a TypeScript port of this engine
would have no way to reproduce it. PCG64 is a published algorithm small enough
to write in fifty lines and identical in any language that has 128-bit integer
arithmetic — which, in Python, every integer is.

This is the XSL-RR 128/64 variant, the one usually just called `pcg64`.
See docs/decisions/0004-deterministic-seeded-simulation.md.
"""

from __future__ import annotations

import hashlib

__all__ = ["Pcg64", "derive_seed"]

_MASK_64 = (1 << 64) - 1
_MASK_128 = (1 << 128) - 1

#: The PCG64 LCG multiplier, from the reference implementation.
_MULTIPLIER = 47026247687942121848144207491837523525


class Pcg64:
    """A single PCG64 generator.

    Two generators with the same state and increment produce the same sequence,
    on any platform and in any language, which is the whole point.

    Parameters
    ----------
    state : int
        The 128-bit LCG state.
    increment : int
        The 128-bit stream increment. Forced odd, as PCG requires.
    """

    __slots__ = ("_increment", "_state", "_draws")

    def __init__(self, state: int, increment: int) -> None:
        self._increment = (increment | 1) & _MASK_128
        self._state = state & _MASK_128
        self._draws = 0

    @classmethod
    def seeded(cls, initial_state: int, sequence: int) -> Pcg64:
        """Build a generator the way the reference implementation seeds one.

        Parameters
        ----------
        initial_state : int
            Seed material for the state.
        sequence : int
            Seed material for the stream increment.

        Returns
        -------
        Pcg64
            A generator ready to draw from.
        """
        generator = cls(0, (sequence << 1) | 1)
        generator._advance()
        generator._state = (generator._state + initial_state) & _MASK_128
        generator._advance()
        generator._draws = 0
        return generator

    @property
    def draws(self) -> int:
        """How many numbers have been taken from this generator.

        Returns
        -------
        int
            The draw count, which is the stream's position in the state.
        """
        return self._draws

    @property
    def state(self) -> tuple[int, int, int]:
        """The generator's full position, for snapshots.

        Returns
        -------
        tuple of (int, int, int)
            State, increment, and draw count.
        """
        return self._state, self._increment, self._draws

    @classmethod
    def restore(cls, state: tuple[int, int, int]) -> Pcg64:
        """Rebuild a generator from a snapshot.

        Parameters
        ----------
        state : tuple of (int, int, int)
            A tuple from `state`.

        Returns
        -------
        Pcg64
            A generator that will carry on exactly where the other stopped.
        """
        lcg_state, increment, draws = state
        generator = cls(lcg_state, increment)
        generator._draws = draws
        return generator

    def next_uint64(self) -> int:
        """Draw the next 64-bit value.

        Returns
        -------
        int
            A value in [0, 2**64).
        """
        # Step first, then output from the new state — the order the reference
        # implementation uses. Getting this backwards produces a sequence that
        # is just as random and matches no other implementation of PCG64.
        self._advance()
        self._draws += 1

        state = self._state
        xorshifted = ((state >> 64) ^ state) & _MASK_64
        rotation = state >> 122
        return ((xorshifted >> rotation) | (xorshifted << (-rotation & 63))) & _MASK_64

    def _advance(self) -> None:
        """Step the underlying linear congruential generator."""
        self._state = (self._state * _MULTIPLIER + self._increment) & _MASK_128


def derive_seed(root_seed: str, stream_name: str) -> tuple[int, int]:
    """Derive one stream's seed material from the session seed and its name.

    SHA-256 rather than Python's `hash`, which is randomized per process and
    would make a "deterministic" engine reproducible only within one run. The
    digest is split into state and sequence halves, so two stream names never
    share a sequence.

    Parameters
    ----------
    root_seed : str
        The session seed.
    stream_name : str
        The stream's name, e.g. `encounters.north-road`.

    Returns
    -------
    tuple of (int, int)
        Initial state and stream sequence, 128 bits each.
    """
    digest = hashlib.sha256(f"{root_seed}\x00{stream_name}".encode()).digest()
    return (
        int.from_bytes(digest[:16], "big"),
        int.from_bytes(digest[16:], "big"),
    )
