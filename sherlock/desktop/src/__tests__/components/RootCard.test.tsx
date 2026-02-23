import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import RootCard from "../../components/Sidebar/RootCard";
import type { RootInfo } from "../../types";

const sampleRoot: RootInfo = {
  id: 1,
  rootPath: "/home/user/photos",
  rootName: "photos",
  createdAt: 0,
  lastScanAt: null,
  fileCount: 42,
};

describe("RootCard", () => {
  it("renders root name and file count", () => {
    render(
      <RootCard root={sampleRoot} isSelected={false} scan={undefined} readOnly={false} onSelect={vi.fn()} onDelete={vi.fn()} />
    );
    expect(screen.getByText("photos")).toBeInTheDocument();
    expect(screen.getByText("42 files")).toBeInTheDocument();
  });

  it("applies selected class when selected", () => {
    const { container } = render(
      <RootCard root={sampleRoot} isSelected scan={undefined} readOnly={false} onSelect={vi.fn()} onDelete={vi.fn()} />
    );
    expect(container.querySelector(".root-card.selected")).not.toBeNull();
  });

  it("calls onSelect when clicked", async () => {
    const onSelect = vi.fn();
    render(
      <RootCard root={sampleRoot} isSelected={false} scan={undefined} readOnly={false} onSelect={onSelect} onDelete={vi.fn()} />
    );
    await userEvent.click(screen.getByText("photos"));
    expect(onSelect).toHaveBeenCalled();
  });

  it("calls onDelete when delete button clicked", async () => {
    const onDelete = vi.fn();
    render(
      <RootCard root={sampleRoot} isSelected={false} scan={undefined} readOnly={false} onSelect={vi.fn()} onDelete={onDelete} />
    );
    await userEvent.click(screen.getByLabelText("Remove photos"));
    expect(onDelete).toHaveBeenCalled();
  });

  it("hides delete button in readOnly mode", () => {
    render(
      <RootCard root={sampleRoot} isSelected={false} scan={undefined} readOnly onSelect={vi.fn()} onDelete={vi.fn()} />
    );
    expect(screen.queryByLabelText("Remove photos")).not.toBeInTheDocument();
  });

  it("shows scan progress when scan is active", () => {
    const scan = {
      id: 10, rootId: 1, rootPath: "/home/user/photos", status: "running" as const,
      scanMarker: 0, totalFiles: 100, processedFiles: 50, progressPct: 50,
      added: 10, modified: 5, moved: 2, unchanged: 33, deleted: 0,
      startedAt: 0, updatedAt: 0,
    };
    render(
      <RootCard root={sampleRoot} isSelected={false} scan={scan} readOnly={false} onSelect={vi.fn()} onDelete={vi.fn()} />
    );
    expect(screen.getByText("50/100")).toBeInTheDocument();
  });
});
