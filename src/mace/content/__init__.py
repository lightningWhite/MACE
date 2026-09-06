"""The content layer: packs on disk to an immutable compiled World.

Discovery, namespaced id resolution, `extends` inheritance, dependency ordering,
and schema validation. Reads `packs/`; never reads session state.
See docs/03-content-model.md and docs/04-schema-reference.md.
"""
