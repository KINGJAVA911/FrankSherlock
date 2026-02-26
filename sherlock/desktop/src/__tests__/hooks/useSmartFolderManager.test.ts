import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useSmartFolderManager } from "../../hooks/useSmartFolderManager";
import { listSmartFolders, createSmartFolder, deleteSmartFolder, reorderSmartFolders } from "../../api";
import { mockSmartFolder } from "../fixtures";

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return {
    ...actual,
    listSmartFolders: vi.fn(),
    createSmartFolder: vi.fn(),
    deleteSmartFolder: vi.fn(),
    reorderSmartFolders: vi.fn(),
  };
});

describe("useSmartFolderManager", () => {
  const callbacks = {
    onNotice: vi.fn(),
    onError: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listSmartFolders).mockResolvedValue([mockSmartFolder]);
    vi.mocked(createSmartFolder).mockResolvedValue(mockSmartFolder);
    vi.mocked(deleteSmartFolder).mockResolvedValue(undefined);
    vi.mocked(reorderSmartFolders).mockResolvedValue(undefined);
  });

  it("starts with empty state", () => {
    const { result } = renderHook(() => useSmartFolderManager(callbacks));
    expect(result.current.smartFolders).toEqual([]);
    expect(result.current.showCreateSmartFolder).toBe(false);
    expect(result.current.activeSmartFolderId).toBeNull();
  });

  it("refreshSmartFolders loads folders", async () => {
    const { result } = renderHook(() => useSmartFolderManager(callbacks));
    await act(async () => {
      await result.current.refreshSmartFolders();
    });
    expect(result.current.smartFolders).toEqual([mockSmartFolder]);
  });

  it("onSelectSmartFolder returns query and sets active id", () => {
    const { result } = renderHook(() => useSmartFolderManager(callbacks));
    let query: string;
    act(() => {
      ({ query } = result.current.onSelectSmartFolder(mockSmartFolder));
    });
    expect(query!).toBe("anime photo");
    expect(result.current.activeSmartFolderId).toBe(1);
  });

  it("onDeleteSmartFolder deletes and refreshes", async () => {
    const { result } = renderHook(() => useSmartFolderManager(callbacks));
    await act(async () => {
      await result.current.onDeleteSmartFolder(mockSmartFolder);
    });
    expect(deleteSmartFolder).toHaveBeenCalledWith(mockSmartFolder.id);
    expect(listSmartFolders).toHaveBeenCalled();
    expect(callbacks.onNotice).toHaveBeenCalledWith('Deleted smart folder "Anime photos"');
  });

  it("onDeleteSmartFolder clears active id when deleting active folder", async () => {
    const { result } = renderHook(() => useSmartFolderManager(callbacks));
    // Set active
    act(() => {
      result.current.onSelectSmartFolder(mockSmartFolder);
    });
    expect(result.current.activeSmartFolderId).toBe(1);

    await act(async () => {
      await result.current.onDeleteSmartFolder(mockSmartFolder);
    });
    expect(result.current.activeSmartFolderId).toBeNull();
  });

  it("onCreateSmartFolderConfirm creates and sets active", async () => {
    const { result } = renderHook(() => useSmartFolderManager(callbacks));
    act(() => result.current.openCreateModal());
    expect(result.current.showCreateSmartFolder).toBe(true);

    await act(async () => {
      await result.current.onCreateSmartFolderConfirm("New Folder", "test query");
    });
    expect(createSmartFolder).toHaveBeenCalledWith("New Folder", "test query");
    expect(result.current.showCreateSmartFolder).toBe(false);
    expect(result.current.activeSmartFolderId).toBe(mockSmartFolder.id);
    expect(callbacks.onNotice).toHaveBeenCalledWith('Saved smart folder "New Folder"');
  });

  it("onReorderSmartFolders calls API and refreshes", async () => {
    const { result } = renderHook(() => useSmartFolderManager(callbacks));
    await act(async () => {
      await result.current.onReorderSmartFolders([2, 1]);
    });
    expect(reorderSmartFolders).toHaveBeenCalledWith([2, 1]);
    expect(listSmartFolders).toHaveBeenCalled();
  });

  it("closeCreateModal resets state", () => {
    const { result } = renderHook(() => useSmartFolderManager(callbacks));
    act(() => result.current.openCreateModal());
    expect(result.current.showCreateSmartFolder).toBe(true);
    act(() => result.current.closeCreateModal());
    expect(result.current.showCreateSmartFolder).toBe(false);
  });

  it("shows error on delete failure", async () => {
    vi.mocked(deleteSmartFolder).mockRejectedValue(new Error("fail"));
    const { result } = renderHook(() => useSmartFolderManager(callbacks));
    await act(async () => {
      await result.current.onDeleteSmartFolder(mockSmartFolder);
    });
    expect(callbacks.onError).toHaveBeenCalledWith("fail");
  });

  it("setActiveSmartFolderId works", () => {
    const { result } = renderHook(() => useSmartFolderManager(callbacks));
    act(() => result.current.setActiveSmartFolderId(42));
    expect(result.current.activeSmartFolderId).toBe(42);
    act(() => result.current.setActiveSmartFolderId(null));
    expect(result.current.activeSmartFolderId).toBeNull();
  });
});
