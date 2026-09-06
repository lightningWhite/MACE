"""Smoke tests for the package skeleton."""

import importlib

import pytest

import mace

# Every package the layout in CLAUDE.md and docs/02-architecture.md promises.
SUBPACKAGES = [
    "mace.api",
    "mace.cli",
    "mace.content",
    "mace.engine",
    "mace.engine.combat",
    "mace.engine.economy",
    "mace.engine.encounter",
    "mace.engine.expr",
    "mace.engine.rng",
    "mace.engine.world",
    "mace.model",
    "mace.session",
    "mace.wizard",
]


def test_version_is_exposed() -> None:
    assert mace.__version__


@pytest.mark.parametrize("name", SUBPACKAGES)
def test_subpackage_imports(name: str) -> None:
    assert importlib.import_module(name) is not None


def test_cli_runs() -> None:
    from mace.cli import main

    assert main([]) == 0
