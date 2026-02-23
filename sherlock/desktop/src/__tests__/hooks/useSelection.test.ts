import { describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useSelection } from "../../hooks/useSelection";

describe("useSelection", () => {
  it("starts with empty selection", () => {
    const { result } = renderHook(() => useSelection());
    expect(result.current.selectedIndices.size).toBe(0);
    expect(result.current.focusIndex).toBeNull();
    expect(result.current.anchorIndex).toBeNull();
  });

  it("selectOnly sets single selection and focus", () => {
    const { result } = renderHook(() => useSelection());
    act(() => result.current.selectOnly(5));
    expect(result.current.selectedIndices).toEqual(new Set([5]));
    expect(result.current.focusIndex).toBe(5);
    expect(result.current.anchorIndex).toBe(5);
  });

  it("toggleSelect adds and removes", () => {
    const { result } = renderHook(() => useSelection());
    act(() => result.current.toggleSelect(3));
    expect(result.current.selectedIndices.has(3)).toBe(true);
    act(() => result.current.toggleSelect(3));
    expect(result.current.selectedIndices.has(3)).toBe(false);
  });

  it("rangeSelect selects range inclusive", () => {
    const { result } = renderHook(() => useSelection());
    act(() => result.current.selectOnly(2));
    act(() => result.current.rangeSelect(2, 5));
    expect(result.current.selectedIndices).toEqual(new Set([2, 3, 4, 5]));
    expect(result.current.focusIndex).toBe(5);
  });

  it("selectAll selects all indices", () => {
    const { result } = renderHook(() => useSelection());
    act(() => result.current.selectAll(10));
    expect(result.current.selectedIndices.size).toBe(10);
  });

  it("clearSelection resets everything", () => {
    const { result } = renderHook(() => useSelection());
    act(() => result.current.selectOnly(3));
    act(() => result.current.clearSelection());
    expect(result.current.selectedIndices.size).toBe(0);
    expect(result.current.focusIndex).toBeNull();
    expect(result.current.anchorIndex).toBeNull();
  });
});
