import { useEffect } from "react";

export type ShortcutMap = Record<string, (event: KeyboardEvent) => void>;

function typing(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return (
    tag === "INPUT" ||
    tag === "TEXTAREA" ||
    tag === "SELECT" ||
    target.isContentEditable ||
    target.closest("[role='dialog'] input, [role='dialog'] textarea") !== null
  );
}

/**
 * Guide 11.4's keys. Keys are matched by `event.key` ("i", "1", "ArrowRight", "?") and
 * "mod+z" for Ctrl or Cmd with Z. They never fire while someone is typing, and plain keys
 * are ignored when a modifier is held, so browser shortcuts still work.
 */
export function useShortcuts(shortcuts: ShortcutMap, enabled = true): void {
  useEffect(() => {
    if (!enabled) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || typing(event.target)) return;
      const mod = event.metaKey || event.ctrlKey;
      const key = mod
        ? `mod+${event.key.toLowerCase()}`
        : event.key.length === 1
          ? event.key.toLowerCase()
          : event.key;
      if (!mod && event.altKey) return;
      const action = shortcuts[key] ?? (key === "/" ? shortcuts["/"] : undefined);
      if (!action) return;
      event.preventDefault();
      action(event);
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, [shortcuts, enabled]);
}
