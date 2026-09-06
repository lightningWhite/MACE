"""Whether a load stops at the first bad object, or carries on past it.

Two callers want two different things from the same loader, and until now only
one of them could have it.

**Playing** wants a hard stop. Content that does not compile cannot be played,
and a game that started anyway and fell over an hour in would be worse than one
that refused. `load_library` still raises on the first failure.

**Authoring** wants the opposite. A half-written pack is the normal state of a
pack being written, and an author must be able to stop mid-thought and come
back — so the wizard needs the whole problem list, not the first entry in it.
Before this, one misspelled field on one location hid every other problem in
the pack: the loader aborted, `mace validate` reported that single error, and
the dangling reference three objects later was invisible until the first was
fixed. Fixing a world one hidden error at a time is not authoring.

So a load carries a `Tolerance`. Strict raises; collecting records the failure,
drops the object that caused it, and keeps going. Everything that reads a
`Tolerance` has to be written so that dropping the object is a *correct*
outcome — which is why this is a passed-in policy rather than a try/except
somewhere in the middle.

See docs/09-authoring-and-wizard.md § Validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mace.content.errors import ContentError

__all__ = ["STRICT", "Tolerance", "collecting"]


@dataclass(slots=True)
class Tolerance:
    """How a load reacts to content it cannot build.

    Attributes
    ----------
    collect : bool
        Whether to record failures and carry on rather than raise at the first.
    problems : list of ContentError
        What was recorded, in the order it was found.
    """

    collect: bool = False
    problems: list[ContentError] = field(default_factory=list)

    def fail(self, error: ContentError) -> None:
        """Report one thing that could not be built.

        Parameters
        ----------
        error : ContentError
            What went wrong.

        Raises
        ------
        ContentError
            The error itself, when this tolerance is strict.
        """
        if not self.collect:
            raise error
        self.problems.append(error)


#: The default: a load that stops at the first thing it cannot build.
STRICT = Tolerance()


def collecting() -> Tolerance:
    """A fresh tolerance that records failures instead of raising.

    A function rather than a constant, because it accumulates: two loads
    sharing one would report each other's problems.

    Returns
    -------
    Tolerance
        An empty collecting tolerance.
    """
    return Tolerance(collect=True)
