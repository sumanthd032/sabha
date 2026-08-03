import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Button } from "./Button";

describe("Button", () => {
  it("renders as a real button with an accessible name", () => {
    render(<Button>File the clause set</Button>);
    expect(screen.getByRole("button", { name: "File the clause set" })).toBeInTheDocument();
  });

  it("is truly disabled, not just styled to look disabled", () => {
    render(<Button disabled>File the clause set</Button>);
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("defaults to type button so it never submits a form by accident", () => {
    render(<Button>Review before filing</Button>);
    expect(screen.getByRole("button")).toHaveAttribute("type", "button");
  });
});
