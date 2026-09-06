"""Safe evaluation of author-supplied conditions and effects.

Content packs are untrusted community input. Nothing here may use `eval` or
`exec`; author expressions go through a restricted parser and evaluator.
See docs/decisions/0003-structured-conditions-and-effects.md.
"""
