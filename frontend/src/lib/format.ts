const relative = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
const STEPS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 365 * 24 * 3600],
  ["month", 30 * 24 * 3600],
  ["week", 7 * 24 * 3600],
  ["day", 24 * 3600],
  ["hour", 3600],
  ["minute", 60],
];

/** "5 minutes ago", "yesterday", "just now". */
export function timeAgo(iso: string, now: number = Date.now()): string {
  const seconds = (new Date(iso).getTime() - now) / 1000;
  for (const [unit, size] of STEPS) {
    if (Math.abs(seconds) >= size) return relative.format(Math.round(seconds / size), unit);
  }
  return "just now";
}

/** A short, human description of a browser from its user agent. Best effort. */
export function describeDevice(userAgent: string | null | undefined): string {
  if (!userAgent) return "Unknown device";
  const browser = userAgent.includes("Edg/")
    ? "Edge"
    : userAgent.includes("Firefox/")
      ? "Firefox"
      : userAgent.includes("Chrome/")
        ? "Chrome"
        : userAgent.includes("Safari/")
          ? "Safari"
          : null;
  const system = /iPhone|iPad/.test(userAgent)
    ? "iOS"
    : userAgent.includes("Android")
      ? "Android"
      : userAgent.includes("Mac OS X")
        ? "macOS"
        : userAgent.includes("Windows")
          ? "Windows"
          : userAgent.includes("Linux")
            ? "Linux"
            : null;
  if (browser && system) return `${browser} on ${system}`;
  return browser ?? system ?? "Unknown device";
}

/** Up to two initials for an avatar: "Ada Lovelace" → "AL". */
export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const first = parts[0]?.[0] ?? "";
  const last = parts.length > 1 ? (parts.at(-1)?.[0] ?? "") : "";
  return (first + last).toUpperCase() || "?";
}

const SIZES = ["bytes", "KB", "MB", "GB"] as const;

/** "840 KB", "12.4 MB": a file's size as people read it. */
export function fileSize(bytes: number): string {
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < SIZES.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const shown = unit === 0 || value >= 100 ? Math.round(value).toString() : value.toFixed(1);
  return `${shown} ${SIZES[unit]}`;
}
