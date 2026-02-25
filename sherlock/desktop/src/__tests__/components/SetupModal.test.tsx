import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SetupModal from "../../components/modals/SetupModal";
import type { SetupStatus } from "../../types";

const mockSetup: SetupStatus = {
  isReady: false,
  ollamaAvailable: true,
  requiredModels: ["qwen2.5vl:7b"],
  missingModels: ["qwen2.5vl:7b"],
  instructions: ["Install Ollama", "Pull the model"],
  download: { status: "idle", progressPct: 0, message: "Ready to download" },
  pythonAvailable: false,
  pythonVersion: null,
  suryaVenvOk: false,
  recommendedModel: "qwen2.5vl:7b",
  modelTier: "medium",
  modelSelectionReason: "NVIDIA GPU (24 GiB VRAM) — 7b is optimal",
  systemPythonFound: false,
  venvProvision: { status: "idle", step: "", progressPct: 0, message: "No OCR setup in progress" },
  ffmpegAvailable: true,
};

describe("SetupModal", () => {
  it("renders setup heading and instructions", () => {
    render(<SetupModal setup={mockSetup} onRecheck={() => {}} onDownload={() => {}} onSetupOcr={() => {}} />);
    expect(screen.getByText("First-Time Setup")).toBeInTheDocument();
    expect(screen.getByText("Install Ollama")).toBeInTheDocument();
    expect(screen.getByText("Pull the model")).toBeInTheDocument();
  });

  it("shows Ollama status", () => {
    render(<SetupModal setup={mockSetup} onRecheck={() => {}} onDownload={() => {}} onSetupOcr={() => {}} />);
    expect(screen.getByText("Running")).toBeInTheDocument();
  });

  it("calls onRecheck when Recheck clicked", async () => {
    const user = userEvent.setup();
    const onRecheck = vi.fn();
    render(<SetupModal setup={mockSetup} onRecheck={onRecheck} onDownload={() => {}} onSetupOcr={() => {}} />);
    await user.click(screen.getByText("Recheck"));
    expect(onRecheck).toHaveBeenCalledOnce();
  });

  it("calls onDownload when Download clicked", async () => {
    const user = userEvent.setup();
    const onDownload = vi.fn();
    render(<SetupModal setup={mockSetup} onRecheck={() => {}} onDownload={onDownload} onSetupOcr={() => {}} />);
    await user.click(screen.getByText("Download model"));
    expect(onDownload).toHaveBeenCalledOnce();
  });

  it("shows model tier and recommended model", () => {
    render(<SetupModal setup={mockSetup} onRecheck={() => {}} onDownload={() => {}} onSetupOcr={() => {}} />);
    expect(screen.getByText(/Model \(medium\)/)).toBeInTheDocument();
    const modelTexts = screen.getAllByText("qwen2.5vl:7b");
    expect(modelTexts.length).toBeGreaterThanOrEqual(1);
    // The model name with the title attribute is the recommended model display
    const recommended = modelTexts.find((el) => el.getAttribute("title"));
    expect(recommended).toBeTruthy();
  });

  it("disables download button when running", () => {
    const running = {
      ...mockSetup,
      download: { ...mockSetup.download, status: "running" as const, progressPct: 50 },
    };
    render(<SetupModal setup={running} onRecheck={() => {}} onDownload={() => {}} onSetupOcr={() => {}} />);
    expect(screen.getByText("Downloading...")).toBeDisabled();
  });

  it("does not show Setup OCR button when system python not found", () => {
    render(<SetupModal setup={mockSetup} onRecheck={() => {}} onDownload={() => {}} onSetupOcr={() => {}} />);
    expect(screen.queryByText("Setup OCR")).not.toBeInTheDocument();
  });

  it("shows Setup OCR button when system python found and venv not ok", async () => {
    const user = userEvent.setup();
    const onSetupOcr = vi.fn();
    const withPython = { ...mockSetup, systemPythonFound: true };
    render(<SetupModal setup={withPython} onRecheck={() => {}} onDownload={() => {}} onSetupOcr={onSetupOcr} />);
    const btn = screen.getByText("Setup OCR");
    expect(btn).toBeInTheDocument();
    await user.click(btn);
    expect(onSetupOcr).toHaveBeenCalledOnce();
  });

  it("shows disabled button when venv provision is running", () => {
    const running = {
      ...mockSetup,
      systemPythonFound: true,
      venvProvision: { status: "running" as const, step: "installing_surya", progressPct: 45, message: "Installing..." },
    };
    render(<SetupModal setup={running} onRecheck={() => {}} onDownload={() => {}} onSetupOcr={() => {}} />);
    expect(screen.queryByText("Setup OCR")).not.toBeInTheDocument();
    expect(screen.getByText("Setting up OCR...")).toBeDisabled();
  });

  it("shows venv provision progress when not idle", () => {
    const provisioning = {
      ...mockSetup,
      systemPythonFound: true,
      venvProvision: { status: "running" as const, step: "installing_surya", progressPct: 50, message: "Installing surya-ocr..." },
    };
    render(<SetupModal setup={provisioning} onRecheck={() => {}} onDownload={() => {}} onSetupOcr={() => {}} />);
    expect(screen.getByText("Installing surya-ocr...")).toBeInTheDocument();
    expect(screen.getByText("50.0%")).toBeInTheDocument();
  });
});
