"""The Project: a pack being written, rather than a pack being played.

A `Library` is finished content — immutable, validated, and useless to an
author halfway through a sentence. A `Project` is the other thing: the raw
authored mappings, editable, compiled on demand, and perfectly willing to be
wrong for a while.

Three rules shape it.

**The YAML is canonical.** Objects are held as the mappings an author wrote,
not as validated models, so an object the models would reject is still
something the wizard can hold, show, and let you fix. Compiling is something
that happens *to* the raw content, repeatedly, and never something the raw
content has to survive.

**Every object remembers its file.** An author who organised their world into
`locations.yml` and `people.yml` keeps that arrangement; the wizard writes each
object back where it came from and creates a file named for the collection only
when there is nowhere to put a new one. Saving rewrites only files that
actually changed, which is what keeps a hand-written pack's comments alive
everywhere the wizard has not been.

**Compiling never touches the disk.** `compile()` builds from what is in
memory, so "playtest from anywhere, unsaved changes included" is true rather
than approximately true.

See docs/09-authoring-and-wizard.md and open question 8.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from mace.content import ContentError, Library, load_pack_manifest
from mace.content.discovery import MANIFEST_NAME, content_files, find_packs, read_yaml
from mace.content.library import COLLECTION_MODELS
from mace.content.loader import Loaded, compile_pack, load_library
from mace.content.tolerance import collecting
from mace.content.validation import Report, as_problem, validate_library
from mace.content.writing import write_document
from mace.model import Pack
from mace.model.jsonschema import UNMODELLED_COLLECTIONS
from mace.wizard.notes import ProjectNotes

__all__ = ["NOTES_PATH", "Project"]

#: Where the authoring sidecar lives, relative to the pack root.
NOTES_PATH = Path(".mace") / "project.yml"

#: The key the sidecar's body sits under, matching how `game:` works.
NOTES_KEY = "project"

#: A content file's top-level key for the game manifest.
GAME_KEY = "game"


@dataclass(slots=True)
class Held:
    """One authored object, and the file it belongs in.

    Attributes
    ----------
    data : mapping
        Exactly what the author wrote, `extends` and merge sentinels included.
    home : Path
        The file it is written to, relative to the pack root.
    """

    data: Mapping[str, Any]
    home: Path


@dataclass(slots=True)
class Project:
    """A pack open for editing.

    Attributes
    ----------
    root : Path
        The pack directory.
    manifest : Pack
        The pack's `pack.yml`.
    objects : dict
        Collection name to local id to the object held there.
    unmodelled : dict
        Collections no model covers yet, kept exactly as written so a later
        phase can model them without an author losing work in the meantime.
    game : mapping or None
        The `game:` manifest's raw body.
    game_home : Path
        Which file the game manifest is written to.
    notes : ProjectNotes
        The authoring sidecar.
    dependencies : Library
        The packs this one builds on, already loaded.
    unreadable : list of ContentError
        Files that would not parse. They are left exactly as they are — the
        wizard cannot edit what it cannot read — but they are reported on
        every compile, because an author who is never told is an author who
        wonders why their new location does not exist.
    dirty : set of Path
        Files changed since the last save, relative to the pack root.
    """

    root: Path
    manifest: Pack
    objects: dict[str, dict[str, Held]] = field(default_factory=dict)
    unmodelled: dict[str, tuple[Any, ...]] = field(default_factory=dict)
    game: Mapping[str, Any] | None = None
    game_home: Path = Path("game.yml")
    notes: ProjectNotes = field(default_factory=ProjectNotes)
    dependencies: Library = field(default_factory=lambda: Library(()))
    unreadable: list[ContentError] = field(default_factory=list)
    dirty: set[Path] = field(default_factory=set)

    # ── Opening and creating ──────────────────────────────────────────────

    @classmethod
    def open(cls, root: Path, *search: Path) -> Project:
        """Read a pack off disk, ready to edit.

        Parameters
        ----------
        root : Path
            The pack directory.
        *search : Path
            Where this pack's dependencies live. Loaded best-effort: a
            dependency that will not compile is a problem to report, not a
            reason the author cannot open their own work.

        Returns
        -------
        Project
            The pack, held as raw authored mappings.

        Raises
        ------
        ContentError
            If there is no readable `pack.yml`. Everything else is survivable;
            not knowing which pack this is, is not.
        """
        manifest = load_pack_manifest(root)
        project = cls(
            root=root,
            manifest=manifest,
            dependencies=_dependencies(manifest, root, search),
        )
        project._read()
        return project

    @classmethod
    def create(
        cls,
        root: Path,
        *search: Path,
        pack_id: str,
        name: str,
        kind: str = "game",
        requires: Mapping[str, str] | None = None,
    ) -> Project:
        """Start a new pack on disk.

        Parameters
        ----------
        root : Path
            The directory to create. Must not already be a pack.
        *search : Path
            Where dependencies live.
        pack_id : str
            The pack's namespaced id.
        name : str
            Its human-readable title.
        kind : str
            `game` or `library`.
        requires : mapping or None
            Pack id to version range.

        Returns
        -------
        Project
            The new, empty project, already written to disk.

        Raises
        ------
        ContentError
            If the directory is already a pack.
        """
        if (root / MANIFEST_NAME).exists():
            raise ContentError(f"{root} is already a pack", path=root)
        manifest = Pack.model_validate(
            {
                "id": pack_id,
                "name": name,
                "version": "0.1.0",
                "kind": kind,
                "maceVersion": "^0.1",
                "requires": [
                    {"id": needed, "version": version}
                    for needed, version in sorted((requires or {}).items())
                ],
            }
        )
        root.mkdir(parents=True, exist_ok=True)
        write_document(root / MANIFEST_NAME, manifest.authored())
        project = cls(
            root=root,
            manifest=manifest,
            dependencies=_dependencies(manifest, root, search),
        )
        project.save()
        return project

    def _read(self) -> None:
        """Load every content file into raw held objects."""
        for path in content_files(self.root):
            if path.is_relative_to(self.root / NOTES_PATH.parent):
                continue
            try:
                document = read_yaml(path)
            except ContentError as error:
                # A file that will not parse is a file the wizard cannot edit.
                # It stays on disk untouched and is reported on every compile,
                # which is the only honest thing to do with content it cannot
                # read: silently skipping it would leave the author wondering
                # why the locations they wrote do not exist.
                self.unreadable.append(error)
                continue
            if not isinstance(document, Mapping):
                continue
            home = path.relative_to(self.root)
            for collection, body in document.items():
                if collection == GAME_KEY:
                    self.game, self.game_home = body, home
                elif collection in UNMODELLED_COLLECTIONS:
                    kept = self.unmodelled.get(collection, ())
                    self.unmodelled[collection] = (*kept, *(body or ()))
                elif collection in COLLECTION_MODELS:
                    self._hold(str(collection), body, home)
        self.notes = _read_notes(self.root)

    def _hold(self, collection: str, body: Any, home: Path) -> None:
        """Index one file's objects for a collection.

        Parameters
        ----------
        collection : str
            The collection.
        body : object
            The file's value for it.
        home : Path
            The file, relative to the pack root.
        """
        if not isinstance(body, list):
            return
        held = self.objects.setdefault(collection, {})
        for entry in body:
            if isinstance(entry, Mapping) and "id" in entry:
                held.setdefault(str(entry["id"]), Held(entry, home))

    # ── Editing ───────────────────────────────────────────────────────────

    def put(self, collection: str, authored: Mapping[str, Any]) -> str:
        """Add or replace one object.

        Parameters
        ----------
        collection : str
            Which collection it belongs to.
        authored : mapping
            The object, as it would be written. Needs an `id`.

        Returns
        -------
        str
            The object's local id.

        Raises
        ------
        ContentError
            If the collection is unknown or the object has no id.
        """
        if collection not in COLLECTION_MODELS:
            raise ContentError(f"`{collection}` is not a content collection")
        if "id" not in authored:
            raise ContentError("every definition needs an `id`", collection=collection)

        local_id = str(authored["id"])
        held = self.objects.setdefault(collection, {})
        existing = held.get(local_id)
        home = existing.home if existing is not None else Path(f"{collection}.yml")
        held[local_id] = Held(dict(authored), home)
        self.dirty.add(home)
        return local_id

    def drop(self, collection: str, local_id: str) -> bool:
        """Remove one object.

        Parameters
        ----------
        collection : str
            Which collection.
        local_id : str
            The object's id.

        Returns
        -------
        bool
            Whether there was one to remove.
        """
        held = self.objects.get(collection, {})
        gone = held.pop(local_id, None)
        if gone is None:
            return False
        self.dirty.add(gone.home)
        return True

    def get(self, collection: str, local_id: str) -> Mapping[str, Any] | None:
        """Look up one object as it was authored.

        Parameters
        ----------
        collection : str
            Which collection.
        local_id : str
            The object's id.

        Returns
        -------
        mapping or None
            The authored object, or None.
        """
        held = self.objects.get(collection, {}).get(local_id)
        return None if held is None else held.data

    def ids(self, collection: str) -> list[str]:
        """Every local id in one collection, sorted.

        Parameters
        ----------
        collection : str
            Which collection.

        Returns
        -------
        list of str
            Local ids, sorted — a menu wants alphabetical even though a file
            keeps the author's own order.
        """
        return sorted(self.objects.get(collection, {}))

    def set_game(self, authored: Mapping[str, Any]) -> None:
        """Replace the `game:` manifest.

        Parameters
        ----------
        authored : mapping
            The manifest, as it would be written.
        """
        self.game = dict(authored)
        self.dirty.add(self.game_home)

    def remember(self, notes: ProjectNotes) -> None:
        """Replace the authoring sidecar.

        Parameters
        ----------
        notes : ProjectNotes
            The new sidecar.
        """
        self.notes = notes
        self.dirty.add(NOTES_PATH)

    # ── Compiling and checking ────────────────────────────────────────────

    def compile(self) -> Loaded:
        """Build what is held, without touching the disk.

        Returns
        -------
        Loaded
            A library containing this pack and its dependencies, and every
            object that would not build.
        """
        tolerance = collecting()
        pack = compile_pack(
            self.manifest,
            self.root,
            {
                collection: {name: held.data for name, held in objects.items()}
                for collection, objects in self.objects.items()
            },
            self.unmodelled,
            self.game,
            self.dependencies,
            tolerance,
            homes={
                name: self.root / held.home
                for objects in self.objects.values()
                for name, held in objects.items()
            },
            game_path=self.root / self.game_home,
        )
        library = Library((*self.dependencies.packs, pack))
        return Loaded(library, (*self.unreadable, *tolerance.problems))

    def report(self) -> Report:
        """Everything wrong with the project right now.

        Load failures first, then the validator's own findings. Never raises
        and never blocks: an author must be able to stop mid-thought.

        Returns
        -------
        Report
            The live problem list.
        """
        loaded = self.compile()
        problems = [as_problem(error) for error in loaded.problems]
        problems.extend(
            problem
            for problem in validate_library(loaded.library).problems
            if problem.pack == self.manifest.id
        )
        return Report(tuple(problems))

    # ── Saving ────────────────────────────────────────────────────────────

    def save(self) -> list[Path]:
        """Write every changed file, and nothing else.

        Only touching what changed is what lets the wizard edit a pack full of
        hand-written comments without flattening the parts it never went near.

        Returns
        -------
        list of Path
            The files written, relative to the pack root.
        """
        written: list[Path] = []
        for home in sorted(self.dirty):
            if home == NOTES_PATH:
                write_document(
                    self.root / NOTES_PATH, {NOTES_KEY: self.notes.authored()}
                )
            else:
                write_document(self.root / home, self._document(home))
            written.append(home)
        self.dirty.clear()
        return written

    def _document(self, home: Path) -> dict[str, Any]:
        """Rebuild one file from everything that lives in it.

        Parameters
        ----------
        home : Path
            The file, relative to the pack root.

        Returns
        -------
        dict
            Collection name to its objects, in the order the author had them:
            objects keep the position they were read in and new ones go on the
            end. Sorting would be tidier and would reorder somebody's
            carefully grouped file the first time the wizard touched it, which
            turns one small edit into an unreadable diff.
        """
        document: dict[str, Any] = {}
        if self.game is not None and home == self.game_home:
            document[GAME_KEY] = dict(self.game)
        for collection in COLLECTION_MODELS:
            living = [
                held.data
                for held in self.objects.get(collection, {}).values()
                if held.home == home
            ]
            if living:
                document[collection] = living
        for collection, entries in sorted(self.unmodelled.items()):
            if entries and home == Path(f"{collection}.yml"):
                document[collection] = list(entries)
        return document

    def each(self) -> Iterator[tuple[str, str, Mapping[str, Any]]]:
        """Every object in the project.

        Yields
        ------
        tuple of (str, str, mapping)
            Collection, local id, and the authored object.
        """
        for collection in COLLECTION_MODELS:
            for local_id, held in sorted(self.objects.get(collection, {}).items()):
                yield collection, local_id, held.data


def _dependencies(manifest: Pack, root: Path, search: tuple[Path, ...]) -> Library:
    """Load the packs a project builds on.

    Best-effort, and the project's own pack is excluded — a search path is
    usually `packs/`, which contains the project itself.

    Parameters
    ----------
    manifest : Pack
        The project's manifest.
    root : Path
        The project's directory, so it can be skipped.
    search : tuple of Path
        Where to look.

    Returns
    -------
    Library
        The dependency packs that loaded.
    """
    roots = [
        found
        for path in search
        for found in find_packs(path)
        if found.resolve() != root.resolve()
    ]
    if not roots:
        return Library(())
    tolerance = collecting()
    library = load_library(*roots, tolerance=tolerance)
    needed = {requirement.id for requirement in manifest.requires}
    return Library(tuple(pack for pack in library.packs if pack.id in needed))


def _read_notes(root: Path) -> ProjectNotes:
    """Read the authoring sidecar, or start a fresh one.

    Parameters
    ----------
    root : Path
        The pack directory.

    Returns
    -------
    ProjectNotes
        What the wizard remembered, or defaults.
    """
    path = root / NOTES_PATH
    if not path.is_file():
        return ProjectNotes()
    try:
        document = yaml.safe_load(path.read_text())
    except yaml.YAMLError:
        return ProjectNotes()
    if not isinstance(document, Mapping):
        return ProjectNotes()
    try:
        return ProjectNotes.model_validate(document.get(NOTES_KEY) or {})
    except ValueError:
        # A sidecar from a future wizard, or one somebody hand-edited wrong.
        # It holds notes, not work: starting fresh loses nothing that matters.
        return ProjectNotes()
