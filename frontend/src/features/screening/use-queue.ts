import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "@/api/client";
import {
  deleteDecision,
  fetchItem,
  fetchQueue,
  putDecision,
  type DecisionBody,
  type DecisionValue,
  type QueueSort,
  type ScreeningItem,
  type Stage,
} from "@/api/screening";

/** How many records to hold ahead of the one on screen (guide 8.5, 11.5). */
const AHEAD = 10;
const REFILL_BELOW = 5;
const RETRY_MS = 10_000;

export interface Choice {
  decision: DecisionValue;
  reason_ids: string[];
  note?: string | null;
}

interface Pending {
  recordId: string;
  body: DecisionBody;
}

export interface Queue {
  current: ScreeningItem | undefined;
  /** The record that comes after the current one, already held. */
  upcoming: ScreeningItem | undefined;
  /** Where the current record is among those seen this session, from 0. */
  position: number;
  loading: boolean;
  /** Decisions made while the connection was down, waiting to be sent (guide 11.6). */
  waiting: number;
  decide: (choice: Choice, timeSpentMs: number) => Promise<{ ok: boolean; error?: unknown }>;
  undo: () => Promise<ScreeningItem | undefined>;
  next: () => void;
  previous: () => void;
  open: (recordId: string) => Promise<void>;
  update: (recordId: string, change: Partial<ScreeningItem>) => void;
  canUndo: boolean;
}

function unreachable(error: unknown): boolean {
  // fetch rejects with a TypeError when the request never reached the server.
  return !(error instanceof ApiError);
}

/**
 * The screening queue. Records are held ahead so the next one is already on screen when
 * a decision is made; the decision is shown at once and sent behind it. A decision the
 * server refuses puts the record back, and the caller hears why; one that could not be
 * sent at all waits in memory — never in storage — and goes when the connection returns.
 */
export function useScreeningQueue(
  pid: string,
  stage: Stage,
  sort: QueueSort,
  search: string,
): Queue {
  const view = `${pid}|${stage}|${sort}|${search}`;
  const [loaded, setLoaded] = useState<string | null>(null);
  const [items, setItems] = useState<ScreeningItem[]>([]);
  const [index, setIndex] = useState(0);
  const [exhausted, setExhausted] = useState(false);
  const [pending, setPending] = useState<Pending[]>([]);
  const [decided, setDecided] = useState<string[]>([]);
  const itemsRef = useRef(items);
  const generation = useRef(0);
  const topping = useRef(false);

  useEffect(() => {
    itemsRef.current = items;
  }, [items]);

  // A new order or search starts the queue again; what an older request brings is dropped.
  useEffect(() => {
    const mine = ++generation.current;
    void fetchQueue(pid, { stage, n: AHEAD, sort, q: search, exclude: [] }).then((first) => {
      if (mine !== generation.current) return;
      setItems(first);
      setIndex(0);
      setDecided([]);
      setExhausted(first.length < AHEAD);
      setLoaded(view);
    });
  }, [pid, stage, sort, search, view]);

  const loading = loaded !== view;

  // Keep enough held ahead of the one on screen.
  const ahead = items.length - index;
  useEffect(() => {
    if (loading || exhausted || ahead >= REFILL_BELOW || topping.current) return;
    topping.current = true;
    const mine = generation.current;
    const held = itemsRef.current.filter((item) => !item.my_decision).map((item) => item.id);
    void fetchQueue(pid, { stage, n: AHEAD, sort, q: search, exclude: held.slice(-60) })
      .then((more) => {
        if (mine !== generation.current) return;
        setItems((current) => {
          const known = new Set(current.map((item) => item.id));
          return [...current, ...more.filter((item) => !known.has(item.id))];
        });
        setExhausted(more.length < AHEAD);
      })
      .finally(() => {
        topping.current = false;
      });
  }, [ahead, loading, exhausted, pid, stage, sort, search]);

  // Send what could not be sent, when the connection comes back.
  const flush = useCallback(async () => {
    if (pending.length === 0) return;
    const failed: Pending[] = [];
    for (const item of pending) {
      try {
        await putDecision(pid, item.recordId, item.body);
      } catch (error) {
        if (unreachable(error)) failed.push(item);
      }
    }
    setPending(failed);
  }, [pending, pid]);
  useEffect(() => {
    if (pending.length === 0) return;
    const onOnline = () => void flush();
    // They live only in this tab, so leaving it would lose them: ask first.
    const onLeave = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("online", onOnline);
    window.addEventListener("beforeunload", onLeave);
    const timer = window.setInterval(onOnline, RETRY_MS);
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("beforeunload", onLeave);
      window.clearInterval(timer);
    };
  }, [pending.length, flush]);

  const update = useCallback((recordId: string, change: Partial<ScreeningItem>) => {
    setItems((current) =>
      current.map((item) => (item.id === recordId ? { ...item, ...change } : item)),
    );
  }, []);

  const decide = useCallback(
    async (choice: Choice, timeSpentMs: number) => {
      const record = itemsRef.current[index];
      if (!record) return { ok: false };
      const before = record.my_decision;
      const body: DecisionBody = {
        stage,
        decision: choice.decision,
        reason_ids: choice.decision === "exclude" ? choice.reason_ids : [],
        note: choice.note ?? null,
        time_spent_ms: Math.max(0, Math.round(timeSpentMs)),
      };
      // Shown at once; the next record is already held.
      update(record.id, {
        my_decision: {
          decision: body.decision,
          reason_ids: body.reason_ids,
          note: body.note ?? null,
          updated_at: new Date().toISOString(),
        },
      });
      setDecided((stack) => [...stack.filter((id) => id !== record.id), record.id]);
      setIndex((position) => position + 1);
      try {
        const saved = await putDecision(pid, record.id, body);
        update(record.id, { my_decision: saved.decision });
        return { ok: true };
      } catch (error) {
        if (unreachable(error)) {
          setPending((queued) => [
            ...queued.filter((item) => item.recordId !== record.id),
            { recordId: record.id, body },
          ]);
          return { ok: true };
        }
        // Refused: put it back on screen as it was, for the caller to explain.
        update(record.id, { my_decision: before });
        setDecided((stack) => stack.filter((id) => id !== record.id));
        setIndex(itemsRef.current.findIndex((item) => item.id === record.id));
        return { ok: false, error };
      }
    },
    [index, pid, stage, update],
  );

  const undo = useCallback(async () => {
    const last = decided.at(-1);
    if (!last) return undefined;
    const record = itemsRef.current.find((item) => item.id === last);
    setDecided((stack) => stack.slice(0, -1));
    setPending((queued) => queued.filter((item) => item.recordId !== last));
    update(last, { my_decision: null });
    const position = itemsRef.current.findIndex((item) => item.id === last);
    if (position >= 0) setIndex(position);
    try {
      await deleteDecision(pid, last, stage);
    } catch (error) {
      // It never reached the server: the undo here is all there is to do.
      if (!(error instanceof ApiError && error.status === 404)) throw error;
    }
    return record;
  }, [decided, pid, stage, update]);

  const next = useCallback(() => {
    setIndex((position) => Math.min(position + 1, itemsRef.current.length));
  }, []);
  const previous = useCallback(() => {
    setIndex((position) => Math.max(position - 1, 0));
  }, []);

  const open = useCallback(
    async (recordId: string) => {
      const at = itemsRef.current.findIndex((item) => item.id === recordId);
      if (at >= 0) {
        setIndex(at);
        return;
      }
      const item = await fetchItem(pid, recordId, stage);
      setItems((current) => [...current.slice(0, index), item, ...current.slice(index)]);
    },
    [index, pid, stage],
  );

  return {
    current: loading ? undefined : items[index],
    upcoming: loading ? undefined : items[index + 1],
    position: index,
    loading,
    waiting: pending.length,
    decide,
    undo,
    next,
    previous,
    open,
    update,
    canUndo: decided.length > 0,
  };
}
