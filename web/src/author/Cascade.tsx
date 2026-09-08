/**
 * The condition and effect builders, drawn.
 *
 * `defineConditions()` in the v0 wizard printed a syntax explanation and hoped.
 * The terminal's replacement asks a short list of questions; this asks the
 * same ones, from the same data. The vocabulary is not in this file — it comes
 * down from `/api/author/vocabulary` as recipes with their questions and their
 * options already resolved, so a tag added to `mace.wizard.builders` appears
 * here without anybody touching this file.
 *
 * Two things stay on the Python side and must not migrate here. The recipe
 * decides which questions get asked; and `POST /build` round-trips the answers
 * through the model, which both validates them and drops the defaults the
 * cascade filled in — so what lands in the file is the smallest content that
 * says what the author said.
 */

import { useEffect, useState } from "react";

import * as api from "./api";
import { StudioError } from "./api";
import { Control } from "./Control";
import type { Built, Recipe, Vocabulary } from "./protocol";

/** What is on the wire, once, for as long as the tab is open. */
let held: Vocabulary | null = null;

/**
 * The vocabulary, fetched once.
 *
 * It does not change while a pack is open in the sense that matters — the
 * recipes are fixed — but the *options* on its asks do, so it is refetched
 * whenever a cascade opens rather than cached forever. The held copy is only
 * there so the first paint is not empty.
 */
function useVocabulary(kind: "conditions" | "effects") {
  const [vocabulary, setVocabulary] = useState<Vocabulary | null>(held);
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    void api
      .vocabulary()
      .then((found) => {
        held = found;
        if (live) setVocabulary(found);
      })
      .catch((error: unknown) => {
        if (live) {
          setFailure(
            error instanceof StudioError ? error.message : "could not load these",
          );
        }
      });
    return () => {
      live = false;
    };
  }, []);

  return { recipes: vocabulary?.[kind] ?? [], failure };
}

interface Props {
  kind: "conditions" | "effects";
  /** Called with the authored mapping and its English once the wizard has
   * built it. */
  onBuilt: (built: Built) => void;
  onCancel: () => void;
}

/** Pick what this should depend on, answer its questions, get content back. */
export function Cascade({ kind, onBuilt, onCancel }: Props) {
  const { recipes, failure } = useVocabulary(kind);
  const [chosen, setChosen] = useState<Recipe | null>(null);

  if (failure !== null) {
    return <p className="studio-failure">{failure}</p>;
  }
  if (chosen === null) {
    return (
      <Menu
        recipes={recipes}
        noun={kind === "conditions" ? "depend on" : "happen"}
        onPick={setChosen}
        onCancel={onCancel}
      />
    );
  }
  return (
    <Questions
      kind={kind}
      recipe={chosen}
      onBuilt={onBuilt}
      onCancel={() => setChosen(null)}
    />
  );
}

/** The first screen: a grouped list of the things a recipe can produce. */
function Menu({
  recipes,
  noun,
  onPick,
  onCancel,
}: {
  recipes: Recipe[];
  noun: string;
  onPick: (recipe: Recipe) => void;
  onCancel: () => void;
}) {
  // Groups in the order the vocabulary lists them, which is the order the
  // terminal shows and the order an author is most likely to be thinking in.
  const groups: string[] = [];
  for (const recipe of recipes) {
    if (!groups.includes(recipe.group)) groups.push(recipe.group);
  }

  return (
    <div className="cascade">
      <p className="cascade-question">What should this {noun}?</p>
      {recipes.length === 0 ? <p className="dim">Loading…</p> : null}
      {groups.map((group) => (
        <section key={group}>
          {group === "" ? null : <h3 className="cascade-group">{group}</h3>}
          <ul className="cascade-menu">
            {recipes
              .filter((one) => one.group === group)
              .map((one) => (
                <li key={one.tag}>
                  <button type="button" onClick={() => onPick(one)}>
                    <span>{one.label}</span>
                    {one.help === "" ? null : (
                      <span className="dim"> — {one.help}</span>
                    )}
                  </button>
                </li>
              ))}
          </ul>
        </section>
      ))}
      <button type="button" className="cascade-cancel" onClick={onCancel}>
        never mind
      </button>
    </div>
  );
}

/** The second screen: this recipe's own questions, then build it. */
function Questions({
  kind,
  recipe,
  onBuilt,
  onCancel,
}: {
  kind: "conditions" | "effects";
  recipe: Recipe;
  onBuilt: (built: Built) => void;
  onCancel: () => void;
}) {
  const [answers, setAnswers] = useState<Record<string, unknown>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const finish = async () => {
    setBusy(true);
    setFailure(null);
    try {
      const built = await api.build(kind, recipe.tag, answers);
      onBuilt(built);
    } catch (error) {
      setFailure(
        error instanceof StudioError
          ? error.message
          : `that is not a valid ${kind === "conditions" ? "condition" : "effect"}`,
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="cascade">
      <p className="cascade-question">{recipe.label}</p>
      {recipe.asks.map((ask) => (
        <div className="field" key={ask.key === "" ? recipe.tag : ask.key}>
          <label className="field-title" htmlFor={`ask-${recipe.tag}-${ask.key}`}>
            {ask.title}
          </label>
          {ask.help === "" ? null : <p className="field-help">{ask.help}</p>}
          {ask.default === null ? null : (
            <p className="field-help">
              Leave it for <code>{JSON.stringify(ask.default)}</code>.
            </p>
          )}
          <Control
            id={`ask-${recipe.tag}-${ask.key}`}
            field={ask.field}
            value={answers[ask.key] ?? null}
            busy={busy}
            onChange={(value) =>
              setAnswers((current) => ({ ...current, [ask.key]: value }))
            }
          />
        </div>
      ))}

      {failure === null ? null : (
        <p className="studio-failure" role="alert">
          {failure}
        </p>
      )}
      <div className="cascade-actions">
        <button type="button" disabled={busy} onClick={() => void finish()}>
          Add it
        </button>
        <button type="button" className="cascade-cancel" onClick={onCancel}>
          back
        </button>
      </div>
    </div>
  );
}
