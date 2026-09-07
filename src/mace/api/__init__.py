"""The session service: HTTP and WebSocket over a running game.

A front-end like any other. It drives a `mace.session.Session`, hands out the
ordered event stream and the view-model, and holds no rules of its own. The
terminal and the browser tab differ in what they draw, not in what they are
allowed to know.

Importing this needs the `api` extra (`pip install 'mace[api]'`). Nothing
under `mace.engine` or `mace.content` imports it, so the engine stays
installable — and importable under Pyodide — without a web framework.

See docs/10-clients-and-interface.md.
"""

from mace.api.app import create_app
from mace.api.sessions import Registry, UnknownSession

__all__ = ["Registry", "UnknownSession", "create_app"]
