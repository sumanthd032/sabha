import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { EmptyState } from "../../components/EmptyState";
import { ErrorNote } from "../../components/ErrorNote";
import {
  ApiError,
  castVote as postVote,
  fetchNextStatement,
  joinConsultation,
  listConsultations,
  listStatements,
  type Statement,
} from "../../lib/api";
import { useSessionStore } from "../../store/sessionStore";
import { pendingCount, useVoteQueueStore } from "../../store/voteQueueStore";
import { StatementPanel } from "./StatementPanel";
import { StatementPanelSkeleton } from "./StatementPanelSkeleton";
import "./voting.css";

const RETRY_INTERVAL_MS = 4000;
const NEXT_STATEMENT_TIMEOUT_MS = 1200;

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T | "timeout"> {
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve("timeout"), ms);
    promise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      () => {
        clearTimeout(timer);
        resolve("timeout");
      },
    );
  });
}

function pickLocalNext(pool: Statement[], excludeIds: Set<number>): Statement | null {
  const eligible = pool.filter((statement) => !excludeIds.has(statement.id));
  if (eligible.length === 0) return null;
  const picked = eligible[Math.floor(Math.random() * eligible.length)];
  return picked ?? null;
}

/**
 * The primary screen. One statement at a time, three actions, keyboard
 * operable throughout. A vote is recorded in local state the instant it
 * is cast and reconciled with the server afterwards, and the choice of
 * what to show next never waits long on the network: adaptive selection
 * is used when it answers quickly, and a local random pick from the
 * full pool covers a skip or a slow connection, so reading and voting
 * never stalls on a round trip. A session that fails to establish does
 * not block the screen either, since a skip needs no session at all;
 * agree and disagree simply stay queued until it does.
 */
export function VotingScreen() {
  const consultationsQuery = useQuery({ queryKey: ["consultations"], queryFn: listConsultations });
  const consultation = consultationsQuery.data?.[0] ?? null;

  const statementsQuery = useQuery({
    queryKey: ["statements", consultation?.id],
    queryFn: () => listStatements(consultation!.id),
    enabled: consultation !== null,
  });

  const session = useSessionStore((state) =>
    consultation ? state.sessions[consultation.id] : undefined,
  );
  const setSession = useSessionStore((state) => state.setSession);
  const clearSession = useSessionStore((state) => state.clearSession);

  const entries = useVoteQueueStore((state) => state.entries);
  const answeredIds = useVoteQueueStore((state) => state.answeredIds);
  const entryCount = useVoteQueueStore((state) => state.entryCount);
  const castLocally = useVoteQueueStore((state) => state.castLocally);
  const markSynced = useVoteQueueStore((state) => state.markSynced);
  const markFailed = useVoteQueueStore((state) => state.markFailed);

  const [skippedIds, setSkippedIds] = useState<Set<number>>(new Set());
  const [current, setCurrent] = useState<Statement | null>(null);
  const [phase, setPhase] = useState<"loading" | "active" | "completed">("loading");
  const advanceToken = useRef(0);

  const ensureSession = useCallback(async (): Promise<{ sessionToken: string } | null> => {
    if (!consultation) return null;
    if (session) return { sessionToken: session.sessionToken };
    try {
      const joined = await joinConsultation(consultation.id);
      setSession(consultation.id, {
        participantId: joined.participant_id,
        sessionToken: joined.session_token,
      });
      return { sessionToken: joined.session_token };
    } catch {
      return null;
    }
  }, [consultation, session, setSession]);

  const advance = useCallback(
    async (options: { fromSkip: boolean; excludeIds: Set<number> }) => {
      if (!consultation || !statementsQuery.data) return;
      const pool = statementsQuery.data;
      const myToken = ++advanceToken.current;

      if (options.excludeIds.size >= pool.length) {
        setCurrent(null);
        setPhase("completed");
        return;
      }

      if (!options.fromSkip) {
        const sessionResult = await ensureSession();
        if (sessionResult) {
          const result = await withTimeout(
            fetchNextStatement(consultation.id, sessionResult.sessionToken),
            NEXT_STATEMENT_TIMEOUT_MS,
          ).catch(() => "timeout" as const);
          if (advanceToken.current !== myToken) return;
          if (result === null) {
            // Authoritative: the server derives this from real vote rows,
            // including ones cast in an earlier session this client has
            // no local memory of, so null here means genuinely nothing
            // left, not "ask locally instead".
            setCurrent(null);
            setPhase("completed");
            return;
          }
          if (result !== "timeout" && !options.excludeIds.has(result.id)) {
            setCurrent(result);
            setPhase("active");
            return;
          }
        }
      }

      const fallback = pickLocalNext(pool, options.excludeIds);
      if (advanceToken.current !== myToken) return;
      if (fallback === null) {
        setCurrent(null);
        setPhase("completed");
      } else {
        setCurrent(fallback);
        setPhase("active");
      }
    },
    [consultation, statementsQuery.data, ensureSession],
  );

  // Runs once statements are available, and intentionally does not depend
  // on current or phase: advance() itself sets those, and re-running this
  // effect whenever they change would loop.
  useEffect(() => {
    if (consultation && statementsQuery.data && current === null && phase === "loading") {
      void advance({ fromSkip: false, excludeIds: new Set(answeredIds) });
    }
  }, [consultation, statementsQuery.data]); // eslint-disable-line

  const vote = useCallback(
    (value: 1 | -1) => {
      if (!current || !consultation) return;
      const statementId = current.id;
      castLocally(statementId, value);
      setSkippedIds((prev) => {
        if (!prev.has(statementId)) return prev;
        const next = new Set(prev);
        next.delete(statementId);
        return next;
      });

      void (async () => {
        const sessionResult = await ensureSession();
        if (!sessionResult) {
          markFailed(statementId);
          return;
        }
        try {
          await postVote(consultation.id, sessionResult.sessionToken, statementId, value);
          markSynced(statementId);
        } catch (error) {
          if (error instanceof ApiError && error.status === 409) {
            markSynced(statementId);
            return;
          }
          if (error instanceof ApiError && error.status === 404) {
            clearSession(consultation.id);
          }
          markFailed(statementId);
        }
      })();

      const nextAnswered = new Set(answeredIds);
      nextAnswered.add(statementId);
      void advance({ fromSkip: false, excludeIds: new Set([...nextAnswered, ...skippedIds]) });
    },
    [
      current,
      consultation,
      castLocally,
      markSynced,
      markFailed,
      ensureSession,
      clearSession,
      answeredIds,
      skippedIds,
      advance,
    ],
  );

  const skip = useCallback(() => {
    if (!current) return;
    const statementId = current.id;
    const nextSkipped = new Set(skippedIds);
    nextSkipped.add(statementId);
    setSkippedIds(nextSkipped);
    void advance({ fromSkip: true, excludeIds: new Set([...answeredIds, ...nextSkipped]) });
  }, [current, skippedIds, answeredIds, advance]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const key = event.key.toLowerCase();
      if (key === "a") {
        event.preventDefault();
        vote(1);
      } else if (key === "d") {
        event.preventDefault();
        vote(-1);
      } else if (key === "s") {
        event.preventDefault();
        skip();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [vote, skip]);

  useEffect(() => {
    const interval = setInterval(() => {
      if (!consultation) return;
      const stored = useSessionStore.getState().sessions[consultation.id];
      if (!stored) return;
      for (const entry of useVoteQueueStore.getState().entries) {
        if (entry.status !== "failed") continue;
        postVote(consultation.id, stored.sessionToken, entry.statementId, entry.value)
          .then(() => markSynced(entry.statementId))
          .catch(() => undefined);
      }
    }, RETRY_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [consultation, markSynced]);

  const queuedCount = useMemo(() => pendingCount(entries), [entries]);

  if (consultationsQuery.isError || statementsQuery.isError) {
    return (
      <main className="voting-screen">
        <ErrorNote
          heading="This consultation did not load"
          body="Check your connection and reload the page to try again."
        />
      </main>
    );
  }

  if (consultationsQuery.isLoading || (consultation && statementsQuery.isLoading) || !consultation) {
    return (
      <main className="voting-screen">
        <StatementPanelSkeleton />
      </main>
    );
  }

  if (statementsQuery.data && statementsQuery.data.length === 0) {
    return (
      <main className="voting-screen">
        <EmptyState
          heading="No statements are open for voting yet"
          body="This consultation has not been seeded. Check back once statements are added."
        />
      </main>
    );
  }

  return (
    <main className="voting-screen">
      <header className="voting-screen__header">
        <h1 className="voting-screen__title">{consultation.title}</h1>
        <p className="voting-screen__question">{consultation.question}</p>
        {consultation.is_synthetic ? (
          <p className="voting-screen__synthetic-note">
            This consultation runs on synthetic data, generated for this build rather than collected
            from real submissions.
          </p>
        ) : null}
      </header>

      {phase === "completed" || (phase === "active" && current === null) ? (
        <EmptyState
          heading="You have voted on every statement currently open"
          body="New statements may still be added as the consultation continues. Check back later."
        />
      ) : phase === "active" && current ? (
        <StatementPanel
          statement={current}
          entryNumber={entryCount + 1}
          onAgree={() => vote(1)}
          onDisagree={() => vote(-1)}
          onSkip={skip}
        />
      ) : (
        <StatementPanelSkeleton />
      )}

      <p className="voting-screen__hint">Keyboard: A agree, D disagree, S skip.</p>

      {queuedCount > 0 ? (
        <p className="voting-screen__queue-note" role="status">
          {queuedCount === 1
            ? "1 vote is saved on this device and syncing to the server."
            : `${queuedCount} votes are saved on this device and syncing to the server.`}
        </p>
      ) : null}
    </main>
  );
}
