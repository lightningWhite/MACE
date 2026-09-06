"""Errors raised while loading content, phrased for the person who wrote it.

An author does not have a debugger and did not write the loader. Every failure
here carries the pack, the file, and the id it came from, because "which of my
four hundred entities is wrong" is the only question that matters.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["ContentError"]


class ContentError(Exception):
    """A pack could not be loaded.

    Parameters
    ----------
    message : str
        What went wrong, phrased for a content author.
    pack : str or None
        The pack being loaded, if known.
    path : Path or None
        The file the problem came from, if known.
    collection : str or None
        Which collection the object belongs to — `entities`, `scenes`.
    object_id : str or None
        The id of the object, if the problem is with one object.
    """

    def __init__(
        self,
        message: str,
        *,
        pack: str | None = None,
        path: Path | None = None,
        collection: str | None = None,
        object_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.pack = pack
        self.path = path
        self.collection = collection
        self.object_id = object_id

    def __str__(self) -> str:
        """Render the failure with everything needed to find it.

        Returns
        -------
        str
            The location on one line, then the message.
        """
        where = []
        if self.path is not None:
            where.append(str(self.path))
        elif self.pack is not None:
            where.append(self.pack)
        if self.collection is not None and self.object_id is not None:
            where.append(f"{self.collection}/{self.object_id}")
        elif self.collection is not None:
            where.append(self.collection)

        location = " → ".join(where)
        return f"{location}: {self.message}" if location else self.message
