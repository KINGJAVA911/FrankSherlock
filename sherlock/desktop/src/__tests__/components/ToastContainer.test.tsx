import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import ToastContainer from "../../components/Toasts/ToastContainer";

describe("ToastContainer", () => {
  it("renders nothing when both are null", () => {
    const { container } = render(<ToastContainer notice={null} error={null} />);
    expect(container.querySelector(".toast")).toBeNull();
  });

  it("renders notice toast", () => {
    render(<ToastContainer notice="File copied" error={null} />);
    expect(screen.getByText("File copied")).toBeInTheDocument();
    expect(screen.getByText("File copied").closest(".toast")).toHaveClass("notice");
  });

  it("renders error toast", () => {
    render(<ToastContainer notice={null} error="Something failed" />);
    expect(screen.getByText("Something failed")).toBeInTheDocument();
    expect(screen.getByText("Something failed").closest(".toast")).toHaveClass("error");
  });

  it("renders both toasts simultaneously", () => {
    render(<ToastContainer notice="OK" error="Bad" />);
    expect(screen.getByText("OK")).toBeInTheDocument();
    expect(screen.getByText("Bad")).toBeInTheDocument();
  });
});
