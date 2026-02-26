import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { invoke } from "@tauri-apps/api/core";
import FacesView from "../../components/Content/FacesView";
import type { PersonInfo, FaceInfo } from "../../types";

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

const mockFace1: FaceInfo = {
  id: 10,
  personId: 1,
  fileId: 100,
  relPath: "photos/face_a.jpg",
  filename: "face_a.jpg",
  confidence: 0.95,
  cropPath: "/cache/face_crops/10.jpg",
};

const mockFace2: FaceInfo = {
  id: 11,
  personId: 1,
  fileId: 101,
  relPath: "photos/face_b.jpg",
  filename: "face_b.jpg",
  confidence: 0.88,
  cropPath: "/cache/face_crops/11.jpg",
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

  it("shows person detail view when card is clicked", async () => {
    mockedInvoke.mockImplementation(async (cmd: string) => {
      if (cmd === "list_persons") return [mockPerson];
      if (cmd === "list_faces_for_person") return [mockFace1, mockFace2];
      return null;
    });

    render(<FacesView {...defaultProps} />);
    await waitFor(() => {
      expect(screen.getByText("Person 1")).toBeInTheDocument();
    });

    // Click the card — enters detail view (not onSelectPerson)
    await userEvent.click(screen.getByText("Person 1").closest(".faces-card")!);

    await waitFor(() => {
      expect(screen.getByText("Back to People")).toBeInTheDocument();
      expect(screen.getByText("View Photos")).toBeInTheDocument();
      expect(screen.getByText("face_a.jpg")).toBeInTheDocument();
      expect(screen.getByText("face_b.jpg")).toBeInTheDocument();
    });
    // onSelectPerson should NOT have been called
    expect(defaultProps.onSelectPerson).not.toHaveBeenCalled();
  });

  it("calls onSelectPerson via View Photos in detail view", async () => {
    mockedInvoke.mockImplementation(async (cmd: string) => {
      if (cmd === "list_persons") return [mockPerson];
      if (cmd === "list_faces_for_person") return [mockFace1];
      return null;
    });

    render(<FacesView {...defaultProps} />);
    await waitFor(() => {
      expect(screen.getByText("Person 1")).toBeInTheDocument();
    });

    // Enter detail view
    await userEvent.click(screen.getByText("Person 1").closest(".faces-card")!);
    await waitFor(() => {
      expect(screen.getByText("View Photos")).toBeInTheDocument();
    });

    // Click View Photos
    await userEvent.click(screen.getByText("View Photos"));
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

  it("calls unassign_face_from_person when Remove clicked", async () => {
    mockedInvoke.mockImplementation(async (cmd: string) => {
      if (cmd === "list_persons") return [mockPerson];
      if (cmd === "list_faces_for_person") return [mockFace1, mockFace2];
      if (cmd === "unassign_face_from_person") return null;
      return null;
    });

    render(<FacesView {...defaultProps} />);
    await waitFor(() => {
      expect(screen.getByText("Person 1")).toBeInTheDocument();
    });

    // Enter detail view
    await userEvent.click(screen.getByText("Person 1").closest(".faces-card")!);
    await waitFor(() => {
      expect(screen.getByText("face_a.jpg")).toBeInTheDocument();
    });

    // Click Remove on first face
    const removeButtons = screen.getAllByText("Remove");
    await userEvent.click(removeButtons[0]);

    await waitFor(() => {
      expect(mockedInvoke).toHaveBeenCalledWith("unassign_face_from_person", { faceId: 10 });
      expect(defaultProps.onNotice).toHaveBeenCalledWith("Face removed from person");
    });
  });

  it("returns to person grid when Back to People clicked", async () => {
    mockedInvoke.mockImplementation(async (cmd: string) => {
      if (cmd === "list_persons") return [mockPerson];
      if (cmd === "list_faces_for_person") return [mockFace1];
      return null;
    });

    render(<FacesView {...defaultProps} />);
    await waitFor(() => {
      expect(screen.getByText("Person 1")).toBeInTheDocument();
    });

    // Enter detail view
    await userEvent.click(screen.getByText("Person 1").closest(".faces-card")!);
    await waitFor(() => {
      expect(screen.getByText("Back to People")).toBeInTheDocument();
    });

    // Click Back to People
    await userEvent.click(screen.getByText("Back to People"));

    // Should be back on person grid
    await waitFor(() => {
      expect(screen.getByText("Person 1")).toBeInTheDocument();
      expect(screen.queryByText("Back to People")).not.toBeInTheDocument();
    });
  });

  it("removes person from grid when last face unassigned", async () => {
    const singleFacePerson: PersonInfo = { ...mockPerson, faceCount: 1 };
    let personList = [singleFacePerson];

    mockedInvoke.mockImplementation(async (cmd: string) => {
      if (cmd === "list_persons") return [...personList];
      if (cmd === "list_faces_for_person") return [mockFace1];
      if (cmd === "unassign_face_from_person") {
        // Simulate backend: person gets deleted after last face removed
        personList = [];
        return null;
      }
      return null;
    });

    render(<FacesView {...defaultProps} />);
    await waitFor(() => {
      expect(screen.getByText("Person 1")).toBeInTheDocument();
    });

    // Enter detail view
    await userEvent.click(screen.getByText("Person 1").closest(".faces-card")!);
    await waitFor(() => {
      expect(screen.getByText("face_a.jpg")).toBeInTheDocument();
    });

    // Remove the last face
    await userEvent.click(screen.getByText("Remove"));

    // Should return to person grid with empty state
    await waitFor(() => {
      expect(screen.getByText(/No faces clustered yet/)).toBeInTheDocument();
    });
  });
});
