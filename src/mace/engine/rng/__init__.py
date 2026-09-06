"""Named, independently-seeded random streams.

Never call `random` directly anywhere in the engine — take a stream from the
seeded RNG service (`rng.stream("weather")`) so subsystems cannot desync each
other's sequences. New subsystem, new stream.
See docs/decisions/0004-deterministic-seeded-simulation.md.
"""

from mace.engine.rng.pcg import Pcg64, derive_seed
from mace.engine.rng.streams import (
    WEIGHT_SCALE,
    RandomSource,
    RandomStream,
    StreamSnapshot,
)

__all__ = [
    "Pcg64",
    "RandomSource",
    "RandomStream",
    "StreamSnapshot",
    "WEIGHT_SCALE",
    "derive_seed",
]
