import { useEffect } from "react";

import { announcePresence, withdrawPresence, type PresenceStage } from "@/api/presence";

const BEAT_MS = 30_000;

/**
 * While a screening page is open and visible, say so every 30 seconds (guide 8.17). A
 * hidden tab is not screening: it goes quiet, and says so when it closes.
 */
export function usePresence(pid: string, stage: PresenceStage, enabled: boolean): void {
  useEffect(() => {
    if (!enabled) return;
    const beat = () => {
      if (document.visibilityState === "visible") {
        void announcePresence(pid, stage).catch(() => undefined);
      }
    };
    const onVisibility = () => {
      if (document.visibilityState === "visible") beat();
      else void withdrawPresence(pid).catch(() => undefined);
    };
    beat();
    const timer = window.setInterval(beat, BEAT_MS);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibility);
      void withdrawPresence(pid).catch(() => undefined);
    };
  }, [pid, stage, enabled]);
}
