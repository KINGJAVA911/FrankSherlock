import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StatusBar from "../../components/StatusBar/StatusBar";

describe("StatusBar", () => {
  it("shows VRAM info when available", () => {
    render(
      <StatusBar
        runtime={{ os: "linux", vramUsedMib: 2048, vramTotalMib: 8192, ollamaAvailable: true, loadedModels: [], currentModel: "qwen", gpuVendor: "nvidia", unifiedMemory: false, systemRamMib: 32768 }}
        isScanning={false}
        runningScansCount={0}
        selectedCount={0}
        faceProgress={null}
      />
    );
    expect(screen.getByText(/2048\/8192 MiB/)).toBeInTheDocument();
  });

  it("shows n/a when VRAM is not available", () => {
    render(
      <StatusBar
        runtime={{ os: "linux", vramUsedMib: null, vramTotalMib: null, ollamaAvailable: false, loadedModels: [], gpuVendor: "unknown", unifiedMemory: false, systemRamMib: 16384 }}
        isScanning={false}
        runningScansCount={0}
        selectedCount={0}
        faceProgress={null}
      />
    );
    expect(screen.getByText(/n\/a/)).toBeInTheDocument();
  });

  it("shows scanning count when scanning", () => {
    render(
      <StatusBar
        runtime={null}
        isScanning={true}
        runningScansCount={2}
        selectedCount={0}
        faceProgress={null}
      />
    );
    expect(screen.getByText(/2 active job/)).toBeInTheDocument();
  });

  it("shows selected count when items selected", () => {
    render(
      <StatusBar
        runtime={null}
        isScanning={false}
        runningScansCount={0}
        selectedCount={5}
        faceProgress={null}
      />
    );
    expect(screen.getByText("5 selected")).toBeInTheDocument();
  });

  it("shows model name on the left", () => {
    render(
      <StatusBar
        runtime={{ os: "linux", currentModel: "llama3", ollamaAvailable: true, loadedModels: ["llama3"], gpuVendor: "nvidia", unifiedMemory: false, systemRamMib: 32768 }}
        isScanning={false}
        runningScansCount={0}
        selectedCount={0}
        faceProgress={null}
      />
    );
    const modelSpan = screen.getByText(/llama3/);
    expect(modelSpan).toBeInTheDocument();
    // Model should be the first child of the statusbar
    const statusbar = modelSpan.closest(".statusbar");
    expect(statusbar?.firstElementChild).toBe(modelSpan);
  });

  it("calls onShowModelInfo when VRAM span is clicked", async () => {
    const user = userEvent.setup();
    const onShowModelInfo = vi.fn();
    render(
      <StatusBar
        runtime={{ os: "linux", vramUsedMib: 1024, vramTotalMib: 8192, ollamaAvailable: true, loadedModels: [], gpuVendor: "nvidia", unifiedMemory: false, systemRamMib: 32768 }}
        isScanning={false}
        runningScansCount={0}
        selectedCount={0}
        faceProgress={null}
        onShowModelInfo={onShowModelInfo}
      />
    );
    await user.click(screen.getByTitle("Click for model & hardware details"));
    expect(onShowModelInfo).toHaveBeenCalledOnce();
  });

  it("shows face detection progress when active", () => {
    render(
      <StatusBar
        runtime={null}
        isScanning={false}
        runningScansCount={0}
        selectedCount={0}
        faceProgress={{ rootId: 1, total: 200, processed: 75, facesFound: 12, phase: "detecting" }}
      />
    );
    expect(screen.getByText(/Faces: 75\/200/)).toBeInTheDocument();
    expect(screen.getByText(/12 found/)).toBeInTheDocument();
  });

  it("shows downloading phase for face models", () => {
    render(
      <StatusBar
        runtime={null}
        isScanning={false}
        runningScansCount={0}
        selectedCount={0}
        faceProgress={{ rootId: 1, total: 0, processed: 0, facesFound: 0, phase: "downloading" }}
      />
    );
    expect(screen.getByText("Downloading face models...")).toBeInTheDocument();
  });

  it("shows loading phase for face models", () => {
    render(
      <StatusBar
        runtime={null}
        isScanning={false}
        runningScansCount={0}
        selectedCount={0}
        faceProgress={{ rootId: 1, total: 0, processed: 0, facesFound: 0, phase: "loading" }}
      />
    );
    expect(screen.getByText("Loading face models...")).toBeInTheDocument();
  });

  it("hides face detection when progress is null", () => {
    render(
      <StatusBar
        runtime={null}
        isScanning={false}
        runningScansCount={0}
        selectedCount={0}
        faceProgress={null}
      />
    );
    expect(screen.queryByText(/Faces:/)).not.toBeInTheDocument();
  });
});
