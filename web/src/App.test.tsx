import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import App from "./App";
import { useRouterStore } from "./lib/router";

afterEach(() => {
  useRouterStore.setState({ path: "/" });
});

describe("App", () => {
  it("renders without crashing", () => {
    const { container } = render(<App />);
    expect(container).toBeTruthy();
  });

  it("renders the system reference page at /system", () => {
    useRouterStore.getState().navigate("/system");
    render(<App />);
    expect(screen.getByRole("heading", { name: "System reference" })).toBeInTheDocument();
  });
});
