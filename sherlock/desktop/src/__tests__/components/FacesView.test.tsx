import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { invoke } from "@tauri-apps/api/core";
import FacesView from "../../components/Content/FacesView";
import type { PersonInfo } from "../../types";

const mockedInvoke = vi.mocked(invoke);

const mockPerson: PersonInfo = {
  id: 1,
  name: "Person 1",
  faceCount: 5,
  cropPath: "/cache/face_crops/1.jpg",
  thumbnailPath: "/cache/thumbs/img.jpg",
};

const mockPerson2: PersonInfo = {
  id: 2,
  name: "Alice",
  faceCount: 3,
  cropPath: null,
  thumbnailPath: "/cache/thumbs/img2.jpg",
};

const defaultProps = {
  onBack: vi.fn(),
  onSelectPerson: vi.fn(),
  onNotice: vi.fn(),
  onError: vi.fn(),
};

describe("FacesView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedInvoke.mockImplementation(async (cmd: string) => {
      if (cmd === "list_persons") return [];
      return null;
    });
  });

  it("renders empty state", async () => {
    render(<FacesView {...defaultProps} />);
    await waitFor(() => {
      expect(screen.getByText(/No faces clustered yet/)).toBeInTheDocument();
    });
  });

  it("renders person cards", async () => {
    mockedInvoke.mockImplementation(async (cmd: string) => {
      if (cmd === "list_persons") return [mockPerson, mockPerson2];
      return null;
    });

    render(<FacesView {...defaultProps} />);
    await waitFor(() => {
      expect(screen.getByText("Person 1")).toBeInTheDocument();
      expect(screen.getByText("Alice")).toBeInTheDocument();
    });
  });

  it("shows stats in toolbar", async () => {
    mockedInvoke.mockImplementation(async (cmd: string) => {
      if (cmd === "list_persons") return [mockPerson, mockPerson2];
      return null;
    });

    render(<FacesView {...defaultProps} />);
    await waitFor(() => {
      expect(screen.getByText("2")).toBeInTheDocument(); // 2 people
      expect(screen.getByText("8")).toBeInTheDocument(); // 8 faces total
    });
  });

  it("calls onSelectPerson when card is clicked", async () => {
    mockedInvoke.mockImplementation(async (cmd: string) => {
      if (cmd === "list_persons") return [mockPerson];
      return null;
    });

    render(<FacesView {...defaultProps} />);
    await waitFor(() => {
      expect(screen.getByText("Person 1")).toBeInTheDocument();
    });

    // Click the card (which has the person name)
    await userEvent.click(screen.getByText("Person 1").closest(".faces-card")!);
    expect(defaultProps.onSelectPerson).toHaveBeenCalledWith(1, "Person 1");
  });

  it("calls onBack when back button is clicked", async () => {
    render(<FacesView {...defaultProps} />);
    await waitFor(() => {
      expect(screen.getByText("Back")).toBeInTheDocument();
    });
    await userEvent.click(screen.getByText("Back"));
    expect(defaultProps.onBack).toHaveBeenCalled();
  });

  it("inline rename triggers renamePerson", async () => {
    mockedInvoke.mockImplementation(async (cmd: string) => {
      if (cmd === "list_persons") return [mockPerson];
      if (cmd === "rename_person") return null;
      return null;
    });

    render(<FacesView {...defaultProps} />);
    await waitFor(() => {
      expect(screen.getByText("Person 1")).toBeInTheDocument();
    });

    // Click the name label to start editing
    await userEvent.click(screen.getByText("Person 1"));

    // Type a new name
    const input = screen.getByDisplayValue("Person 1");
    await userEvent.clear(input);
    await userEvent.type(input, "Bob{Enter}");

    await waitFor(() => {
      expect(mockedInvoke).toHaveBeenCalledWith("rename_person", { personId: 1, newName: "Bob" });
      expect(defaultProps.onNotice).toHaveBeenCalledWith('Renamed to "Bob"');
    });
  });

  it("displays face count badges", async () => {
    mockedInvoke.mockImplementation(async (cmd: string) => {
      if (cmd === "list_persons") return [mockPerson];
      return null;
    });

    render(<FacesView {...defaultProps} />);
    await waitFor(() => {
      expect(screen.getByText("5")).toBeInTheDocument(); // badge count
    });
  });
});
