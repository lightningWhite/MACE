# Schemas

Generated. Don't edit by hand — run:

```bash
python -m mace.model.jsonschema
```

`tests/test_schemas.py` fails if these files drift from the models in
`src/mace/model/`.

| File | Validates |
|---|---|
| `pack.schema.json` | A pack's `pack.yml` manifest |
| `content.schema.json` | Every other `.yml` file in a pack |

These describe content **as authored**, before the loader has run: `extends` is
still present, an inherited field may still be missing, and the `$append` and
`$remove` merge sentinels are still in the lists they will act on. The pydantic
models describe the same content **after** loading, where none of that is true.
See [docs/03 § Inheritance](../docs/03-content-model.md#inheritance-extends).

Point an editor at them for completion over the whole condition and effect
vocabulary. In VS Code, with the YAML extension:

```jsonc
// .vscode/settings.json
"yaml.schemas": {
  "./schemas/pack.schema.json": "packs/**/pack.yml",
  "./schemas/content.schema.json": ["packs/**/*.yml", "!packs/**/pack.yml"]
}
```
