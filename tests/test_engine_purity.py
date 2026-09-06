"""Enforce boundary 2: `mace.engine` is pure and deterministic.

The engine may not print, prompt, read stdin, touch the filesystem or the
network, read the wall clock, or call `random` directly. That rule is what makes
replay tests, a second engine implementation, and browser execution possible, so
it is checked mechanically rather than trusted to review.

See docs/02-architecture.md and CLAUDE.md.
"""

import ast
from pathlib import Path

import pytest

ENGINE_ROOT = Path(__file__).resolve().parent.parent / "src" / "mace" / "engine"

#: Top-level modules the engine must never import, and why.
FORBIDDEN_IMPORTS = {
    "random": "use the seeded RNG service — rng.stream('name')",
    "secrets": "non-deterministic",
    "time": "the engine may not read the wall clock",
    "datetime": "the engine may not read the wall clock; use the world clock",
    "os": "the engine may not touch the filesystem or environment",
    "pathlib": "the engine may not touch the filesystem",
    "shutil": "the engine may not touch the filesystem",
    "tempfile": "the engine may not touch the filesystem",
    "socket": "the engine may not touch the network",
    "http": "the engine may not touch the network",
    "urllib": "the engine may not touch the network",
    "subprocess": "the engine may not shell out",
    "yaml": "content loading belongs in mace.content, not the engine",
}

#: Builtins the engine must never call.
FORBIDDEN_CALLS = {
    "print": "the engine returns events; front-ends render them",
    "input": "the engine never prompts",
    "eval": "content is untrusted — use mace.engine.expr",
    "exec": "content is untrusted — use mace.engine.expr",
    "open": "the engine may not touch the filesystem",
}


def engine_sources() -> list[Path]:
    """Collect every Python source file under `mace.engine`.

    Returns
    -------
    list[Path]
        Sorted paths of the engine's source files.
    """
    return sorted(ENGINE_ROOT.rglob("*.py"))


def imported_roots(tree: ast.AST) -> set[str]:
    """Find the top-level module names a parsed source file imports.

    Parameters
    ----------
    tree : ast.AST
        The parsed module.

    Returns
    -------
    set[str]
        Top-level names, e.g. `{"os", "mace"}` for `import os.path` and
        `from mace.model import Entity`.
    """
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            # A relative import (level > 0) stays inside the engine.
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


def called_names(tree: ast.AST) -> set[str]:
    """Find the bare function names a parsed source file calls.

    Parameters
    ----------
    tree : ast.AST
        The parsed module.

    Returns
    -------
    set[str]
        Names called directly, e.g. `{"print"}` for `print(x)`. Attribute calls
        such as `logger.info(x)` are not included.
    """
    return {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


@pytest.mark.parametrize("source", engine_sources(), ids=lambda p: p.name)
def test_engine_module_is_pure(source: Path) -> None:
    tree = ast.parse(source.read_text(), filename=str(source))
    relative = source.relative_to(ENGINE_ROOT.parent.parent.parent)

    for name in sorted(imported_roots(tree) & FORBIDDEN_IMPORTS.keys()):
        pytest.fail(f"{relative} imports `{name}`: {FORBIDDEN_IMPORTS[name]}")

    for name in sorted(called_names(tree) & FORBIDDEN_CALLS.keys()):
        pytest.fail(f"{relative} calls `{name}()`: {FORBIDDEN_CALLS[name]}")


def test_purity_check_covers_something() -> None:
    """Guard against the check silently passing because it found no files."""
    assert engine_sources(), f"no engine sources found under {ENGINE_ROOT}"
