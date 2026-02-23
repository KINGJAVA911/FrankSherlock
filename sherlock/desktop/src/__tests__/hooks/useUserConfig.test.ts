import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useUserConfig } from "../../hooks/useUserConfig";
import { loadUserConfig } from "../../api";

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return {
    ...actual,
    loadUserConfig: vi.fn(),
    saveUserConfig: vi.fn(),
  };
});

describe("useUserConfig", () => {
  beforeEach(() => {
    vi.mocked(loadUserConfig).mockResolvedValue({ zoom: 1.5 });
  });

  it("defaults zoom to 1.25", () => {
    vi.mocked(loadUserConfig).mockResolvedValue({});
    const { result } = renderHook(() => useUserConfig());
    expect(result.current.zoom).toBe(1.25);
  });

  it("loads saved zoom from config", async () => {
    const { result } = renderHook(() => useUserConfig());
    await waitFor(() => expect(result.current.zoom).toBe(1.5));
  });

  it("clamps zoom to valid range", async () => {
    vi.mocked(loadUserConfig).mockResolvedValue({ zoom: 10.0 });
    const { result } = renderHook(() => useUserConfig());
    await waitFor(() => expect(result.current.zoom).toBe(3.0));
  });

  it("applies zoom to document font-size", async () => {
    const { result } = renderHook(() => useUserConfig());
    await waitFor(() => expect(result.current.zoom).toBe(1.5));
    expect(document.documentElement.style.fontSize).toBe("21px");
  });
});
