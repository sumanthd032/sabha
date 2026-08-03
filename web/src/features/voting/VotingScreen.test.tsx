import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useSessionStore } from "../../store/sessionStore";
import { useVoteQueueStore } from "../../store/voteQueueStore";
import { VotingScreen } from "./VotingScreen";

const CONSULTATION = {
  id: 1,
  title: "Platform and gig work regulation",
  question: "How should responsibility be shared?",
  department: null,
  is_synthetic: true,
  opens_at: "2026-01-01T00:00:00Z",
  closes_at: "2026-02-01T00:00:00Z",
};

interface FakeStatement {
  id: number;
  code: string;
  text: string;
  language: string;
  author_type: "participant";
  parent_statement_id: null;
  is_synthetic: boolean;
}

function makeStatements(count: number): FakeStatement[] {
  return Array.from({ length: count }, (_, i) => ({
    id: i + 1,
    code: `S-${String(i + 1).padStart(4, "0")}`,
    text: `Statement number ${i + 1}`,
    language: "en",
    author_type: "participant",
    parent_statement_id: null,
    is_synthetic: true,
  }));
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
      <VotingScreen />
    </QueryClientProvider>,
  );
}

describe("VotingScreen", () => {
  let statements: FakeStatement[];
  let votedIds: Set<number>;

  beforeEach(() => {
    statements = makeStatements(5);
    votedIds = new Set();
    window.localStorage.clear();
    useVoteQueueStore.setState({ entries: [], answeredIds: new Set(), entryCount: 0 });
    useSessionStore.setState({ sessions: {} });

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === "string" ? input : input.toString();
        const method = init?.method ?? "GET";

        if (url === "/api/consultations") {
          return jsonResponse([CONSULTATION]);
        }
        if (url === "/api/consultations/1/statements") {
          return jsonResponse(statements);
        }
        if (url === "/api/consultations/1/join" && method === "POST") {
          return jsonResponse({ participant_id: 1, session_token: "test-token" });
        }
        if (url.startsWith("/api/consultations/1/statements/next")) {
          const next = statements.find((s) => !votedIds.has(s.id));
          return jsonResponse(next ?? null);
        }
        if (url === "/api/consultations/1/votes" && method === "POST") {
          const body: { statement_id: number; value: number } = JSON.parse(init?.body as string);
          votedIds.add(body.statement_id);
          return jsonResponse({
            id: 1,
            statement_id: body.statement_id,
            value: body.value,
            created_at: "2026-01-01T00:00:00Z",
          });
        }
        throw new Error(`unhandled request: ${method} ${url}`);
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows the first statement once data loads", async () => {
    renderScreen();
    expect(await screen.findByText("Statement number 1")).toBeInTheDocument();
    expect(screen.getByText("S-0001")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
  });

  it("casts an agree vote by clicking and advances to the next statement", async () => {
    renderScreen();
    await screen.findByText("Statement number 1");

    fireEvent.click(screen.getByRole("button", { name: "Agree A" }));

    await waitFor(() => expect(screen.getByText("Statement number 2")).toBeInTheDocument());
    expect(votedIds.has(1)).toBe(true);
  });

  it("casts a disagree vote with the d key", async () => {
    renderScreen();
    await screen.findByText("Statement number 1");

    fireEvent.keyDown(window, { key: "d" });

    await waitFor(() => expect(screen.getByText("Statement number 2")).toBeInTheDocument());
    expect(votedIds.has(1)).toBe(true);
  });

  it("skips without casting a vote", async () => {
    renderScreen();
    await screen.findByText("Statement number 1");

    fireEvent.keyDown(window, { key: "s" });

    await waitFor(() => expect(screen.queryByText("Statement number 1")).not.toBeInTheDocument());
    expect(votedIds.size).toBe(0);
  });

  it("shows the empty state when there are no statements", async () => {
    statements = [];
    renderScreen();
    expect(await screen.findByText(/no statements are open/i)).toBeInTheDocument();
  });

  it("shows the completed state once the server has nothing left to serve", async () => {
    statements = makeStatements(1);
    votedIds.add(1);
    renderScreen();
    expect(await screen.findByText(/voted on every statement/i)).toBeInTheDocument();
  });
});
