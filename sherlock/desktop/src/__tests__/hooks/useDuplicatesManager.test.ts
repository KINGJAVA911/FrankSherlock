import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useDuplicatesManager } from "../../hooks/useDuplicatesManager";
import { findDuplicates } from "../../api";
import { mockDuplicatesResponse, mockDuplicateGroup, mockDuplicateFileKeeper, mockDuplicateFileCopy } from "../fixtures";

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return {
    ...actual,
    findDuplicates: vi.fn(),
  };
});

describe("useDuplicatesManager", () => {
  const callbacks = {
    onNotice: vi.fn(),
    onError: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(findDuplicates).mockResolvedValue(mockDuplicatesResponse);
  });

  it("starts with default state", () => {
    const { result } = renderHook(() => useDuplicatesManager(callbacks));
    expect(result.current.duplicatesMode).toBe(false);
    expect(result.current.duplicatesData).toBeNull();
    expect(result.current.duplicatesLoading).toBe(false);
    expect(result.current.duplicatesSelected.size).toBe(0);
    expect(result.current.nearEnabled).toBe(false);
    expect(result.current.nearThreshold).toBe(0.85);
    expect(result.current.dupPreviewItems).toEqual([]);
  });

  it("onFindDuplicates enters mode and loads data", async () => {
    const { result } = renderHook(() => useDuplicatesManager(callbacks));
    await act(async () => {
      await result.current.onFindDuplicates();
    });
    expect(result.current.duplicatesMode).toBe(true);
    expect(result.current.duplicatesData).toEqual(mockDuplicatesResponse);
    expect(result.current.duplicatesLoading).toBe(false);
  });

  it("onFindDuplicates shows error and exits mode on failure", async () => {
    vi.mocked(findDuplicates).mockRejectedValue(new Error("fail"));
    const { result } = renderHook(() => useDuplicatesManager(callbacks));
    await act(async () => {
      await result.current.onFindDuplicates();
    });
    expect(result.current.duplicatesMode).toBe(false);
    expect(callbacks.onError).toHaveBeenCalledWith("fail");
  });

  it("onToggleFile toggles selection", async () => {
    const { result } = renderHook(() => useDuplicatesManager(callbacks));
    act(() => result.current.onToggleFile(11));
    expect(result.current.duplicatesSelected.has(11)).toBe(true);
    act(() => result.current.onToggleFile(11));
    expect(result.current.duplicatesSelected.has(11)).toBe(false);
  });

  it("onSelectAllDuplicates selects non-keepers", async () => {
    const { result } = renderHook(() => useDuplicatesManager(callbacks));
    await act(async () => {
      await result.current.onFindDuplicates();
    });
    act(() => result.current.onSelectAllDuplicates());
    // mockDuplicateFileCopy is non-keeper (id: 11), keeper (id: 10) should not be selected
    expect(result.current.duplicatesSelected.has(11)).toBe(true);
    expect(result.current.duplicatesSelected.has(10)).toBe(false);
  });

  it("onDeselectAll clears selection", () => {
    const { result } = renderHook(() => useDuplicatesManager(callbacks));
    act(() => result.current.onToggleFile(11));
    expect(result.current.duplicatesSelected.size).toBe(1);
    act(() => result.current.onDeselectAll());
    expect(result.current.duplicatesSelected.size).toBe(0);
  });

  it("onSelectGroupDuplicates adds non-keepers from group", async () => {
    const { result } = renderHook(() => useDuplicatesManager(callbacks));
    act(() => result.current.onSelectGroupDuplicates(mockDuplicateGroup));
    expect(result.current.duplicatesSelected.has(11)).toBe(true);
    expect(result.current.duplicatesSelected.has(10)).toBe(false);
  });

  it("onPreviewGroup converts files to SearchItems", () => {
    const { result } = renderHook(() => useDuplicatesManager(callbacks));
    act(() => result.current.onPreviewGroup(mockDuplicateGroup));
    expect(result.current.dupPreviewItems).toHaveLength(2);
    expect(result.current.dupPreviewItems[0].id).toBe(mockDuplicateFileKeeper.id);
    expect(result.current.dupPreviewItems[1].id).toBe(mockDuplicateFileCopy.id);
  });

  it("getDeleteSearchItems returns selected items", async () => {
    const { result } = renderHook(() => useDuplicatesManager(callbacks));
    await act(async () => {
      await result.current.onFindDuplicates();
    });
    act(() => result.current.onToggleFile(11));
    const items = result.current.getDeleteSearchItems();
    expect(items).toHaveLength(1);
    expect(items[0].id).toBe(11);
  });

  it("getDeleteFileIds returns selected ids", async () => {
    const { result } = renderHook(() => useDuplicatesManager(callbacks));
    await act(async () => {
      await result.current.onFindDuplicates();
    });
    act(() => result.current.onToggleFile(11));
    expect(result.current.getDeleteFileIds()).toEqual([11]);
  });

  it("onBack resets state", async () => {
    const { result } = renderHook(() => useDuplicatesManager(callbacks));
    await act(async () => {
      await result.current.onFindDuplicates();
    });
    act(() => result.current.onBack());
    expect(result.current.duplicatesMode).toBe(false);
    expect(result.current.duplicatesData).toBeNull();
    expect(result.current.duplicatesSelected.size).toBe(0);
  });

  it("refreshAfterDelete reloads data and clears selection", async () => {
    const { result } = renderHook(() => useDuplicatesManager(callbacks));
    await act(async () => {
      await result.current.onFindDuplicates();
    });
    act(() => result.current.onToggleFile(11));

    await act(async () => {
      await result.current.refreshAfterDelete();
    });
    expect(result.current.duplicatesSelected.size).toBe(0);
    expect(findDuplicates).toHaveBeenCalledTimes(2);
  });

  it("onNearEnabledChange triggers re-search", async () => {
    const { result } = renderHook(() => useDuplicatesManager(callbacks));
    await act(async () => {
      result.current.onNearEnabledChange(true);
    });
    expect(findDuplicates).toHaveBeenCalledWith([], 0.85);
  });

  it("onNearThresholdChange triggers re-search", async () => {
    const { result } = renderHook(() => useDuplicatesManager(callbacks));
    await act(async () => {
      result.current.onNearThresholdChange(0.9);
    });
    expect(findDuplicates).toHaveBeenCalledWith([], 0.9);
  });
});
