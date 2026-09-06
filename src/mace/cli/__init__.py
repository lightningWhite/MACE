"""The terminal front-end: `mace play` and `mace author`.

A front-end's entire job is turning engine events into characters, and turning
input into actions. It must never reach into engine internals.
See docs/10-clients-and-interface.md.
"""

from mace.cli.main import main

__all__ = ["main"]
