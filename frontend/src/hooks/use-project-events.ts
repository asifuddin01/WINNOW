import { useEffect } from "react";

/** What the server sends on the project's event stream (guide 10). */
export interface ProjectEvent {
  event: string;
  batch_id?: string;
  imported?: number;
  problems?: number;
  reason?: string | null;
}

/**
 * Follow a review's live events. The browser reconnects on its own, and the server sends
 * the last few events on connect, so a page opened mid-import catches up.
 */
export function useProjectEvents(pid: string, onEvent: (event: ProjectEvent) => void): void {
  useEffect(() => {
    // jsdom and older browsers have no EventSource; the page still works, just not live.
    if (typeof EventSource === "undefined") return;
    const source = new EventSource(`/api/v1/projects/${pid}/events`);
    source.onmessage = (message: MessageEvent<string>) => {
      try {
        onEvent(JSON.parse(message.data) as ProjectEvent);
      } catch {
        // A partial line is not worth breaking the page over.
      }
    };
    return () => {
      source.close();
    };
  }, [pid, onEvent]);
}
