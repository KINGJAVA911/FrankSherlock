import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useAutoUpdate } from "../../hooks/useAutoUpdate";

const mockCheck = vi.fn();
const mockRelaunch = vi.fn();
const mockDownloadAndInstall = vi.fn();

vi.mock("@tauri-apps/plugin-updater", () => ({
  check: (...args: unknown[]) => mockCheck(...args),
}));

vi.mock("@tauri-apps/plugin-process", () => ({
  relaunch: (...args: unknown[]) => mockRelaunch(...args),
}));

describe("useAutoUpdate", () => {
  const callbacks = {
    onNotice: vi.fn(),
    onError: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockCheck.mockResolvedValue(null);
    mockDownloadAndInstall.mockResolvedValue(undefined);
    mockRelaunch.mockResolvedValue(undefined);
  });

  it("checks for updates silently on mount", async () => {
    renderHook(() => useAutoUpdate(callbacks));
    await waitFor(() => expect(mockCheck).toHaveBeenCalled());
    // Silent check — no notice when no update
    expect(callbacks.onNotice).not.toHaveBeenCalled();
  });

  it("sets updateInfo when update is available", async () => {
    mockCheck.mockResolvedValue({
      version: "2.0.0",
      body: "New features",
      downloadAndInstall: mockDownloadAndInstall,
    });

    const { result } = renderHook(() => useAutoUpdate(callbacks));
    await waitFor(() => expect(result.current.updateInfo).not.toBeNull());
    expect(result.current.updateInfo).toEqual({ version: "2.0.0", body: "New features" });
  });

  it("shows notice when manual check finds no update", async () => {
    mockCheck.mockResolvedValue(null);
    const { result } = renderHook(() => useAutoUpdate(callbacks));

    // Wait for silent startup check to complete
    await waitFor(() => expect(result.current.updateChecking).toBe(false));

    await act(async () => {
      await result.current.checkForUpdates(false);
    });
    expect(callbacks.onNotice).toHaveBeenCalledWith("You're running the latest version");
  });

  it("does not show notice on silent check with no update", async () => {
    mockCheck.mockResolvedValue(null);
    const { result } = renderHook(() => useAutoUpdate(callbacks));

    await waitFor(() => expect(result.current.updateChecking).toBe(false));
    expect(callbacks.onNotice).not.toHaveBeenCalled();
  });

  it("shows error on manual check failure", async () => {
    mockCheck.mockRejectedValue(new Error("network error"));
    const { result } = renderHook(() => useAutoUpdate(callbacks));

    // Wait for silent startup check to fail
    await waitFor(() => expect(result.current.updateChecking).toBe(false));

    await act(async () => {
      await result.current.checkForUpdates(false);
    });
    expect(callbacks.onError).toHaveBeenCalledWith("Could not check for updates");
  });

  it("does not show error on silent check failure", async () => {
    mockCheck.mockRejectedValue(new Error("network error"));
    const { result } = renderHook(() => useAutoUpdate(callbacks));

    await waitFor(() => expect(result.current.updateChecking).toBe(false));
    // onError called once for the silent startup, but silent=true so no error shown
    expect(callbacks.onError).not.toHaveBeenCalled();
  });

  it("sets updateChecking during check", async () => {
    let resolveCheck!: (val: null) => void;
    mockCheck.mockReturnValue(new Promise((r) => { resolveCheck = r; }));

    const { result } = renderHook(() => useAutoUpdate(callbacks));
    expect(result.current.updateChecking).toBe(true);

    await act(async () => { resolveCheck(null); });
    expect(result.current.updateChecking).toBe(false);
  });
});
