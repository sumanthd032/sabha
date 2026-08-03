import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SystemPage } from "./SystemPage";

describe("SystemPage", () => {
  it("renders every token and component section", () => {
    render(<SystemPage />);
    for (const heading of [
      "Colour",
      "Type",
      "Spacing",
      "Rule",
      "Button",
      "Field",
      "Ledger row",
      "Empty state",
      "Error note",
    ]) {
      expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
    }
  });

  it("renders a disabled button state alongside the enabled ones", () => {
    render(<SystemPage />);
    const buttons = screen.getAllByRole("button");
    expect(buttons.some((button) => (button as HTMLButtonElement).disabled)).toBe(true);
    expect(buttons.some((button) => !(button as HTMLButtonElement).disabled)).toBe(true);
  });
});
