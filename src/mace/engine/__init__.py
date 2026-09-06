"""The engine core: pure, deterministic simulation.

`state -> rules -> (state, events)`. This package may not print, prompt, read
stdin, touch the filesystem or network, read the wall clock, call `random`
directly, or mutate content models. Everything it needs is passed in; everything
it produces comes back as a return value.

Same content + same seed + same action log = byte-identical outcome. Always.
See docs/02-architecture.md.
"""

# Deliberately no re-exports. `mace.model` imports `mace.engine.expr` to parse
# author expressions at validation time, so importing this package must not
# pull in anything that reaches back into `mace.content` — import
# `mace.engine.step`, `mace.engine.actions`, and friends directly.
