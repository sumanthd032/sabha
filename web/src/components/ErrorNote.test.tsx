import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ErrorNote } from "./ErrorNote";

describe("ErrorNote", () => {
  it("announces itself as an alert", () => {
    render(
      <ErrorNote
        heading="Your vote did not reach the server"
        body="It is saved on this device and will send automatically once the connection returns."
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Your vote did not reach the server");
  });
});
