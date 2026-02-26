import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useFaceDetection } from "../../hooks/useFaceDetection";
import { detectFaces, cancelFaceDetect, getFaceDetectStatus } from "../../api";
import { mockRoot } from "../fixtures";

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return {
    ...actual,
    detectFaces: vi.fn(),
    cancelFaceDetect: vi.fn(),
    getFaceDetectStatus: vi.fn(),
  };
});

describe("useFaceDetection", () => {
  const callbacks = {
    pollMs: 500,
    onNotice: vi.fn(),
    onError: vi.fn(),
  };

  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    vi.mocked(getFaceDetectStatus).mockResolvedValue(null);
    vi.mocked(detectFaces).mockResolvedValue(undefined);
    vi.mocked(cancelFaceDetect).mockResolvedValue(true);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("starts with facesMode false and no progress", () => {
    const { result } = renderHook(() => useFaceDetection(callbacks));
    expect(result.current.facesMode).toBe(false);
    expect(result.current.faceProgress).toBeNull();
  });

  it("toggles facesMode", () => {
    const { result } = renderHook(() => useFaceDetection(callbacks));
    act(() => result.current.setFacesMode(true));
    expect(result.current.facesMode).toBe(true);
    act(() => result.current.setFacesMode(false));
    expect(result.current.facesMode).toBe(false);
  });

  it("calls detectFaces and shows notice", async () => {
    const { result } = renderHook(() => useFaceDetection(callbacks));
    await act(async () => {
      await result.current.onDetectFaces(mockRoot);
    });
    expect(detectFaces).toHaveBeenCalledWith(mockRoot.id);
    expect(callbacks.onNotice).toHaveBeenCalledWith(`Face detection started for "${mockRoot.rootName}"`);
  });

  it("shows error when detectFaces fails", async () => {
    vi.mocked(detectFaces).mockRejectedValue(new Error("fail"));
    const { result } = renderHook(() => useFaceDetection(callbacks));
    await act(async () => {
      await result.current.onDetectFaces(mockRoot);
    });
    expect(callbacks.onError).toHaveBeenCalledWith("fail");
  });

  it("calls cancelFaceDetect", async () => {
    const { result } = renderHook(() => useFaceDetection(callbacks));
    await act(async () => {
      await result.current.onCancelFaceDetect();
    });
    expect(cancelFaceDetect).toHaveBeenCalled();
  });

  it("polls face detection status", async () => {
    const progress = { rootId: 1, total: 100, processed: 50, facesFound: 10 };
    vi.mocked(getFaceDetectStatus).mockResolvedValue(progress);

    const { result } = renderHook(() => useFaceDetection(callbacks));

    // Advance one interval tick and flush the resulting promise
    await act(async () => {
      vi.advanceTimersByTime(500);
      // Flush the microtask queue so the resolved promise triggers setState
      await Promise.resolve();
    });

    expect(result.current.faceProgress).toEqual(progress);
  });
});
