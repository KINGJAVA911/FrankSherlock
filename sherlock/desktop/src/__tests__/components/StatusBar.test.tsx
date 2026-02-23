import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import StatusBar from "../../components/StatusBar/StatusBar";

describe("StatusBar", () => {
  it("shows VRAM info when available", () => {
    render(
      <StatusBar
        runtime={{ vramUsedMib: 2048, vramTotalMib: 8192, ollamaAvailable: true, loadedModels: [], currentModel: "qwen" }}
        dbStats={{ files: 100, roots: 2 }}
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
        runtime={{ vramUsedMib: null, vramTotalMib: null, ollamaAvailable: false, loadedModels: [] }}
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
        runtime={{ currentModel: "llama3", ollamaAvailable: true, loadedModels: ["llama3"] }}
        dbStats={null}
        isScanning={false}
        runningScansCount={0}
        selectedCount={0}
      />
    );
    expect(screen.getByText(/llama3/)).toBeInTheDocument();
  });
});
