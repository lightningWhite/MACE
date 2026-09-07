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

**Every object stays in its file, in its place, with its comments.** The
project holds the *loaded documents*, not detached copies of the objects in
them, and an edit mutates the document. So an author who organised their world
into `locations.yml` and `people.yml` keeps that arrangement, objects keep the
order they were written in, and the paragraph of explanation at the top of the
file is still there afterwards. Rebuilding a file from its objects — the
obvious implementation — is precisely what loses that paragraph, because it
belongs to the document rather than to anything in it.

**Compiling never touches the disk.** `compile()` builds from what is in
memory, so "playtest from anywhere, unsaved changes included" is true rather
than approximately true.

See docs/09-authoring-and-wizard.md and open question 8.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, MutableMapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from mace.content import ContentError, Library, load_pack_manifest
from mace.content.discovery import MANIFEST_NAME, content_files, find_packs
from mace.content.library import COLLECTION_MODELS
from mace.content.loader import Loaded, compile_pack, load_library
from mace.content.tolerance import collecting
from mace.content.validation import Report, as_problem, validate_library
from mace.content.writing import document, load_document, write_document
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

    `data` is the object *inside* its document rather than a copy of it, so
    editing it and dumping the document is how a change reaches disk.

    Attributes
    ----------
    data : mapping
        Exactly what the author wrote, `extends` and merge sentinels included.
    home : Path
        The file it is written to, relative to the pack root.
    """

    data: MutableMapping[str, Any]
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
    documents : dict
        File, relative to the pack root, to the document read from it —
        comments, key order, and quoting included. This is what gets written
        back; `objects` indexes into it.
    objects : dict
        Collection name to local id to the object held there.
    unmodelled : dict
        Collections no model covers yet, kept exactly as written so a later
        phase can model them without an author losing work in the meantime.
    game : mapping or None
        The `game:` manifest's raw body, read from and written to its document.
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
    documents: dict[Path, MutableMapping[str, Any]] = field(default_factory=dict)
    objects: dict[str, dict[str, Held]] = field(default_factory=dict)
    unmodelled: dict[str, tuple[Any, ...]] = field(default_factory=dict)
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
                body = load_document(path)
            except ContentError as error:
                # A file that will not parse is a file the wizard cannot edit.
                # It stays on disk untouched and is reported on every compile,
                # which is the only honest thing to do with content it cannot
                # read: silently skipping it would leave the author wondering
                # why the locations they wrote do not exist.
                self.unreadable.append(error)
                continue
            if not isinstance(body, MutableMapping):
                continue
            home = path.relative_to(self.root)
            self.documents[home] = body
            for collection, entries in body.items():
                if collection == GAME_KEY:
                    self.game_home = home
                elif collection in UNMODELLED_COLLECTIONS:
                    kept = self.unmodelled.get(collection, ())
                    self.unmodelled[collection] = (*kept, *(entries or ()))
                elif collection in COLLECTION_MODELS:
                    self._hold(str(collection), entries, home)
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
            # Mutable, because editing an object means editing the one sitting
            # in its document. A read-only mapping in a content file would be
            # something the wizard could show and never change.
            if isinstance(entry, MutableMapping) and "id" in entry:
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

        if existing is not None:
            # Mutate the object that is already in the document, so a comment
            # on a key the author did not touch is still there afterwards.
            _overwrite(existing.data, authored)
            self.dirty.add(existing.home)
            return local_id

        home = self._home_for(collection)
        entries = self._collection(home, collection)
        fresh = document(authored)
        entries.append(fresh)
        _space_before(entries)
        held[local_id] = Held(fresh, home)
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
        entries = self.documents.get(gone.home, {}).get(collection)
        if isinstance(entries, list):
            entries[:] = [entry for entry in entries if entry is not gone.data]
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

    def lineage(
        self, collection: str, local_id: str
    ) -> tuple[tuple[Mapping[str, Any], ...], Any]:
        """An object and everything it inherits from, in lookup order.

        `extends` is resolved by the loader, which means it does not exist as
        far as the raw mappings are concerned — and an author who wrote
        `extends: fantasy.core:soldier` and never wrote `kind` has still said
        their character is an actor. Anything asking what an object *is*
        rather than what its file *says* needs this.

        The chain stops at the first ancestor that lives in a dependency,
        because a compiled definition already has its own inheritance resolved.

        Parameters
        ----------
        collection : str
            Which collection.
        local_id : str
            The object's id in this pack.

        Returns
        -------
        tuple of (tuple of mapping, object or None)
            The authored mappings, nearest first, and the compiled ancestor
            that ends the chain, if there is one.
        """
        chain: list[Mapping[str, Any]] = []
        seen: set[str] = set()
        current = self.objects.get(collection, {}).get(local_id)
        while current is not None and local_id not in seen:
            seen.add(local_id)
            chain.append(current.data)
            parent = current.data.get("extends")
            if not isinstance(parent, str):
                return tuple(chain), None
            pack_id, _, local_id = parent.rpartition(":")
            if pack_id not in {"", self.manifest.id}:
                return tuple(chain), self._from_dependency(collection, parent)
            current = self.objects.get(collection, {}).get(local_id)
            if current is None:
                return tuple(chain), self._from_dependency(collection, parent)
        return tuple(chain), None

    def _from_dependency(self, collection: str, reference: str) -> Any:
        """Look a reference up in the packs this one builds on.

        Parameters
        ----------
        collection : str
            Which collection.
        reference : str
            The reference, qualified or bare.

        Returns
        -------
        object or None
            The compiled definition, or None when nothing matches.
        """
        pack_id, _, local_id = reference.rpartition(":")
        for pack in self.dependencies.packs:
            if pack_id in {"", pack.id}:
                found = pack.collection(collection).get(local_id)
                if found is not None:
                    return found
        return None

    def effective(self, collection: str, local_id: str, key: str) -> Any:
        """What an object holds for one top-level field, inheritance included.

        Parameters
        ----------
        collection : str
            Which collection.
        local_id : str
            The object's id.
        key : str
            The authored key.

        Returns
        -------
        object
            The value, or None when neither the object nor its ancestors set
            it. The model's own default is deliberately not applied here —
            callers that want it know which model they are looking at.
        """
        chain, ancestor = self.lineage(collection, local_id)
        for data in chain:
            if key in data:
                return data[key]
        return None if ancestor is None else getattr(ancestor, key, None)

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

    @property
    def game(self) -> Mapping[str, Any] | None:
        """The `game:` manifest, as it was authored.

        Returns
        -------
        mapping or None
            The manifest body, or None for a pack that has none yet.
        """
        held = self.documents.get(self.game_home)
        found = None if held is None else held.get(GAME_KEY)
        return found if isinstance(found, Mapping) else None

    def set_game(self, authored: Mapping[str, Any]) -> None:
        """Replace the `game:` manifest.

        Parameters
        ----------
        authored : mapping
            The manifest, as it would be written.
        """
        body = self._file(self.game_home)
        existing = body.get(GAME_KEY)
        if isinstance(existing, MutableMapping):
            _overwrite(existing, authored)
        else:
            body[GAME_KEY] = dict(authored)
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
                write_document(self.root / home, self.documents[home])
            written.append(home)
        self.dirty.clear()
        return written

    def _home_for(self, collection: str) -> Path:
        """Which file a new object of some collection should join.

        Wherever the author already keeps that collection, when they keep it in
        one place — a pack whose scenes live in `story.yml` should not sprout a
        `scenes.yml` the first time the wizard adds one. Split across several
        files, there is no right answer and a file named for the collection is
        the least surprising one.

        Parameters
        ----------
        collection : str
            The collection.

        Returns
        -------
        Path
            The file, relative to the pack root.
        """
        homes = {held.home for held in self.objects.get(collection, {}).values()}
        if len(homes) == 1:
            return homes.pop()
        return Path(f"{collection}.yml")

    def _file(self, home: Path) -> MutableMapping[str, Any]:
        """The document for one file, started if there is not one yet.

        Parameters
        ----------
        home : Path
            The file, relative to the pack root.

        Returns
        -------
        mutable mapping
            The document.
        """
        found = self.documents.get(home)
        if found is None:
            found = document()
            self.documents[home] = found
        return found

    def _collection(self, home: Path, collection: str) -> list[Any]:
        """The list one collection's objects live in, started if it is absent.

        Parameters
        ----------
        home : Path
            The file, relative to the pack root.
        collection : str
            The collection.

        Returns
        -------
        list
            The list inside the document, which new objects are appended to so
            they land after what the author already wrote.
        """
        body = self._file(home)
        entries = body.get(collection)
        if not isinstance(entries, list):
            entries = []
            body[collection] = entries
        return entries

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


def _space_before(entries: list[Any]) -> None:
    """Put a blank line before the entry just appended.

    Cosmetic, and worth it: every pack in the repo separates its definitions
    with a blank line, and a wizard whose additions are visibly the tool's
    rather than the author's is a wizard people write around.

    Parameters
    ----------
    entries : list
        The collection's list, with the new entry already on the end.
    """
    spacer = getattr(entries, "yaml_set_comment_before_after_key", None)
    if spacer is not None and len(entries) > 1:
        spacer(len(entries) - 1, before="\n")


def _overwrite(target: MutableMapping[str, Any], incoming: Mapping[str, Any]) -> None:
    """Make one mapping hold exactly what another does, in place.

    In place rather than by replacement, because the object being edited is the
    one sitting in its document with its comments attached. A key the author
    did not touch keeps the note they wrote beside it; a key they removed takes
    its note with it, which is the right thing for a note about something that
    is no longer there.

    Parameters
    ----------
    target : mutable mapping
        The object in the document.
    incoming : mapping
        What it should hold now.
    """
    for key in [key for key in target if key not in incoming]:
        del target[key]
    for key, value in incoming.items():
        if target.get(key) != value:
            target[key] = value


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
