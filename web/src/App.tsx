/**
 * The client.
 *
 * It holds three things and derives everything else: the transcript it has
 * accumulated, the last frame the service sent, and the connection it is
 * sending actions down. There is no model of the world here. Every panel
 * renders `frame.view`, which the engine projected, and the transcript
 * renders `frame.events`, which the engine emitted.
 *
 * The one thing this file decides is what to do when the service says no.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import {
  Connection,
  fetchSave,
  openSession,
  resumeSession,
  type Transport,
} from "./api";
import { Character } from "./panels/Character";
import { Choices } from "./panels/Choices";
import { Journal } from "./panels/Journal";
import { Opening } from "./panels/Opening";
import { Pack } from "./panels/Pack";
import { StatusLine } from "./panels/StatusLine";
import type { Frame, Made, Option, SaveRecord, WorldStatus } from "./protocol";
import { forget, keep, kept } from "./storage";
import { menuOf, statusOf, transcribe, type Line } from "./transcript";

export function App() {
  const [frame, setFrame] = useState<Frame | null>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const [status, setStatus] = useState<WorldStatus | null>(null);
  const [menu, setMenu] = useState<Option[]>([]);
  const [transport, setTransport] = useState<Transport>("connecting");
  const [refusal, setRefusal] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<SaveRecord | null>(() => kept());

  const connection = useRef<Connection | null>(null);
  const scroller = useRef<HTMLDivElement | null>(null);

  /**
   * Take in a frame: append what happened, replace what stands.
   *
   * A frame with no menu in it leaves the last one alone. Combat frames say
   * nothing about choices, and blanking the menu on every one of them would
   * make the world's options flicker in and out of a fight.
   */
  const absorb = useCallback((next: Frame) => {
    setFrame(next);
    setLines((current) => [...current, ...transcribe(next.events)]);
    const standing = statusOf(next.events);
    if (standing !== null) setStatus(standing);
    const options = menuOf(next.events);
    if (options !== null) setMenu(options);
    setRefusal(null);
    setBusy(false);
  }, []);

  /** Hold the connection open, and keep the save where a reload finds it. */
  const attach = useCallback(
    (opened: Frame) => {
      absorb(opened);
      const held = new Connection(opened.session, {
        onFrame: absorb,
        onRefusal: (message) => {
          setRefusal(message);
          setBusy(false);
        },
        onTransport: setTransport,
      });
      held.open();
      connection.current = held;
    },
    [absorb],
  );

  // ADR-0009: the service holds no playthroughs, so the client keeps the save.
  useEffect(() => {
    const session = frame?.session;
    if (session === undefined) return;
    fetchSave(session)
      .then((save) => {
        keep(save);
        setSaved(save);
      })
      .catch(() => undefined);
  }, [frame]);

  // Stay at the foot of the transcript as it grows. Setting `scrollTop`
  // rather than calling `scrollIntoView` because the smoothness is the
  // stylesheet's business, and it already knows to drop it for a reader who
  // has asked for less motion.
  useEffect(() => {
    const box = scroller.current;
    if (box !== null) box.scrollTop = box.scrollHeight;
  }, [lines]);

  useEffect(() => () => connection.current?.close(), []);

  function begin(pack: string, character: Made | null): void {
    setFailure(null);
    openSession(character === null ? { pack } : { pack, character })
      .then(attach)
      .catch((error: Error) => setFailure(error.message));
  }

  function carryOn(save: SaveRecord): void {
    setFailure(null);
    resumeSession(save)
      .then((opened) => {
        // The replay already happened, in silence. Re-reading a whole
        // playthrough is not resuming it: what the player wants back is the
        // room they were standing in, which is the last step's events.
        attach(opened);
        if (opened.warnings?.length) {
          setRefusal(opened.warnings.join(" "));
        }
      })
      .catch((error: Error) => setFailure(error.message));
  }

  function startOver(): void {
    forget();
    setSaved(null);
  }

  function choose(option: number): void {
    setBusy(true);
    void connection.current?.send({ kind: "choose", option });
  }

  if (frame === null) {
    return (
      <Opening
        saved={saved}
        onBegin={begin}
        onResume={carryOn}
        onForget={startOver}
        failure={failure}
      />
    );
  }

  return (
    <div className="game">
      <main className="narrative">
        <div className="transcript" role="log" aria-live="polite" ref={scroller}>
          {lines.map((entry) => (
            <p key={entry.id} className={`line line-${entry.tone}`}>
              {entry.text}
            </p>
          ))}
        </div>

        {refusal !== null && <p className="trouble">{refusal}</p>}

        {frame.playing ? (
          <Choices options={menu} onChoose={choose} busy={busy} />
        ) : (
          <div className="ending-panel">
            <p className="line line-ending">
              {frame.view.outcome === "won" ? "You won." : "You lost."}
            </p>
            {frame.view.endedBecause !== null && (
              <p className="dim">{frame.view.endedBecause}</p>
            )}
            <button type="button" className="primary" onClick={() => window.location.reload()}>
              Again
            </button>
          </div>
        )}
      </main>

      <aside className="sidebar">
        <Character sheet={frame.view.sheet} />
        <Pack carried={frame.view.carried} />
        <Journal journal={frame.view.journal} />
        <p className={`transport transport-${transport}`}>
          {transport === "socket"
            ? "connected"
            : transport === "polling"
              ? "reconnecting — playing over HTTP"
              : "connecting…"}
        </p>
      </aside>

      <StatusLine status={status} />
    </div>
  );
}
