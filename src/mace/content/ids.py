"""Namespaced ids, and the order a bare reference resolves in.

Every object's fully qualified id is `pack-id:local-id`. Inside a pack an
author may write the bare local id, which resolves against that pack first and
then its direct dependencies, in the order they are listed in `requires`.
Ambiguity is not tolerated: two dependencies offering the same bare id is an
error, not a coin flip. See docs/03-content-model.md § Ids and namespacing.
"""

from __future__ import annotations

__all__ = ["QUALIFIER", "is_qualified", "qualify", "split"]

#: Separates a pack id from a local id.
QUALIFIER = ":"


def qualify(pack_id: str, local_id: str) -> str:
    """Build a fully qualified id.

    Parameters
    ----------
    pack_id : str
        The owning pack.
    local_id : str
        The id within that pack.

    Returns
    -------
    str
        `pack-id:local-id`.
    """
    return f"{pack_id}{QUALIFIER}{local_id}"


def is_qualified(reference: str) -> bool:
    """Whether a reference already names its pack.

    Parameters
    ----------
    reference : str
        A content reference.

    Returns
    -------
    bool
        True if the reference is `pack:id` rather than a bare local id.
    """
    return QUALIFIER in reference


def split(reference: str) -> tuple[str | None, str]:
    """Split a reference into its pack and local parts.

    Parameters
    ----------
    reference : str
        A content reference, bare or qualified.

    Returns
    -------
    tuple of (str or None, str)
        The pack id, or None for a bare reference, and the local id.
    """
    pack, separator, local = reference.partition(QUALIFIER)
    return (pack, local) if separator else (None, reference)
