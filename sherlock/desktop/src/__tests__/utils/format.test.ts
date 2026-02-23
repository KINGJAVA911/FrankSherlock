import { describe, it, expect } from "vitest";
import { fileName, formatBytes, formatElapsed } from "../../utils/format";

describe("fileName", () => {
  it("extracts filename from path with slashes", () => {
    expect(fileName("photos/vacation/beach.jpg")).toBe("beach.jpg");
  });

  it("returns the string when no slash present", () => {
    expect(fileName("image.png")).toBe("image.png");
  });

  it("handles deeply nested paths", () => {
    expect(fileName("a/b/c/d/file.txt")).toBe("file.txt");
  });

  it("handles trailing slash edge case", () => {
    expect(fileName("folder/")).toBe("");
  });
});

describe("formatBytes", () => {
  it("formats bytes", () => {
    expect(formatBytes(500)).toBe("500 B");
  });

  it("formats kilobytes", () => {
    expect(formatBytes(2048)).toBe("2.0 KB");
  });

  it("formats megabytes", () => {
    expect(formatBytes(5242880)).toBe("5.0 MB");
  });

  it("formats gigabytes", () => {
    expect(formatBytes(1073741824)).toBe("1.00 GB");
  });

  it("formats zero", () => {
    expect(formatBytes(0)).toBe("0 B");
  });
});

describe("formatElapsed", () => {
  it("returns n/a when completedAt is null", () => {
    expect(formatElapsed(100, null)).toBe("n/a");
  });

  it("returns n/a when completedAt is undefined", () => {
    expect(formatElapsed(100, undefined)).toBe("n/a");
  });

  it("returns n/a when completedAt is 0", () => {
    expect(formatElapsed(100, 0)).toBe("n/a");
  });

  it("formats seconds only", () => {
    expect(formatElapsed(0, 45)).toBe("45s");
  });

  it("formats minutes and seconds", () => {
    expect(formatElapsed(0, 125)).toBe("2m 5s");
  });

  it("formats hours and minutes", () => {
    expect(formatElapsed(0, 3665)).toBe("1h 1m");
  });

  it("formats exactly 60 seconds as 1m 0s", () => {
    expect(formatElapsed(0, 60)).toBe("1m 0s");
  });

  it("formats exactly 1 hour", () => {
    expect(formatElapsed(0, 3600)).toBe("1h 0m");
  });
});
