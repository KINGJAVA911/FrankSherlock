import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useAlbumManager } from "../../hooks/useAlbumManager";
import { listAlbums, createAlbum, deleteAlbum, addFilesToAlbum, reorderAlbums } from "../../api";
import { mockAlbum } from "../fixtures";

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return {
    ...actual,
    listAlbums: vi.fn(),
    createAlbum: vi.fn(),
    deleteAlbum: vi.fn(),
    addFilesToAlbum: vi.fn(),
    reorderAlbums: vi.fn(),
  };
});

describe("useAlbumManager", () => {
  const callbacks = {
    onNotice: vi.fn(),
    onError: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listAlbums).mockResolvedValue([mockAlbum]);
    vi.mocked(createAlbum).mockResolvedValue(mockAlbum);
    vi.mocked(deleteAlbum).mockResolvedValue(undefined);
    vi.mocked(addFilesToAlbum).mockResolvedValue(3);
    vi.mocked(reorderAlbums).mockResolvedValue(undefined);
  });

  it("starts with empty albums", () => {
    const { result } = renderHook(() => useAlbumManager(callbacks));
    expect(result.current.albums).toEqual([]);
    expect(result.current.showCreateAlbum).toBe(false);
    expect(result.current.pendingAlbumFileIds).toEqual([]);
  });

  it("refreshAlbums loads albums", async () => {
    const { result } = renderHook(() => useAlbumManager(callbacks));
    await act(async () => {
      await result.current.refreshAlbums();
    });
    expect(result.current.albums).toEqual([mockAlbum]);
  });

  it("onSelectAlbum returns query for simple name", () => {
    const { result } = renderHook(() => useAlbumManager(callbacks));
    const { query } = result.current.onSelectAlbum(mockAlbum);
    expect(query).toBe("album:Vacation");
  });

  it("onSelectAlbum returns quoted query for name with spaces", () => {
    const { result } = renderHook(() => useAlbumManager(callbacks));
    const spaced = { ...mockAlbum, name: "My Vacation" };
    const { query } = result.current.onSelectAlbum(spaced);
    expect(query).toBe('album:"My Vacation"');
  });

  it("onDeleteAlbum deletes and refreshes", async () => {
    const { result } = renderHook(() => useAlbumManager(callbacks));
    await act(async () => {
      await result.current.onDeleteAlbum(mockAlbum);
    });
    expect(deleteAlbum).toHaveBeenCalledWith(mockAlbum.id);
    expect(listAlbums).toHaveBeenCalled();
    expect(callbacks.onNotice).toHaveBeenCalledWith('Deleted album "Vacation"');
  });

  it("onAddToAlbum adds files and refreshes", async () => {
    const { result } = renderHook(() => useAlbumManager(callbacks));
    await act(async () => {
      await result.current.onAddToAlbum(1, [10, 11, 12]);
    });
    expect(addFilesToAlbum).toHaveBeenCalledWith(1, [10, 11, 12]);
    expect(callbacks.onNotice).toHaveBeenCalledWith("Added 3 file(s) to album");
  });

  it("onAddToAlbum skips when no fileIds", async () => {
    const { result } = renderHook(() => useAlbumManager(callbacks));
    await act(async () => {
      await result.current.onAddToAlbum(1, []);
    });
    expect(addFilesToAlbum).not.toHaveBeenCalled();
  });

  it("onCreateAlbumFromSelection opens modal with pending files", () => {
    const { result } = renderHook(() => useAlbumManager(callbacks));
    act(() => {
      result.current.onCreateAlbumFromSelection([1, 2, 3]);
    });
    expect(result.current.showCreateAlbum).toBe(true);
    expect(result.current.pendingAlbumFileIds).toEqual([1, 2, 3]);
  });

  it("onCreateAlbumConfirm creates album with pending files", async () => {
    const { result } = renderHook(() => useAlbumManager(callbacks));
    act(() => {
      result.current.onCreateAlbumFromSelection([10, 11]);
    });
    await act(async () => {
      await result.current.onCreateAlbumConfirm("New Album");
    });
    expect(createAlbum).toHaveBeenCalledWith("New Album");
    expect(addFilesToAlbum).toHaveBeenCalledWith(mockAlbum.id, [10, 11]);
    expect(result.current.showCreateAlbum).toBe(false);
    expect(result.current.pendingAlbumFileIds).toEqual([]);
  });

  it("onReorderAlbums calls API and refreshes", async () => {
    const { result } = renderHook(() => useAlbumManager(callbacks));
    await act(async () => {
      await result.current.onReorderAlbums([2, 1]);
    });
    expect(reorderAlbums).toHaveBeenCalledWith([2, 1]);
    expect(listAlbums).toHaveBeenCalled();
  });

  it("closeCreateModal resets state", () => {
    const { result } = renderHook(() => useAlbumManager(callbacks));
    act(() => {
      result.current.onCreateAlbumFromSelection([1, 2]);
    });
    act(() => {
      result.current.closeCreateModal();
    });
    expect(result.current.showCreateAlbum).toBe(false);
    expect(result.current.pendingAlbumFileIds).toEqual([]);
  });

  it("shows error on delete failure", async () => {
    vi.mocked(deleteAlbum).mockRejectedValue(new Error("delete failed"));
    const { result } = renderHook(() => useAlbumManager(callbacks));
    await act(async () => {
      await result.current.onDeleteAlbum(mockAlbum);
    });
    expect(callbacks.onError).toHaveBeenCalledWith("delete failed");
  });
});
