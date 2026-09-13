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
  lookSession,
  remote,
  serviceIsUp,
  type Link,
  type Service,
  type Transport,
} from "./api";
import { local, type Progress } from "./local/engine";
import { Combat, type Fight } from "./combat/Combat";
import { Character } from "./panels/Character";
import { Choices } from "./panels/Choices";
import { Journal } from "./panels/Journal";
import { MapView } from "./map/Map";
import { Opening } from "./panels/Opening";
import { Pack } from "./panels/Pack";
import { StatusLine } from "./panels/StatusLine";
import type {
  Action,
  CombatBegan,
  Frame,
  Gauge,
  Made,
  Option,
  SaveRecord,
  WorldStatus,
} from "./protocol";
import { isKind } from "./protocol";
import { forget, keep, kept } from "./storage";
import { useSplitGrid } from "./useSplitGrid";
import {
  fightEnded,
  fightOf,
  menuOf,
  responsesOf,
  statusOf,
  tellOf,
  transcribe,
  type Fighting,
  type Line,
} from "./transcript";

/** Every combatant's opening pool, actor to gauge, as `combat.begin` states it. */
function seedVitals(began: CombatBegan): Record<string, Gauge> {
  const table: Record<string, Gauge> = {};
  for (const combatant of began.combatants) table[combatant.actor] = combatant.vital;
  return table;
}

/**
 * The client.
 *
 * @param playtest - A session the wizard already opened, handed over as
 *   `#play/<id>`. The client attaches to it instead of offering to start
 *   one; everything after that is an ordinary playthrough, because that is
 *   all a playtest is.
 */
/** The transcript, split at "now": everything before this tick, and this
 * tick's own lines. */
interface Thread {
  history: Line[];
  latest: Line[];
}

const EMPTY_THREAD: Thread = { history: [], latest: [] };

export function App({ playtest }: { playtest?: string } = {}) {
  const [frame, setFrame] = useState<Frame | null>(null);
  const [thread, setThread] = useState<Thread>(EMPTY_THREAD);
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [status, setStatus] = useState<WorldStatus | null>(null);
  const [menu, setMenu] = useState<Option[]>([]);
  const [transport, setTransport] = useState<Transport>("connecting");
  const [refusal, setRefusal] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [fight, setFight] = useState<Fight | null>(null);
  const [saved, setSaved] = useState<SaveRecord | null>(() => kept());
  const [service, setService] = useState<Service | null>(null);
  const [progress, setProgress] = useState<Progress>(null);

  const connection = useRef<Link | null>(null);
  const scroller = useRef<HTMLDivElement | null>(null);
  const pane = useRef<HTMLDivElement | null>(null);
  const shell = useRef<HTMLDivElement | null>(null);
  const acted = useRef(false);
  const fighting = useRef<Fighting>({ current: false });
  const split = useSplitGrid(shell);

  /**
   * Take in a frame: append what happened, replace what stands.
   *
   * A frame with no menu in it leaves the last one alone. Combat frames say
   * nothing about choices, and blanking the menu on every one of them would
   * make the world's options flicker in and out of a fight.
   */
  const absorb = useCallback((next: Frame) => {
    setFrame(next);
    // Last tick's "latest" is now history — it happened before this one —
    // and this tick's own lines take its place as what is always on show.
    setThread((current) => ({
      history: [...current.history, ...current.latest],
      latest: transcribe(next.events, fighting.current),
    }));
    const standing = statusOf(next.events);
    if (standing !== null) setStatus(standing);
    const options = menuOf(next.events);
    if (options !== null) setMenu(options);

    // A fight is a tell and the answers to it. `combat.begin` arrives once and
    // carries the mode and the counter matrix, so it is carried forward across
    // exchanges; the tell and the responses come with every one.
    const tell = tellOf(next.events);
    const responses = responsesOf(next.events);
    if (tell !== null && responses !== null) {
      setFight((current) => {
        const opened = fightOf(next.events);
        const began: CombatBegan | null = opened ?? current?.began ?? null;
        if (began === null) return null;
        // A fresh `combat.begin` seeds every combatant's opening pool;
        // otherwise carry forward what the fight has taken so far and let
        // this frame's own `stat.changed` events update it.
        let vitals = opened !== null ? seedVitals(opened) : (current?.vitals ?? seedVitals(began));
        for (const event of next.events) {
          if (!isKind(event, "stat.changed")) continue;
          const known = vitals[event.actor];
          if (known !== undefined && event.stat === known.stat && event.value !== known.value) {
            vitals = { ...vitals, [event.actor]: { ...known, value: event.value } };
          }
        }
        // The window opens when the tell reaches the player, not when the
        // engine wrote it: the time on the wire is theirs, not the network's.
        return { began, tell, responses, vitals, openedAt: performance.now() };
      });
    } else if (fightEnded(next.events)) {
      setFight(null);
    }

    setRefusal(null);
    setBusy(false);
  }, []);

  // One build, two deployments. The hosted one has a session service; the
  // static one has no server at all and runs the same engine, compiled to
  // WebAssembly, in a worker in this tab. Asking rather than being told at
  // build time is also what lets an offline tab fall through to the engine it
  // already has. See ADR-0005.
  useEffect(() => {
    // A playtest lives in the process the wizard is running in — that is
    // where the half-finished pack is — so there is nothing to ask about.
    if (playtest !== undefined) {
      setService(remote);
      return;
    }
    let live = true;
    void serviceIsUp().then((up) => {
      if (live) setService(up ? remote : local(setProgress));
    });
    return () => {
      live = false;
    };
  }, [playtest]);

  /** Hold the connection open, and keep the save where a reload finds it. */
  const attach = useCallback(
    (opened: Frame, on: Service) => {
      absorb(opened);
      connection.current = on.connect(opened.session, {
        onFrame: absorb,
        onRefusal: (message) => {
          setRefusal(message);
          setBusy(false);
        },
        onTransport: setTransport,
      });
    },
    [absorb],
  );

  // Pick up the playthrough the wizard opened. Attaching rather than
  // beginning: the seed, the weather and the kit were all chosen on the
  // author's form, and asking again here would be asking twice.
  useEffect(() => {
    if (playtest === undefined) return;
    lookSession(playtest)
      .then((opened) => attach(opened, remote))
      .catch((error: Error) => setFailure(error.message));
  }, [playtest, attach]);

  // ADR-0009: nothing but the client is holding on to this playthrough — not
  // the service, and certainly not a tab that might be closed.
  useEffect(() => {
    const session = frame?.session;
    if (session === undefined || service === null) return;
    // Except a playtest, whose save would be a lie: the weather and the extra
    // kit are set on the opening state rather than smuggled into content, so
    // they are not in the action log and would not come back. Keeping one
    // would also put a half-finished pack in the player's "carry on".
    if (playtest !== undefined) return;
    service
      .fetchSave(session)
      .then((save) => {
        keep(save);
        setSaved(save);
      })
      .catch(() => undefined);
  }, [frame, service]);

  // Stay at the foot of memory as it grows, so the tick just folded into
  // history is the one already in view rather than one a reader has to
  // scroll to find. Setting `scrollTop` rather than calling `scrollIntoView`
  // because the smoothness is the stylesheet's business, and it already
  // knows to drop it for a reader who has asked for less motion.
  useEffect(() => {
    const box = scroller.current;
    if (box !== null) box.scrollTop = box.scrollHeight;
  }, [thread.history]);

  // The button a player pressed is gone by the time the frame lands, so
  // without this focus falls back to the document and the next Tab starts
  // from the top of the page — a keyboard player would have to tab back into
  // the game after every single turn. Focus moves only when the player
  // acted, never on the opening frame, which would take it from whatever
  // they were reading.
  useEffect(() => {
    if (!acted.current) return;
    acted.current = false;
    pane.current
      ?.querySelector<HTMLButtonElement>("button:not(:disabled)")
      ?.focus();
  }, [frame]);

  useEffect(() => () => connection.current?.close(), []);

  function begin(
    pack: string,
    character: Made | null,
    timePressure: number,
    combatMode: string | null,
  ): void {
    if (service === null) return;
    setFailure(null);
    service
      .openSession({
        pack,
        timePressure,
        ...(character === null ? {} : { character }),
        ...(combatMode === null ? {} : { combatMode }),
      })
      .then((opened) => attach(opened, service))
      .catch((error: Error) => setFailure(error.message));
  }

  function carryOn(save: SaveRecord): void {
    if (service === null) return;
    setFailure(null);
    service
      .resumeSession(save)
      .then((opened) => {
        // The replay already happened, in silence. Re-reading a whole
        // playthrough is not resuming it: what the player wants back is the
        // room they were standing in, which is the last step's events.
        attach(opened, service);
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
    acted.current = true;
    void connection.current?.send({ kind: "choose", option });
  }

  function answer(action: Action): void {
    setBusy(true);
    acted.current = true;
    void connection.current?.send(action);
  }

  /**
   * Step back to the picker without losing the playthrough.
   *
   * The session itself is untouched — it is on the server, or in this tab's
   * own worker, either way outliving this — so leaving is nothing more than
   * this component forgetting it was looking at one. `saved` is still what
   * it was, so the picker offers "carry on" for exactly this game if there
   * is nowhere else to go, and starting a different one is the ordinary
   * `begin` a fresh player would use.
   */
  function leave(): void {
    connection.current?.close();
    connection.current = null;
    setFrame(null);
    setThread(EMPTY_THREAD);
    setMemoryOpen(false);
    setStatus(null);
    setMenu([]);
    setFight(null);
    setRefusal(null);
    setBusy(false);
    setTransport("connecting");
  }

  if (frame === null && playtest !== undefined) {
    // Nothing to offer and nothing to choose: this playthrough already
    // exists. Either it arrives, or the wizard that opened it is gone.
    return (
      <main className="opening">
        <p className="dim">{failure ?? "Opening the playtest…"}</p>
      </main>
    );
  }

  if (frame === null) {
    return (
      <Opening
        service={service}
        progress={progress}
        saved={saved}
        onBegin={begin}
        onResume={carryOn}
        onForget={startOver}
        failure={failure}
      />
    );
  }

  return (
    <div
      className="shell"
      ref={shell}
      style={
        {
          "--col-split": `${split.colPercent}%`,
          "--row-split": `${split.rowPercent}%`,
        } as React.CSSProperties
      }
    >
      <main className="narrative">
        <section className={memoryOpen ? "memory memory-open" : "memory"}>
          <button
            type="button"
            className="memory-toggle"
            aria-expanded={memoryOpen}
            onClick={() => setMemoryOpen((open) => !open)}
          >
            Memory
          </button>
          {memoryOpen && (
            <div className="transcript" role="log" aria-live="polite" ref={scroller}>
              {thread.history.map((entry) => (
                <p key={entry.id} className={`line line-${entry.tone}`}>
                  {entry.text}
                </p>
              ))}
            </div>
          )}
        </section>

        {/* What just happened, always in view whether memory is open or
            closed — the collapsed state has to still be a game, not just a
            toggle. */}
        <div className="current-tick transcript" role="log" aria-live="polite">
          {thread.latest.map((entry) => (
            <p key={entry.id} className={`line line-${entry.tone}`}>
              {entry.text}
            </p>
          ))}
        </div>
      </main>

      <aside className="map-quadrant">
        <MapView
          atlas={frame.view.atlas}
          carried={frame.view.carried}
          onTravel={choose}
          busy={busy}
        />
        {frame.view.submap != null && (
          <MapView
            atlas={frame.view.submap}
            carried={frame.view.carried}
            onTravel={choose}
            busy={busy}
            heading="Close by"
          />
        )}
      </aside>

      {/* Not a landmark element (article/aside/main/nav/section): the footer
          nested at its foot must stay reachable as `contentinfo`, which the
          HTML spec strips the moment a footer sits inside one of those. */}
      <div className="action" ref={pane} aria-busy={busy}>
        {refusal !== null && <p className="trouble">{refusal}</p>}

        {frame.playing && fight !== null ? (
          <Combat
            fight={fight}
            onAnswer={answer}
            busy={busy}
            staminaOf={
              frame.view.sheet.stats.find((gauge) => gauge.role === "effort")
                ?.maximum ?? null
            }
          />
        ) : frame.playing ? (
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

        <StatusLine status={status} />
      </div>

      <aside className="info">
        {playtest === undefined && (
          <button type="button" className="link-button leave-game" onClick={leave}>
            ‹ Choose a different game
          </button>
        )}
        <details className="accordion" open>
          <summary>Stats</summary>
          <Character sheet={frame.view.sheet} />
        </details>
        <details className="accordion" open>
          <summary>Pack</summary>
          <Pack carried={frame.view.carried} />
        </details>
        <details className="accordion" open>
          <summary>Journal</summary>
          <Journal journal={frame.view.journal} />
        </details>
        <p className={`transport transport-${transport}`}>
          {transport === "local"
            ? "running in this tab"
            : transport === "socket"
              ? "connected"
              : transport === "polling"
                ? "reconnecting — playing over HTTP"
                : "connecting…"}
        </p>
      </aside>

      {/* The four quadrants share one column split and one row split, so one
          divider each reshapes all four rather than needing eight handles for
          four independently resizable panes. Hidden on the narrow layout,
          where the quadrants stack into one column and there is nothing left
          to divide. */}
      <div
        className="col-resizer"
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize the story and action panels against the map and stats"
        tabIndex={0}
        {...split.columnHandle}
      />
      <div
        className="row-resizer"
        role="separator"
        aria-orientation="horizontal"
        aria-label="Resize the top panels against the bottom panels"
        tabIndex={0}
        {...split.rowHandle}
      />
    </div>
  );
}
