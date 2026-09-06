"""Named, independently-seeded random streams.

Never call `random` directly anywhere in the engine — take a stream from the
seeded RNG service (`rng.stream("weather")`) so subsystems cannot desync each
other's sequences. New subsystem, new stream.
See docs/decisions/0004-deterministic-seeded-simulation.md.
"""
