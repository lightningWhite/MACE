"""The engine, driven from inside a browser tab.

The third front-end, and the one with no network between it and the player.
`mace.cli` renders to a terminal, `mace.api` renders to HTTP, and this renders
to whatever JavaScript is holding it — which under Pyodide is a Web Worker
(`web/src/local/`).

It is the same shape as the service on purpose. Both hand out the frame that
`mace.session.frame` builds, so a client cannot tell which one it is talking
to, and neither can a bug report. What differs is only what a front-end can
*be*: there is no registry here, because a tab plays one game at a time, and
no eviction, because nothing is competing for the memory.

There are no imports here that a browser cannot satisfy — stdlib, pydantic and
a YAML reader — which is the constraint ADR-0005 exists to keep, and the
reason this module is in the package rather than written in JavaScript beside
the worker that calls it.
"""

from __future__ import annotations

import json
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

from mace.content import ContentError, Library, load_library
from mace.engine.actions import decode
from mace.engine.conditions import RuleError
from mace.engine.creation import Character
from mace.engine.creation import offer as creation_offer
from mace.session import Save, Session, choose_game, frame, resume

__all__ = ["MANIFEST", "Runtime", "unpack"]

#: The manifest `mace bundle` writes into the zip.
MANIFEST = "bundle.json"

#: What a tab's one playthrough is called. There is only ever one, so the id
#: is a constant rather than a secret — nothing is being addressed across a
#: network here, and a token would only be theatre.
ONLY = "local"


def unpack(archive: bytes, into: Path) -> list[Path]:
    """Extract a bundle and say where its packs landed.

    Parameters
    ----------
    archive : bytes
        A zip written by `mace bundle`.
    into : Path
        Where to extract it. Under Pyodide this is the virtual filesystem.

    Returns
    -------
    list of Path
        The pack directories, in the order the manifest lists them.

    Raises
    ------
    ContentError
        If it is not a bundle, or does not say what is in it.
    """
    try:
        with zipfile.ZipFile(BytesIO(archive)) as opened:
            opened.extractall(into)
            manifest = json.loads(opened.read(MANIFEST))
    except (zipfile.BadZipFile, KeyError, ValueError) as error:
        raise ContentError(f"this is not a MACE bundle: {error}") from error

    return [into / inside for inside in manifest["packs"]]


class Runtime:
    """A tab's engine: content loaded once, one playthrough at a time.

    Attributes
    ----------
    library : Library
        The loaded content.
    session : Session or None
        The playthrough, once one has been opened.
    """

    def __init__(self, library: Library) -> None:
        self.library = library
        self.session: Session | None = None

    @classmethod
    def load(cls, root: str | Path) -> Runtime:
        """Load an already-unpacked bundle.

        The worker's entry point, and it takes an unpacked directory rather
        than the zip for a plain reason: `mace` has to be on `sys.path` before
        anything here can be imported, so whoever extracted the archive has
        already done the extracting. `zipfile` is stdlib, so that costs them
        four lines and this module a chicken-and-egg problem.

        Parameters
        ----------
        root : str or Path
            Where the bundle was extracted.

        Returns
        -------
        Runtime
            Ready to open a game.

        Raises
        ------
        ContentError
            If there is no manifest, or the packs will not load.
        """
        here = Path(root)
        try:
            manifest = json.loads((here / MANIFEST).read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ContentError(f"no MACE bundle at {here}: {error}") from error
        return cls(load_library(*(here / inside for inside in manifest["packs"])))

    @classmethod
    def install(cls, archive: bytes, into: str | Path = "/mace") -> Runtime:
        """Unpack a bundle and load everything in it.

        Parameters
        ----------
        archive : bytes
            A zip written by `mace bundle`.
        into : str or Path
            Where to put it.

        Returns
        -------
        Runtime
            Ready to open a game.

        Raises
        ------
        ContentError
            If the bundle is not one, or its packs will not load.
        """
        unpack(archive, Path(into))
        return cls.load(into)

    def handle(self, request: dict[str, Any]) -> Any:
        """Answer one request from whatever is holding this runtime.

        The dispatch lives here rather than in the worker so that the
        JavaScript side is glue and nothing else: it fetches two files and
        passes JSON through. Everything that could be wrong about a request is
        wrong in a language this project has tests in.

        Parameters
        ----------
        request : dict
            `{"type": ...}` plus whatever that type needs. The types are the
            service's routes by another name — `games`, `creation`, `open`,
            `act`, `look`, `save`.

        Returns
        -------
        object
            JSON-safe.

        Raises
        ------
        ContentError
            If the request names nothing, or cannot be carried out.
        """
        kind = request.get("type")
        if kind == "games":
            return self.games()
        if kind == "creation":
            return self.creation(str(request["pack"]), request.get("background"))
        if kind == "open":
            return self.open(request.get("request") or {})
        if kind == "act":
            return self.act(dict(request["action"]))
        if kind == "look":
            return self.look()
        if kind == "save":
            return self.save()

        known = "games, creation, open, act, look, save"
        raise ContentError(f"unknown request `{kind}`; this runtime does: {known}")

    # ── What there is to play ─────────────────────────────────────────────

    def games(self) -> dict[str, Any]:
        """List the playable packs.

        Returns
        -------
        dict
            The same body `GET /api/games` returns.
        """
        return {
            "games": [
                {
                    "id": pack.id,
                    "name": pack.manifest.name,
                    "version": str(pack.manifest.version),
                    "description": pack.manifest.description,
                }
                for pack in self.library.games
            ]
        }

    def creation(self, pack: str, background: str | None = None) -> dict[str, Any]:
        """The character-creation question, if the game asks one.

        Parameters
        ----------
        pack : str
            The game pack.
        background : str or None
            A background already chosen, so the stats are the ones the player
            will actually start with.

        Returns
        -------
        dict
            The same body `GET /api/games/{pack}/creation` returns.
        """
        return creation_offer(self.library, pack, background=background).record()

    # ── Playing ───────────────────────────────────────────────────────────

    def open(self, request: dict[str, Any] | None = None) -> dict[str, Any]:
        """Start a playthrough, or carry a saved one on.

        Parameters
        ----------
        request : dict or None
            `{pack, seed, combatMode, timePressure, character}`, or `{save}`
            to resume. The same body `POST /api/sessions` takes.

        Returns
        -------
        dict
            The opening frame, with any warnings the save raised.

        Raises
        ------
        ContentError
            If the content will not open it, or the save will not replay.
        """
        asked = request or {}
        drift: list[str] = []

        saved = asked.get("save")
        if saved is not None:
            self.session, drift = resume(Save.restore(saved), self.library)
        else:
            made = asked.get("character")
            self.session = Session.begin(
                self.library,
                choose_game(self.library, asked.get("pack")),
                seed=str(asked.get("seed", "mace")),
                combat_mode=asked.get("combatMode"),
                time_pressure=float(asked.get("timePressure", 1.0)),
                character=(
                    None
                    if made is None
                    else Character(
                        background=made.get("background"),
                        spend=dict(made.get("spend") or {}),
                    )
                ),
            )

        return {**frame(ONLY, self.session), "warnings": drift}

    def act(self, action: dict[str, Any]) -> dict[str, Any]:
        """Do one thing.

        Parameters
        ----------
        action : dict
            An action record.

        Returns
        -------
        dict
            The frame the action produced.

        Raises
        ------
        ContentError
            If nothing has been opened, or the action means nothing here.
        """
        session = self._playing()
        try:
            session.perform(decode(dict(action), offered=session.offered))
        except (ValueError, RuleError) as error:
            raise ContentError(str(error)) from error
        return frame(ONLY, session)

    def look(self) -> dict[str, Any]:
        """Where the playthrough stands, and what it last said.

        Returns
        -------
        dict
            The frame.

        Raises
        ------
        ContentError
            If nothing has been opened.
        """
        return frame(ONLY, self._playing())

    def save(self) -> dict[str, Any]:
        """The playthrough as a save file.

        Returns
        -------
        dict
            The save record.

        Raises
        ------
        ContentError
            If nothing has been opened.
        """
        return Save.of(self._playing()).record()

    def _playing(self) -> Session:
        """The open playthrough, or a plain complaint that there is none.

        Returns
        -------
        Session
            The playthrough.

        Raises
        ------
        ContentError
            If nothing has been opened.
        """
        if self.session is None:
            raise ContentError("no game is open — open one first")
        return self.session
