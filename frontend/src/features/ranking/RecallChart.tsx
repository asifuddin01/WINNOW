import { useEffect, useId, useMemo, useRef, useState } from "react";

import type { Curve } from "@/api/ranking";
import { foundAfter, ticks, type Series } from "@/features/ranking/curve";

const HEIGHT = 240;
const MARGIN = { top: 16, right: 72, bottom: 36, left: 44 };

function useWidth(fallback: number) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const element = ref.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setWidth(Math.max(240, Math.round(entry.contentRect.width)));
    });
    observer.observe(element);
    return () => {
      observer.disconnect();
    };
  }, []);
  return [ref, width] as const;
}

/**
 * The recall curve (guide 8.10): relevant records found against records screened, as
 * steps. A dashed line shows the same finds at an even pace, which is what screening in
 * random order gives on average; the further the curve bows above it, the more screening
 * the ranking has saved.
 */
export function RecallChart({ series, caption }: { series: Series[]; caption: string }) {
  const [ref, width] = useWidth(640);
  const titleId = useId();
  const [hover, setHover] = useState<number | null>(null);

  const xMax = Math.max(1, ...series.map((line) => line.curve.screened));
  const yMax = Math.max(1, ...series.map((line) => line.curve.found_at.length));
  const xTicks = useMemo(() => ticks(xMax), [xMax]);
  const yTicks = useMemo(() => ticks(yMax, 4), [yMax]);
  const xTop = xTicks.at(-1) ?? xMax;
  const yTop = yTicks.at(-1) ?? yMax;
  const plotWidth = width - MARGIN.left - MARGIN.right;
  const plotHeight = HEIGHT - MARGIN.top - MARGIN.bottom;
  const x = (value: number) => MARGIN.left + (value / xTop) * plotWidth;
  const y = (value: number) => MARGIN.top + plotHeight - (value / yTop) * plotHeight;
  const lead = series[0];

  const path = (curve: Curve) => {
    let d = `M${x(0)},${y(0)}`;
    curve.found_at.forEach((position, index) => {
      d += `H${x(position)}V${y(index + 1)}`;
    });
    return `${d}H${x(curve.screened)}`;
  };

  const step = Math.max(1, Math.round(xTop / 100));
  const at = hover === null ? null : Math.min(xMax, Math.max(0, hover));

  return (
    <figure className="grid gap-2">
      <div ref={ref} className="relative w-full">
        <svg
          role="img"
          aria-labelledby={titleId}
          width={width}
          height={HEIGHT}
          tabIndex={0}
          className="recall-chart block max-w-full touch-none rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring"
          onPointerMove={(event) => {
            const box = event.currentTarget.getBoundingClientRect();
            const value = ((event.clientX - box.left - MARGIN.left) / plotWidth) * xTop;
            setHover(Math.round(value));
          }}
          onPointerLeave={() => {
            setHover(null);
          }}
          onFocus={() => {
            setHover((value) => value ?? xMax);
          }}
          onBlur={() => {
            setHover(null);
          }}
          onKeyDown={(event) => {
            if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
              event.preventDefault();
              const by = event.key === "ArrowLeft" ? -step : step;
              setHover((value) => Math.min(xMax, Math.max(0, (value ?? xMax) + by)));
            }
          }}
        >
          <title id={titleId}>{caption}</title>
          {yTicks.map((tick) => (
            <g key={`y${tick}`}>
              <line
                x1={MARGIN.left}
                x2={MARGIN.left + plotWidth}
                y1={y(tick)}
                y2={y(tick)}
                className="stroke-border"
                strokeWidth={1}
              />
              <text
                x={MARGIN.left - 8}
                y={y(tick)}
                dy="0.32em"
                textAnchor="end"
                className="fill-muted-foreground text-[11px] tabular-nums"
              >
                {tick.toLocaleString()}
              </text>
            </g>
          ))}
          {xTicks.map((tick) => (
            <text
              key={`x${tick}`}
              x={x(tick)}
              y={MARGIN.top + plotHeight + 18}
              textAnchor="middle"
              className="fill-muted-foreground text-[11px] tabular-nums"
            >
              {tick.toLocaleString()}
            </text>
          ))}
          <text
            x={MARGIN.left + plotWidth / 2}
            y={HEIGHT - 4}
            textAnchor="middle"
            className="fill-muted-foreground text-[11px]"
          >
            Records screened
          </text>
          {lead && lead.curve.found_at.length > 0 && (
            <line
              x1={x(0)}
              y1={y(0)}
              x2={x(lead.curve.screened)}
              y2={y(lead.curve.found_at.length)}
              className="stroke-muted-foreground"
              strokeWidth={1.5}
              strokeDasharray="4 4"
            />
          )}
          {series.map((line) => (
            <path
              key={line.key}
              d={path(line.curve)}
              fill="none"
              stroke={`var(--chart-${line.key})`}
              strokeWidth={2}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          ))}
          {series.map((line) => {
            const found = line.curve.found_at.length;
            return (
              <g key={`end-${line.key}`}>
                <circle
                  cx={x(line.curve.screened)}
                  cy={y(found)}
                  r={4}
                  fill={`var(--chart-${line.key})`}
                  className="stroke-card"
                  strokeWidth={2}
                />
                <text
                  x={x(line.curve.screened) + 8}
                  y={y(found)}
                  dy="0.32em"
                  className="fill-foreground text-[11px] font-medium"
                >
                  {line.label} {found.toLocaleString()}
                </text>
              </g>
            );
          })}
          {at !== null && (
            <line
              x1={x(at)}
              x2={x(at)}
              y1={MARGIN.top}
              y2={MARGIN.top + plotHeight}
              className="stroke-foreground/40"
              strokeWidth={1}
            />
          )}
        </svg>
        {at !== null && (
          <div
            role="status"
            className="pointer-events-none absolute top-2 rounded-md border bg-popover px-2 py-1 text-xs shadow-sm"
            style={{
              left: Math.min(Math.max(x(at) + 8, 0), Math.max(0, width - 180)),
            }}
          >
            <p className="text-muted-foreground">
              After <span className="tabular-nums">{at.toLocaleString()}</span> screened
            </p>
            {series.map((line) => (
              <p key={line.key} className="flex items-center gap-1.5">
                <span
                  aria-hidden="true"
                  className="inline-block h-0.5 w-3 rounded-full"
                  style={{ background: `var(--chart-${line.key})` }}
                />
                <span className="font-semibold tabular-nums">
                  {foundAfter(line.curve, at).toLocaleString()}
                </span>
                <span className="text-muted-foreground">{line.label.toLowerCase()}</span>
              </p>
            ))}
          </div>
        )}
      </div>
      <figcaption className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {series.map((line) => (
          <span key={line.key} className="flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className="inline-block h-0.5 w-4 rounded-full"
              style={{ background: `var(--chart-${line.key})` }}
            />
            {line.label}
          </span>
        ))}
        {lead && lead.curve.found_at.length > 0 && (
          <span className="flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className="inline-block w-4 border-t-[1.5px] border-dashed border-muted-foreground"
            />
            Same finds at an even pace (random order, on average)
          </span>
        )}
      </figcaption>
      <details className="text-sm">
        <summary className="cursor-pointer text-xs font-medium text-primary">
          Show as a table
        </summary>
        <CurveTable series={series} xMax={xMax} />
      </details>
    </figure>
  );
}

function CurveTable({ series, xMax }: { series: Series[]; xMax: number }) {
  const rows = [...new Set([...ticks(xMax, 8).filter((tick) => tick < xMax), xMax])];
  return (
    <table className="mt-2 w-full text-left text-xs tabular-nums">
      <thead>
        <tr className="border-b">
          <th scope="col" className="py-1 font-medium">
            Records screened
          </th>
          {series.map((line) => (
            <th key={line.key} scope="col" className="py-1 font-medium">
              Relevant found: {line.label.toLowerCase()}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row} className="border-b last:border-0">
            <td className="py-1">{row.toLocaleString()}</td>
            {series.map((line) => (
              <td key={line.key} className="py-1">
                {row <= line.curve.screened ? foundAfter(line.curve, row).toLocaleString() : "—"}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
