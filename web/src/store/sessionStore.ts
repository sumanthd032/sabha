import { create } from "zustand";
import { persist } from "zustand/middleware";

interface StoredSession {
  participantId: number;
  sessionToken: string;
}

interface SessionState {
  sessions: Record<number, StoredSession>;
  setSession: (consultationId: number, session: StoredSession) => void;
  clearSession: (consultationId: number) => void;
}

/**
 * A participant's join persists across a reload, keyed by consultation,
 * so refreshing the page mid session does not spend a fresh anonymous
 * participant row and does not lose progress already made.
 */
export const useSessionStore = create<SessionState>()(
  persist(
    (set) => ({
      sessions: {},
      setSession: (consultationId, session) =>
        set((state) => ({ sessions: { ...state.sessions, [consultationId]: session } })),
      clearSession: (consultationId) =>
        set((state) => {
          const sessions = { ...state.sessions };
          delete sessions[consultationId];
          return { sessions };
        }),
    }),
    { name: "sabha-session" },
  ),
);
