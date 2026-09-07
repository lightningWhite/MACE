/**
 * What the player may do next.
 *
 * An unavailable option is shown and disabled rather than hidden: the author
 * wrote a hint for it — "You don't have ten gold" — and hiding the option
 * would hide the hint, which is the part that tells the player what to go and
 * do about it.
 *
 * Options are sent by index. A live client has the menu it is looking at, and
 * the index is what a `choices` event's ordering means. Prompts are for
 * things written down to outlive their content, which a click is not.
 */

import type { Option } from "../protocol";

export function Choices({
  options,
  onChoose,
  busy,
}: {
  options: Option[];
  onChoose: (index: number) => void;
  busy: boolean;
}) {
  if (options.length === 0) {
    return <p className="empty">There is nothing to do here.</p>;
  }

  return (
    <ul className="choices">
      {options.map((option, index) => (
        <li key={`${index}-${option.prompt}`}>
          <button
            type="button"
            className="choice"
            disabled={!option.available || busy}
            onClick={() => onChoose(index)}
          >
            <span className="choice-prompt">{option.prompt}</span>
            {!option.available && option.hint !== null && (
              <span className="choice-hint">{option.hint}</span>
            )}
          </button>
        </li>
      ))}
    </ul>
  );
}
