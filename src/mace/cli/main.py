"""Entry point for the `mace` console script."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from mace import __version__
from mace.cli.author import author
from mace.cli.bundle import bundle
from mace.cli.create import parse_spend
from mace.cli.play import play
from mace.content import ContentError, Severity, validate_paths
from mace.engine.creation import Character
from mace.wizard.project import Project


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser.

    Returns
    -------
    argparse.ArgumentParser
        The parser for the `mace` command.
    """
    parser = argparse.ArgumentParser(
        prog="mace",
        description="MACE — build and play text-driven adventure worlds.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"mace {__version__}",
    )
    commands = parser.add_subparsers(dest="command")

    validate = commands.add_parser(
        "validate",
        help="check content packs and report what is wrong with them",
        description=(
            "Load every pack under the given paths and report problems. "
            "Exits non-zero if anything is an error."
        ),
    )
    validate.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[Path("packs")],
        help="pack directories to check (default: packs/)",
    )
    validate.add_argument(
        "--errors-only",
        action="store_true",
        help="report only what breaks the game, hiding warnings and notes",
    )
    validate.set_defaults(run=run_validate)

    player = commands.add_parser(
        "play",
        help="play a game pack in the terminal",
        description=(
            "Load the packs under the given paths and play one of them. The "
            "same seed and the same choices replay identically."
        ),
    )
    player.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[Path("packs")],
        help="pack directories to load (default: packs/)",
    )
    player.add_argument("--pack", help="which game to play, if more than one loaded")
    player.add_argument(
        "--seed",
        default="mace",
        help="the session seed; the same seed replays the same world",
    )
    player.add_argument(
        "--combat",
        choices=["reflex", "tactical", "auto"],
        help=(
            "how combat is played: `reflex` runs a timing window, `tactical` "
            "is untimed and loses none of the reading, `auto` plays both "
            "sides. Overrides the game's own default."
        ),
    )
    player.add_argument(
        "--background",
        help=(
            "start with this background instead of being asked; the games "
            "that offer none ignore it"
        ),
    )
    player.add_argument(
        "--spend",
        nargs="*",
        default=None,
        metavar="STAT=POINTS",
        help=(
            "spend creation points without being asked, as `strength=5 "
            "speed=10`. Implies the first background unless --background says "
            "otherwise."
        ),
    )
    player.add_argument(
        "--time-pressure",
        type=float,
        default=1.0,
        metavar="X",
        help=(
            "how hard the clock presses in reflex combat. 1.0 is the fight as "
            "written; 0.5 gives twice the window and 2.0 gives half of it. For "
            "playing the reading game without that much of the reaction game."
        ),
    )
    player.add_argument(
        "--save",
        type=Path,
        metavar="FILE",
        help=(
            "write the playthrough here when it ends. A save is the packs, "
            "the seed and everything you did — small enough to send someone, "
            "exact enough for them to watch it happen."
        ),
    )
    player.add_argument(
        "--load",
        type=Path,
        metavar="FILE",
        help=(
            "carry on from a save. Its seed, combat mode and character are "
            "the session's, so --seed, --combat and --background are ignored."
        ),
    )
    player.set_defaults(run=run_play)

    server = commands.add_parser(
        "serve",
        help="serve a game over HTTP and WebSocket",
        description=(
            "Run the session service. The browser client talks to this; so "
            "does anything else that can post JSON. Sessions live in this "
            "process, and `GET /api/sessions/{id}/save` is how a client "
            "keeps one past a restart."
        ),
    )
    server.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[Path("packs")],
        help="pack directories to serve (default: packs/)",
    )
    server.add_argument(
        "--host",
        default="127.0.0.1",
        help=(
            "address to bind (default: 127.0.0.1). The service has no "
            "authentication, so binding it to the world shares every save on "
            "it with the world."
        ),
    )
    server.add_argument("--port", type=int, default=8000, help="port (default: 8000)")
    server.add_argument(
        "--client",
        type=Path,
        metavar="DIR",
        help=(
            "a built web client to serve alongside the API (usually "
            "web/dist). With one, the game and the service share an origin "
            "and there is nothing to configure; without one, run the Vite "
            "dev server and let it proxy."
        ),
    )
    server.add_argument(
        "--origin",
        action="append",
        metavar="URL",
        help=(
            "an origin a browser may call this from. Repeatable. Defaults to "
            "the Vite dev server on localhost."
        ),
    )
    server.set_defaults(run=run_serve)

    packer = commands.add_parser(
        "bundle",
        help="pack the engine and some worlds into one file for a browser",
        description=(
            "Write a zip holding the `mace` package and the content packs "
            "found under the given paths. The static web build fetches it and "
            "runs the engine in the tab, with no server at all."
        ),
    )
    packer.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[Path("packs")],
        help="pack directories to include (default: packs/)",
    )
    packer.add_argument(
        "-o",
        "--out",
        type=Path,
        default=Path("web/public/mace-bundle.zip"),
        help="where to write it (default: web/public/mace-bundle.zip)",
    )
    packer.set_defaults(run=run_bundle)

    started = commands.add_parser(
        "new",
        help="start a new content pack",
        description=(
            "Create a pack directory with a manifest, ready to author. The "
            "pack is empty: `mace author` is what fills it in."
        ),
    )
    started.add_argument("directory", type=Path, help="where to create the pack")
    started.add_argument(
        "--id",
        dest="pack_id",
        help="the pack's namespaced id (default: the directory name)",
    )
    started.add_argument("--name", help="its title (default: the directory name)")
    started.add_argument(
        "--library",
        action="store_true",
        help="make a library to build on rather than a playable game",
    )
    started.add_argument(
        "--requires",
        nargs="*",
        default=["fantasy.core"],
        metavar="PACK",
        help=(
            "packs to build on (default: fantasy.core; pass none to depend "
            "on nothing)"
        ),
    )
    started.add_argument(
        "--packs",
        type=Path,
        default=Path("packs"),
        help="where the packs it requires live (default: packs/)",
    )
    started.set_defaults(run=run_new)

    writer = commands.add_parser(
        "author",
        help="build a game without writing YAML",
        description=(
            "Open a pack in the wizard: a task list you can work through in "
            "any order, live validation, and a playtest from anywhere."
        ),
    )
    writer.add_argument("directory", type=Path, help="the pack to author")
    writer.add_argument(
        "--packs",
        type=Path,
        default=Path("packs"),
        help="where the packs it builds on live (default: packs/)",
    )
    writer.add_argument(
        "--web",
        action="store_true",
        help=(
            "serve the wizard to a browser instead of running it in this "
            "terminal. Same pack, same questions, same validator — the "
            "browser only draws them differently."
        ),
    )
    writer.add_argument(
        "--host",
        default="127.0.0.1",
        help=(
            "address to bind with --web (default: 127.0.0.1). These routes "
            "write to your disk and have no authentication, so binding them "
            "to a network hands that network your filesystem."
        ),
    )
    writer.add_argument(
        "--port", type=int, default=8000, help="port for --web (default: 8000)"
    )
    writer.add_argument(
        "--client",
        type=Path,
        metavar="DIR",
        help="a built web client to serve alongside --web (usually web/dist)",
    )
    writer.set_defaults(run=run_author)
    return parser


def run_author(options: argparse.Namespace) -> int:
    """Run `mace author`.

    Parameters
    ----------
    options : argparse.Namespace
        Parsed arguments.

    Returns
    -------
    int
        The process exit code.
    """
    if not options.web:
        return author(options.directory, options.packs)
    return _author_on_the_web(options)


def _author_on_the_web(options: argparse.Namespace) -> int:
    """Serve the wizard to a browser rather than to this terminal.

    One pack per process, the way the terminal is one pack per window: a
    project holds unsaved edits in memory, and two behind one process would be
    two authors overwriting each other.

    Parameters
    ----------
    options : argparse.Namespace
        Parsed arguments.

    Returns
    -------
    int
        The process exit code.
    """
    try:
        import uvicorn  # noqa: PLC0415

        from mace.api.app import DEV_ORIGINS, create_app  # noqa: PLC0415
    except ImportError:
        print(
            "error   the wizard's web mode needs the server extras: "
            "pip install 'mace[api]'",
            file=sys.stderr,
        )
        return 1

    from mace.wizard.studio import Studio  # noqa: PLC0415

    try:
        studio = Studio.open(options.directory, options.packs)
        app = create_app(
            [options.packs],
            origins=list(DEV_ORIGINS),
            client=options.client,
            authoring=studio,
        )
    except ContentError as error:
        print(f"error   {error}", file=sys.stderr)
        return 1

    where = f"http://{options.host}:{options.port}"
    print(f"Authoring {studio.project.manifest.name} on {where} — ctrl-c to stop")
    if options.host not in {"127.0.0.1", "localhost", "::1"}:
        print(
            "warning these routes write to your disk and have no " "authentication.",
            file=sys.stderr,
        )
    uvicorn.run(app, host=options.host, port=options.port, log_level="warning")
    return 0


def run_new(options: argparse.Namespace) -> int:
    """Run `mace new`.

    Parameters
    ----------
    options : argparse.Namespace
        Parsed arguments.

    Returns
    -------
    int
        The process exit code.
    """
    directory = options.directory
    fallback = directory.name
    try:
        project = Project.create(
            directory,
            options.packs,
            pack_id=options.pack_id or fallback,
            name=options.name or fallback,
            kind="library" if options.library else "game",
            requires={needed: "^0.1" for needed in options.requires},
        )
    except (ContentError, ValidationError) as error:
        print(f"error   {error}", file=sys.stderr)
        return 1

    print(f"created {project.root}")
    missing = {needed for needed in options.requires} - {
        pack.id for pack in project.dependencies.packs
    }
    for needed in sorted(missing):
        print(
            f"warning `{needed}` was not found under {options.packs}; "
            "it is still required, so put it there before playing",
            file=sys.stderr,
        )
    return 0


def run_play(options: argparse.Namespace) -> int:
    """Run `mace play`.

    Parameters
    ----------
    options : argparse.Namespace
        Parsed arguments.

    Returns
    -------
    int
        The process exit code.
    """
    character = None
    if options.background is not None or options.spend is not None:
        try:
            spend = parse_spend(options.spend or ())
        except ValueError as error:
            print(f"error   {error}", file=sys.stderr)
            return 1
        character = Character(background=options.background, spend=spend)

    return play(
        options.paths,
        pack_id=options.pack,
        seed=options.seed,
        combat_mode=options.combat,
        time_pressure=options.time_pressure,
        character=character,
        save=options.save,
        resume=options.load,
    )


def run_serve(options: argparse.Namespace) -> int:
    """Run `mace serve`.

    Parameters
    ----------
    options : argparse.Namespace
        Parsed arguments.

    Returns
    -------
    int
        The process exit code.
    """
    try:
        import uvicorn  # noqa: PLC0415

        from mace.api.app import DEV_ORIGINS, create_app  # noqa: PLC0415
    except ImportError:
        print(
            "error   the server needs its extras: pip install 'mace[api]'",
            file=sys.stderr,
        )
        return 1

    try:
        app = create_app(
            options.paths,
            origins=options.origin or list(DEV_ORIGINS),
            client=options.client,
        )
    except ContentError as error:
        print(f"error   {error}", file=sys.stderr)
        return 1

    print(f"MACE on http://{options.host}:{options.port} — ctrl-c to stop")
    uvicorn.run(app, host=options.host, port=options.port, log_level="warning")
    return 0


def run_bundle(options: argparse.Namespace) -> int:
    """Run `mace bundle`.

    Parameters
    ----------
    options : argparse.Namespace
        Parsed arguments.

    Returns
    -------
    int
        The process exit code.
    """
    try:
        written, packed = bundle(options.paths, options.out)
    except ContentError as error:
        print(f"error   {error}", file=sys.stderr)
        return 1

    size = written.stat().st_size
    names = ", ".join(one.rpartition("/")[2] for one in packed)
    print(f"wrote {written} — {size // 1024} KiB, {len(packed)} packs: {names}")
    return 0


def run_validate(options: argparse.Namespace) -> int:
    """Run `mace validate`.

    Parameters
    ----------
    options : argparse.Namespace
        Parsed arguments.

    Returns
    -------
    int
        0 when nothing is at error severity, 1 otherwise.
    """
    report = validate_paths(*options.paths)
    include = Severity.ERROR if options.errors_only else None
    stream = sys.stdout if report.ok else sys.stderr
    print(report.format(include=include), file=stream)
    return 0 if report.ok else 1


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI.

    Parameters
    ----------
    argv : Sequence[str] | None
        Arguments to parse. Defaults to `sys.argv[1:]`.

    Returns
    -------
    int
        The process exit code.
    """
    parser = build_parser()
    options = parser.parse_args(argv)

    if not hasattr(options, "run"):
        parser.print_help()
        return 0

    exit_code: int = options.run(options)
    return exit_code
