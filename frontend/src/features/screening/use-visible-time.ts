import { useCallback, useEffect, useRef } from "react";

/**
 * Time on the current record, counting only while the tab is visible (guide 8.5). Call
 * `take` when the decision is made: it returns the time and starts counting again.
 */
export function useVisibleTime(recordId: string | undefined): () => number {
  const started = useRef<number | null>(null);
  const spent = useRef(0);

  useEffect(() => {
    spent.current = 0;
    started.current = document.hidden ? null : performance.now();
  }, [recordId]);

  useEffect(() => {
    const onVisibility = () => {
      if (document.hidden) {
        if (started.current !== null) spent.current += performance.now() - started.current;
        started.current = null;
      } else {
        started.current = performance.now();
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  return useCallback(() => {
    const now = performance.now();
    const total = spent.current + (started.current === null ? 0 : now - started.current);
    spent.current = 0;
    started.current = document.hidden ? null : now;
    return total;
  }, []);
}
