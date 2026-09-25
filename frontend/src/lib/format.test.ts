import { describe, expect, test } from "vitest";

import { describeDevice, fileSize, initials, timeAgo } from "@/lib/format";

describe("formatters", () => {
  test("devices", () => {
    expect(
      describeDevice("Mozilla/5.0 (Windows NT 10.0) AppleWebKit Chrome/140 Safari/537 Edg/140"),
    ).toBe("Edge on Windows");
    expect(describeDevice("Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko Firefox/130.0")).toBe(
      "Firefox on Linux",
    );
    expect(describeDevice("Mozilla/5.0 (Linux; Android 15) Chrome/140 Mobile Safari/537")).toBe(
      "Chrome on Android",
    );
    expect(describeDevice("curl/8.0")).toBe("Unknown device");
    expect(describeDevice(null)).toBe("Unknown device");
  });

  test("file sizes", () => {
    expect(fileSize(512)).toBe("512 bytes");
    expect(fileSize(2048)).toBe("2.0 KB");
    expect(fileSize(860_000)).toBe("840 KB");
    expect(fileSize(13 * 1024 ** 2)).toBe("13.0 MB");
    expect(fileSize(3 * 1024 ** 4)).toBe("3072 GB");
  });

  test("relative times", () => {
    const now = Date.parse("2026-09-22T12:00:00Z");
    expect(timeAgo("2026-09-22T11:59:50Z", now)).toBe("just now");
    expect(timeAgo("2026-09-22T11:55:00Z", now)).toBe("5 minutes ago");
    expect(timeAgo("2026-09-21T12:00:00Z", now)).toBe("yesterday");
  });

  test("initials", () => {
    expect(initials("Ada Lovelace")).toBe("AL");
    expect(initials("ada")).toBe("A");
    expect(initials("Mary Ann Evans")).toBe("ME");
    expect(initials("   ")).toBe("?");
  });
});
