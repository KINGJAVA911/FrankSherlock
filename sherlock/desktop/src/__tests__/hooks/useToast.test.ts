import { describe, it, expect, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useToast } from "../../hooks/useToast";

describe("useToast", () => {
  it("starts with null notice and error", () => {
    const { result } = renderHook(() => useToast());
    expect(result.current.notice).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it("sets and returns notice", () => {
    const { result } = renderHook(() => useToast());
    act(() => result.current.setNotice("hello"));
    expect(result.current.notice).toBe("hello");
  });

  it("sets and returns error", () => {
    const { result } = renderHook(() => useToast());
    act(() => result.current.setError("oops"));
    expect(result.current.error).toBe("oops");
  });

  it("auto-dismisses notice after 6s", () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useToast());
    act(() => result.current.setNotice("will disappear"));
    expect(result.current.notice).toBe("will disappear");
    act(() => { vi.advanceTimersByTime(6000); });
    expect(result.current.notice).toBeNull();
    vi.useRealTimers();
  });

  it("auto-dismisses error after 10s", () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useToast());
    act(() => result.current.setError("will disappear"));
    expect(result.current.error).toBe("will disappear");
    act(() => { vi.advanceTimersByTime(10000); });
    expect(result.current.error).toBeNull();
    vi.useRealTimers();
  });
});
