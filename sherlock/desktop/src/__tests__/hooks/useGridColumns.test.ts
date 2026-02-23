import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook } from "@testing-library/react";
import { useGridColumns } from "../../hooks/useGridColumns";

describe("useGridColumns", () => {
  let observeCallback: ResizeObserverCallback;

  beforeEach(() => {
    vi.stubGlobal("ResizeObserver", class {
      constructor(cb: ResizeObserverCallback) { observeCallback = cb; }
      observe() {}
      disconnect() {}
    });
  });

  it("defaults to 1 column", () => {
    const ref = { current: document.createElement("div") };
    const { result } = renderHook(() => useGridColumns(ref));
    expect(result.current.current).toBe(1);
  });

  it("calculates columns from width", () => {
    const ref = { current: document.createElement("div") };
    const { result } = renderHook(() => useGridColumns(ref));
    // Simulate width of 700px: (700 + 6) / (220 + 6) = 3.12 -> floor = 3
    observeCallback([{ contentRect: { width: 700 } } as ResizeObserverEntry], {} as ResizeObserver);
    expect(result.current.current).toBe(3);
  });

  it("returns at least 1 column for narrow width", () => {
    const ref = { current: document.createElement("div") };
    const { result } = renderHook(() => useGridColumns(ref));
    observeCallback([{ contentRect: { width: 50 } } as ResizeObserverEntry], {} as ResizeObserver);
    expect(result.current.current).toBe(1);
  });
});
