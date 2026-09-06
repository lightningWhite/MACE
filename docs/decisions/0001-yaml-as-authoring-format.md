# ADR-0001 — YAML for authoring, compiled JSON at runtime

**Status:** Accepted

## Context

The v0 prototype defines games as YAML files. Before building further on that
assumption it's worth asking whether YAML is right, because the format decision
is expensive to reverse once content exists.

Requirements the format has to satisfy:

1. Hand-writable and hand-readable — authors must be able to open a file and
   understand it, and to fix things without the wizard.
2. Reviewable in a GitHub pull request — the community model is people sending
   worlds as PRs, and a maintainer has to be able to read the diff.
3. Commentable — library packs are documentation as much as data.
4. Machine-generated cleanly by the wizard.
5. Fast to load, including in a browser.
6. Validatable against a schema.

## Decision

**YAML is the authoring format. A compiled JSON bundle is the runtime format.**

The loader resolves inheritance, namespacing, and defaults once, producing a flat
immutable structure. Distribution and play (especially in the browser) use the
compiled bundle; nobody parses YAML at play time.

Three changes to how the v0 templates use YAML, each with its own consequences —
see ADR-0002 and ADR-0003:

1. Named, referenceable scenes instead of deep anonymous nesting.
2. Structured conditions and effects instead of expression strings.
3. Namespaced ids and `extends` inheritance.

## Alternatives considered

**JSON.** Meets 4, 5, 6 well; fails 1 and 3 badly. No comments is disqualifying
for library packs, and hand-editing JSON is miserable. Rejected as the authoring
format, adopted as the compiled one.

**TOML.** Excellent for flat config, poor for deeply nested lists of objects —
which is most of this content. Location exit lists would be painful. Rejected.

**A custom DSL.** Tempting: a purpose-built syntax could be beautiful, and
interactive fiction has a tradition of it (Inform, Ink, Twine). Rejected because
it means writing and maintaining a parser, a formatter, an error-reporting
system, and editor tooling, all before anyone can build a game. YAML gets syntax
highlighting, folding, and schema-aware autocomplete in every editor for free.
Worth revisiting *for scenes specifically* if authoring dialog in YAML proves
painful in practice — an Ink-like scene syntax that compiles to the same models
would be a contained, additive change.

**SQLite or another database.** Good for large worlds and fast queries; fails 1,
2, and 3 completely. A binary blob can't be reviewed in a PR, and "clone the repo
and read someone's world" is a property worth protecting. Rejected.

**Python modules as content.** Maximum power, and no schema. Rejected outright:
running arbitrary community code is a security problem, and it puts authoring out
of reach of non-programmers — which contradicts the project's premise.

## Consequences

- Authors get comments, diffs, and readable files. Reviewers can review.
- YAML's sharp edges must be managed: the Norway problem (`no` → `False`),
  significant indentation, tab intolerance, and duplicate keys silently winning.
  The loader uses `yaml.safe_load` with a strict resolver, rejects duplicate keys,
  and requires quoting for ambiguous scalars. The wizard emits safe YAML always.
- Two formats means a compile step, and a compiler to keep correct. The mitigation
  is that the compiled form is a pure function of the source and is regenerated,
  never hand-edited.
- Large worlds will eventually make full-pack loads slow. Not a real concern at
  the scale of a text adventure; if it becomes one, the compiled bundle can be
  indexed and lazily loaded without touching the authoring format.
