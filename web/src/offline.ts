/**
 * Whether the network is there.
 *
 * The shell loads offline; the *game* does not, and will not until the engine
 * moves into the tab (ADR-0005). So the honest thing for an installed client
 * with no network is to open, say exactly that, and point at the save — which
 * is local, and is the whole playthrough.
 *
 * `navigator.onLine` is famously only trustworthy in one direction: false
 * means there is definitely no network, true means there might be. That is
 * the direction this needs, because it is only ever used to explain a request
 * that already failed.
 */

import { useEffect, useState } from "react";

export function useOffline(): boolean {
  const [offline, setOffline] = useState(() => navigator.onLine === false);

  useEffect(() => {
    const went = () => setOffline(navigator.onLine === false);
    window.addEventListener("online", went);
    window.addEventListener("offline", went);
    return () => {
      window.removeEventListener("online", went);
      window.removeEventListener("offline", went);
    };
  }, []);

  return offline;
}
