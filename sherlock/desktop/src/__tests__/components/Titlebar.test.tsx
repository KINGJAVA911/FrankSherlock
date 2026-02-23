import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Titlebar from "../../components/Titlebar/Titlebar";

describe("Titlebar", () => {
  it("renders the app title", () => {
    render(<Titlebar onClose={() => {}} />);
    expect(screen.getByText("Frank Sherlock")).toBeInTheDocument();
  });

  it("renders minimize, maximize, close buttons", () => {
    render(<Titlebar onClose={() => {}} />);
    expect(screen.getByLabelText("Minimize")).toBeInTheDocument();
    expect(screen.getByLabelText("Maximize")).toBeInTheDocument();
    expect(screen.getByLabelText("Close")).toBeInTheDocument();
  });

  it("calls onClose when close button is clicked", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<Titlebar onClose={onClose} />);
    await user.click(screen.getByLabelText("Close"));
    expect(onClose).toHaveBeenCalledOnce();
  });
});
