import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import EditMetadataModal from "../../components/modals/EditMetadataModal";

vi.mock("../../api", () => ({
  getFileMetadata: vi.fn(),
}));

import { getFileMetadata } from "../../api";

const mockMetadata = {
  id: 42,
  mediaType: "photo",
  description: "A sunset photo",
  extractedText: "some text",
  canonicalMentions: "Alice, Bob",
  locationText: "New York, NY, US",
};

describe("EditMetadataModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (getFileMetadata as ReturnType<typeof vi.fn>).mockResolvedValue(mockMetadata);
  });

  it("shows loading state initially", () => {
    render(
      <EditMetadataModal fileId={42} onSave={vi.fn()} onCancel={vi.fn()} />
    );
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("renders form fields after loading", async () => {
    render(
      <EditMetadataModal fileId={42} onSave={vi.fn()} onCancel={vi.fn()} />
    );
    await waitFor(() => {
      expect(screen.queryByText("Loading...")).toBeNull();
    });
    expect(screen.getByText("Type")).toBeInTheDocument();
    expect(screen.getByText("Description")).toBeInTheDocument();
    expect(screen.getByText("Extracted text")).toBeInTheDocument();
    expect(screen.getByText("Mentions")).toBeInTheDocument();
    expect(screen.getByText("Location")).toBeInTheDocument();
  });

  it("populates fields with loaded metadata", async () => {
    render(
      <EditMetadataModal fileId={42} onSave={vi.fn()} onCancel={vi.fn()} />
    );
    await waitFor(() => {
      expect(screen.queryByText("Loading...")).toBeNull();
    });
    expect(screen.getByDisplayValue("A sunset photo")).toBeInTheDocument();
    expect(screen.getByDisplayValue("some text")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Alice, Bob")).toBeInTheDocument();
    expect(screen.getByDisplayValue("New York, NY, US")).toBeInTheDocument();
  });

  it("calls onSave with updated metadata", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    render(
      <EditMetadataModal fileId={42} onSave={onSave} onCancel={vi.fn()} />
    );
    await waitFor(() => {
      expect(screen.queryByText("Loading...")).toBeNull();
    });
    await user.click(screen.getByText("Save"));
    expect(onSave).toHaveBeenCalledOnce();
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      id: 42,
      mediaType: "photo",
      description: "A sunset photo",
    }));
  });

  it("calls onCancel when Cancel clicked", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    render(
      <EditMetadataModal fileId={42} onSave={vi.fn()} onCancel={onCancel} />
    );
    await waitFor(() => {
      expect(screen.queryByText("Loading...")).toBeNull();
    });
    await user.click(screen.getByText("Cancel"));
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it("shows error when loading fails", async () => {
    (getFileMetadata as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("Not found")
    );
    render(
      <EditMetadataModal fileId={999} onSave={vi.fn()} onCancel={vi.fn()} />
    );
    await waitFor(() => {
      expect(screen.getByText("Not found")).toBeInTheDocument();
    });
  });
});
