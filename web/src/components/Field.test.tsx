import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Field } from "./Field";

describe("Field", () => {
  it("associates the label with the input", () => {
    render(<Field label="Consultation title" value="" onChange={() => {}} />);
    expect(screen.getByLabelText("Consultation title")).toBeInTheDocument();
  });

  it("links an error message to the input for assistive technology", () => {
    render(
      <Field
        label="Ministry email"
        value="not-an-address"
        onChange={() => {}}
        error="Enter a complete email address"
      />,
    );
    const input = screen.getByLabelText("Ministry email");
    expect(input).toHaveAttribute("aria-invalid", "true");
    const describedBy = input.getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();
    expect(screen.getByText("Enter a complete email address")).toHaveAttribute("id", describedBy);
  });

  it("is truly disabled when asked to be", () => {
    render(<Field label="Statutory deadline" value="" onChange={() => {}} disabled />);
    expect(screen.getByLabelText("Statutory deadline")).toBeDisabled();
  });
});
