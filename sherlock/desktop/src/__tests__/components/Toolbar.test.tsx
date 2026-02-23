import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Toolbar from "../../components/Content/Toolbar";

const defaultSortProps = {
  sortBy: "dateModified" as const,
  onSortByChange: vi.fn(),
  sortOrder: "desc" as const,
  onSortOrderChange: vi.fn(),
  hasTextQuery: false,
};

describe("Toolbar", () => {
  const mediaTypes = ["", "document", "photo", "anime"];

  it("renders search input with value", () => {
    render(
      <Toolbar query="cats" onQueryChange={() => {}} selectedMediaType="" onMediaTypeChange={() => {}} mediaTypeOptions={mediaTypes} {...defaultSortProps} />
    );
    expect(screen.getByLabelText("Search query")).toHaveValue("cats");
  });

  it("calls onQueryChange when typing", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <Toolbar query="" onQueryChange={onChange} selectedMediaType="" onMediaTypeChange={() => {}} mediaTypeOptions={mediaTypes} {...defaultSortProps} />
    );
    await user.type(screen.getByLabelText("Search query"), "a");
    expect(onChange).toHaveBeenCalledWith("a");
  });

  it("renders media type options", () => {
    render(
      <Toolbar query="" onQueryChange={() => {}} selectedMediaType="" onMediaTypeChange={() => {}} mediaTypeOptions={mediaTypes} {...defaultSortProps} />
    );
    expect(screen.getByText("all types")).toBeInTheDocument();
    expect(screen.getByText("document")).toBeInTheDocument();
    expect(screen.getByText("photo")).toBeInTheDocument();
  });

  it("calls onMediaTypeChange on select change", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <Toolbar query="" onQueryChange={() => {}} selectedMediaType="" onMediaTypeChange={onChange} mediaTypeOptions={mediaTypes} {...defaultSortProps} />
    );
    await user.selectOptions(screen.getByLabelText("Media type filter"), "photo");
    expect(onChange).toHaveBeenCalledWith("photo");
  });

  it("renders sort toggle buttons", () => {
    render(
      <Toolbar query="" onQueryChange={() => {}} selectedMediaType="" onMediaTypeChange={() => {}} mediaTypeOptions={mediaTypes} {...defaultSortProps} />
    );
    expect(screen.getByRole("group", { name: "Sort field" })).toBeInTheDocument();
    expect(screen.getByLabelText("Date")).toBeInTheDocument();
    expect(screen.getByLabelText("Name")).toBeInTheDocument();
    expect(screen.getByLabelText("Type")).toBeInTheDocument();
    expect(screen.queryByLabelText("Relevance")).not.toBeInTheDocument();
  });

  it("marks active sort button with aria-pressed", () => {
    render(
      <Toolbar query="" onQueryChange={() => {}} selectedMediaType="" onMediaTypeChange={() => {}} mediaTypeOptions={mediaTypes} {...defaultSortProps} />
    );
    expect(screen.getByLabelText("Date")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText("Name")).toHaveAttribute("aria-pressed", "false");
  });

  it("shows Relevance toggle when hasTextQuery is true", () => {
    render(
      <Toolbar query="" onQueryChange={() => {}} selectedMediaType="" onMediaTypeChange={() => {}} mediaTypeOptions={mediaTypes} {...defaultSortProps} hasTextQuery={true} />
    );
    expect(screen.getByLabelText("Relevance")).toBeInTheDocument();
  });

  it("calls onSortByChange when clicking a sort toggle", async () => {
    const user = userEvent.setup();
    const onSortByChange = vi.fn();
    render(
      <Toolbar query="" onQueryChange={() => {}} selectedMediaType="" onMediaTypeChange={() => {}} mediaTypeOptions={mediaTypes} {...defaultSortProps} onSortByChange={onSortByChange} />
    );
    await user.click(screen.getByLabelText("Name"));
    expect(onSortByChange).toHaveBeenCalledWith("name");
  });

  it("renders sort direction button", () => {
    render(
      <Toolbar query="" onQueryChange={() => {}} selectedMediaType="" onMediaTypeChange={() => {}} mediaTypeOptions={mediaTypes} {...defaultSortProps} />
    );
    const dirBtn = screen.getByLabelText("Sort direction");
    expect(dirBtn).toBeInTheDocument();
    expect(dirBtn).toHaveTextContent("\u2193");
  });

  it("toggles sort direction on click", async () => {
    const user = userEvent.setup();
    const onSortOrderChange = vi.fn();
    render(
      <Toolbar query="" onQueryChange={() => {}} selectedMediaType="" onMediaTypeChange={() => {}} mediaTypeOptions={mediaTypes} {...defaultSortProps} onSortOrderChange={onSortOrderChange} />
    );
    await user.click(screen.getByLabelText("Sort direction"));
    expect(onSortOrderChange).toHaveBeenCalledWith("asc");
  });

  it("hides sort direction button when sortBy is relevance", () => {
    render(
      <Toolbar query="" onQueryChange={() => {}} selectedMediaType="" onMediaTypeChange={() => {}} mediaTypeOptions={mediaTypes} {...defaultSortProps} sortBy="relevance" hasTextQuery={true} />
    );
    expect(screen.queryByLabelText("Sort direction")).not.toBeInTheDocument();
  });
});
