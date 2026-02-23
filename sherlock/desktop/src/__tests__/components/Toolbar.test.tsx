import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Toolbar from "../../components/Content/Toolbar";

describe("Toolbar", () => {
  const mediaTypes = ["", "document", "photo", "anime"];

  it("renders search input with value", () => {
    render(
      <Toolbar query="cats" onQueryChange={() => {}} selectedMediaType="" onMediaTypeChange={() => {}} mediaTypeOptions={mediaTypes} />
    );
    expect(screen.getByLabelText("Search query")).toHaveValue("cats");
  });

  it("calls onQueryChange when typing", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <Toolbar query="" onQueryChange={onChange} selectedMediaType="" onMediaTypeChange={() => {}} mediaTypeOptions={mediaTypes} />
    );
    await user.type(screen.getByLabelText("Search query"), "a");
    expect(onChange).toHaveBeenCalledWith("a");
  });

  it("renders media type options", () => {
    render(
      <Toolbar query="" onQueryChange={() => {}} selectedMediaType="" onMediaTypeChange={() => {}} mediaTypeOptions={mediaTypes} />
    );
    expect(screen.getByText("all types")).toBeInTheDocument();
    expect(screen.getByText("document")).toBeInTheDocument();
    expect(screen.getByText("photo")).toBeInTheDocument();
  });

  it("calls onMediaTypeChange on select change", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <Toolbar query="" onQueryChange={() => {}} selectedMediaType="" onMediaTypeChange={onChange} mediaTypeOptions={mediaTypes} />
    );
    await user.selectOptions(screen.getByLabelText("Media type filter"), "photo");
    expect(onChange).toHaveBeenCalledWith("photo");
  });
});
