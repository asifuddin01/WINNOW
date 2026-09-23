import { useRef, useState, type PointerEvent, type ReactNode } from "react";

import type { DecisionValue } from "@/api/screening";
import { cn } from "@/lib/utils";

const THRESHOLD = 90;

/**
 * Guide 8.5's phone layout: swipe right to include, left to exclude, up for maybe. The
 * abstract scrolls as usual (the browser keeps vertical panning there), so "up" is read
 * from the card's header; left and right work anywhere. Buttons below do the same, so a
 * swipe is never the only way.
 */
export function SwipeCard({
  children,
  header,
  onSwipe,
  disabled,
}: {
  children: ReactNode;
  header: ReactNode;
  onSwipe: (decision: DecisionValue) => void;
  disabled?: boolean;
}) {
  const start = useRef<{ x: number; y: number; vertical: boolean } | null>(null);
  const [offset, setOffset] = useState({ x: 0, y: 0 });

  const direction =
    offset.x > THRESHOLD / 2
      ? "include"
      : offset.x < -THRESHOLD / 2
        ? "exclude"
        : offset.y < -THRESHOLD / 2
          ? "maybe"
          : null;

  const begin = (event: PointerEvent<HTMLDivElement>, vertical: boolean) => {
    if (disabled || event.pointerType === "mouse") return;
    start.current = { x: event.clientX, y: event.clientY, vertical };
  };
  const move = (event: PointerEvent<HTMLDivElement>) => {
    if (!start.current) return;
    const x = event.clientX - start.current.x;
    const y = start.current.vertical ? Math.min(0, event.clientY - start.current.y) : 0;
    setOffset({ x, y });
  };
  const end = () => {
    const decided =
      offset.x > THRESHOLD
        ? "include"
        : offset.x < -THRESHOLD
          ? "exclude"
          : offset.y < -THRESHOLD
            ? "maybe"
            : null;
    start.current = null;
    setOffset({ x: 0, y: 0 });
    if (decided) onSwipe(decided);
  };

  return (
    <div
      onPointerMove={move}
      onPointerUp={end}
      onPointerCancel={end}
      onPointerDown={(event) => {
        begin(event, false);
      }}
      style={{
        transform: `translate(${offset.x}px, ${offset.y}px) rotate(${offset.x / 30}deg)`,
        touchAction: "pan-y",
      }}
      className={cn(
        "relative grid gap-4 rounded-xl border bg-card p-4 shadow-sm motion-safe:transition-transform motion-safe:duration-150",
        direction === "include" && "border-include",
        direction === "exclude" && "border-exclude",
        direction === "maybe" && "border-maybe",
        !direction && "border-border",
      )}
    >
      <div
        onPointerDown={(event) => {
          event.stopPropagation();
          begin(event, true);
        }}
        style={{ touchAction: "none" }}
      >
        {header}
      </div>
      {direction && (
        <p
          aria-hidden="true"
          className={cn(
            "absolute top-3 right-3 rounded-md px-2 py-0.5 text-sm font-semibold text-white",
            direction === "include" && "bg-include",
            direction === "exclude" && "bg-exclude",
            direction === "maybe" && "bg-maybe",
          )}
        >
          {direction === "include" ? "Include" : direction === "exclude" ? "Exclude" : "Maybe"}
        </p>
      )}
      {children}
    </div>
  );
}
