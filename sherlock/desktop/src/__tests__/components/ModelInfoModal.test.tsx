import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ModelInfoModal from "../../components/modals/ModelInfoModal";
import type { RuntimeStatus, SetupStatus } from "../../types";

const mockRuntime: RuntimeStatus = {
  os: "linux",
  currentModel: "qwen2.5vl:7b",
  loadedModels: ["qwen2.5vl:7b"],
  vramUsedMib: 4096,
  vramTotalMib: 24576,
  gpuVendor: "nvidia",
  unifiedMemory: false,
  systemRamMib: 32768,
  ollamaAvailable: true,
};

const mockSetup: SetupStatus = {
  isReady: true,
  ollamaAvailable: true,
  requiredModels: ["qwen2.5vl:7b"],
  missingModels: [],
  instructions: ["Setup complete."],
  download: { status: "idle", progressPct: 0, message: "No download in progress" },
  pythonAvailable: true,
  pythonVersion: "3.11",
  suryaVenvOk: true,
  recommendedModel: "qwen2.5vl:7b",
  modelTier: "medium",
  modelSelectionReason: "NVIDIA GPU (24 GiB VRAM) — 7b is optimal",
};

describe("ModelInfoModal", () => {
  it("renders hardware info", () => {
    render(<ModelInfoModal runtime={mockRuntime} setup={mockSetup} onClose={() => {}} />);
    expect(screen.getByText("NVIDIA")).toBeInTheDocument();
    expect(screen.getByText(/4096.*24576 MiB/)).toBeInTheDocument();
    expect(screen.getByText("Discrete")).toBeInTheDocument();
  });

  it("renders model selection info", () => {
    render(<ModelInfoModal runtime={mockRuntime} setup={mockSetup} onClose={() => {}} />);
    expect(screen.getByText("medium")).toBeInTheDocument();
    expect(screen.getByText(/7b is optimal/)).toBeInTheDocument();
  });

  it("renders loaded models with active badge", () => {
    render(<ModelInfoModal runtime={mockRuntime} setup={mockSetup} onClose={() => {}} />);
    expect(screen.getByText("active")).toBeInTheDocument();
  });

  it("shows no models message when none loaded", () => {
    const noModels = { ...mockRuntime, loadedModels: [], currentModel: null };
    render(<ModelInfoModal runtime={noModels} setup={mockSetup} onClose={() => {}} />);
    expect(screen.getByText("No models currently loaded")).toBeInTheDocument();
  });

  it("shows missing models when present", () => {
    const setupMissing = { ...mockSetup, missingModels: ["qwen2.5vl:7b"] };
    render(<ModelInfoModal runtime={mockRuntime} setup={setupMissing} onClose={() => {}} />);
    expect(screen.getByText("Missing models")).toBeInTheDocument();
  });

  it("shows unified memory type for Apple", () => {
    const appleRuntime = {
      ...mockRuntime,
      gpuVendor: "apple",
      unifiedMemory: true,
      vramUsedMib: null,
      vramTotalMib: null,
      systemRamMib: 65536,
    };
    render(<ModelInfoModal runtime={appleRuntime} setup={mockSetup} onClose={() => {}} />);
    expect(screen.getByText("Apple Silicon")).toBeInTheDocument();
    expect(screen.getByText("Unified")).toBeInTheDocument();
  });

  it("calls onClose when Close button clicked", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<ModelInfoModal runtime={mockRuntime} setup={mockSetup} onClose={onClose} />);
    await user.click(screen.getByText("Close"));
    expect(onClose).toHaveBeenCalledOnce();
  });
});
