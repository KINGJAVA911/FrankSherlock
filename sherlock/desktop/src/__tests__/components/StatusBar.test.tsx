import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StatusBar from "../../components/StatusBar/StatusBar";

describe("StatusBar", () => {
  it("shows VRAM info when available", () => {
    render(
      <StatusBar
        runtime={{ vramUsedMib: 2048, vramTotalMib: 8192, ollamaAvailable: true, loadedModels: [], currentModel: "qwen", gpuVendor: "nvidia", unifiedMemory: false, systemRamMib: 32768 }}
        dbStats={{ files: 100, roots: 2, dbSizeBytes: 0, thumbsSizeBytes: 0 }}
        isScanning={false}
        runningScansCount={0}
        selectedCount={0}
      />
    );
    expect(screen.getByText(/2048\/8192 MiB/)).toBeInTheDocument();
  });

  it("shows n/a when VRAM is not available", () => {
    render(
      <StatusBar
        runtime={{ vramUsedMib: null, vramTotalMib: null, ollamaAvailable: false, loadedModels: [], gpuVendor: "unknown", unifiedMemory: false, systemRamMib: 16384 }}
        dbStats={null}
        isScanning={false}
        runningScansCount={0}
        selectedCount={0}
      />
    );
    expect(screen.getByText(/n\/a/)).toBeInTheDocument();
  });

  it("shows scanning count when scanning", () => {
    render(
      <StatusBar
        runtime={null}
        dbStats={null}
        isScanning={true}
        runningScansCount={2}
        selectedCount={0}
      />
    );
    expect(screen.getByText(/2 active job/)).toBeInTheDocument();
  });

  it("shows selected count when items selected", () => {
    render(
      <StatusBar
        runtime={null}
        dbStats={null}
        isScanning={false}
        runningScansCount={0}
        selectedCount={5}
      />
    );
    expect(screen.getByText("5 selected")).toBeInTheDocument();
  });

  it("shows model name", () => {
    render(
      <StatusBar
        runtime={{ currentModel: "llama3", ollamaAvailable: true, loadedModels: ["llama3"], gpuVendor: "nvidia", unifiedMemory: false, systemRamMib: 32768 }}
        dbStats={null}
        isScanning={false}
        runningScansCount={0}
        selectedCount={0}
      />
    );
    expect(screen.getByText(/llama3/)).toBeInTheDocument();
  });

  it("calls onShowModelInfo when VRAM span is clicked", async () => {
    const user = userEvent.setup();
    const onShowModelInfo = vi.fn();
    render(
      <StatusBar
        runtime={{ vramUsedMib: 1024, vramTotalMib: 8192, ollamaAvailable: true, loadedModels: [], gpuVendor: "nvidia", unifiedMemory: false, systemRamMib: 32768 }}
        dbStats={null}
        isScanning={false}
        runningScansCount={0}
        selectedCount={0}
        onShowModelInfo={onShowModelInfo}
      />
    );
    await user.click(screen.getByTitle("Click for model & hardware details"));
    expect(onShowModelInfo).toHaveBeenCalledOnce();
  });
});
