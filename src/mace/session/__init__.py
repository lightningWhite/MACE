"""The session layer: owns a running game.

Applies actions, emits events, snapshots and restores saves, and projects a
read-only view-model for front-ends. The boundary between the pure engine and
the impure outside world. See docs/02-architecture.md.
"""
