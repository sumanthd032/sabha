import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useSessionStore } from "../../store/sessionStore";
import { ResultsScreen } from "./ResultsScreen";

const CONSULTATION = {
  id: 1,
  title: "Platform and gig work regulation",
  question: "How should responsibility be shared?",
  department: null,
  is_synthetic: true,
  opens_at: "2026-01-01T00:00:00Z",
  closes_at: "2026-02-01T00:00:00Z",
};

const OPINION_MAP = {
  model_run_id: 7,
  k_clusters: 2,
  points: [
    { participant_id: 1, factor: [0.4, -0.2] as [number, number], cluster: 0, is_self: false },
    { participant_id: 2, factor: [-0.3, 0.5] as [number, number], cluster: 1, is_self: false },
  ],
};

const RANKINGS = {
  model_run_id: 7,
  model_run_created_at: "2026-01-01T00:00:00Z",
  bridging: [
    { statement_id: 1, code: "S-0001", text: "Bridging statement", score: 0.9, rank: 1 },
  ],
  majority: [
    { statement_id: 2, code: "S-0002", text: "Majority statement", score: 0.6, rank: 1 },
  ],
};

const CERTIFICATE = {
  model_run_id: 7,
  statement: {
    id: 1,
    code: "S-0001",
    text: "Bridging statement",
    language: "en",
    author_type: "participant" as const,
    parent_statement_id: null,
    is_synthetic: true,
  },
  participant_count: 2,
  clusters: [
    { cluster: 0, participant_count: 1, agree_count: 1, agree_fraction: 1.0 },
    { cluster: 1, participant_count: 1, agree_count: 1, agree_fraction: 1.0 },
  ],
};

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  close = vi.fn();

  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

function renderScreen(): void {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ResultsScreen />
    </QueryClientProvider>,
  );
}

describe("ResultsScreen", () => {
  let hasModelRun: boolean;

  beforeEach(() => {
    hasModelRun = true;
    useSessionStore.setState({ sessions: {} });
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket);

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = typeof input === "string" ? input : input.toString();

        if (url === "/api/consultations") return jsonResponse([CONSULTATION]);
        if (url.startsWith("/api/consultations/1/opinion-map")) {
          return hasModelRun ? jsonResponse(OPINION_MAP) : new Response("not found", { status: 404 });
        }
        if (url === "/api/consultations/1/rankings") {
          return jsonResponse(
            hasModelRun ? RANKINGS : { model_run_id: null, model_run_created_at: null, bridging: [], majority: [] },
          );
        }
        if (url === "/api/consultations/1/certificate") {
          return hasModelRun ? jsonResponse(CERTIFICATE) : new Response("not found", { status: 404 });
        }
        throw new Error(`unhandled request: ${url}`);
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows the opinion map, legend, rankings, and certificate once data loads", async () => {
    renderScreen();

    expect(await screen.findByText("Bridging ranking")).toBeInTheDocument();
    expect(screen.getByText("Majority ranking")).toBeInTheDocument();
    expect(screen.getAllByText("Bridging statement").length).toBeGreaterThan(0);
    expect(screen.getByText("Consensus certificate")).toBeInTheDocument();
    expect(screen.getByText(/2 participants placed into 2 factions/)).toBeInTheDocument();
    expect(screen.getByText("Colours are assigned by cluster number and carry no political meaning.")).toBeInTheDocument();
  });

  it("shows an empty state when there is no model run yet", async () => {
    hasModelRun = false;
    renderScreen();

    expect(await screen.findByText("No results yet")).toBeInTheDocument();
  });

  it("opens a live websocket connection for the consultation", async () => {
    renderScreen();
    await screen.findByText("Bridging ranking");

    await waitFor(() => expect(FakeWebSocket.instances.length).toBe(1));
    expect(FakeWebSocket.instances[0]?.url).toContain("/api/consultations/1/live");
  });
});
