import { create } from "zustand";

export type VoteEntryStatus = "pending" | "synced" | "failed";

export interface VoteEntry {
  statementId: number;
  value: 1 | -1;
  status: VoteEntryStatus;
}

interface VoteQueueState {
  entries: VoteEntry[];
  answeredIds: Set<number>;
  entryCount: number;
  castLocally: (statementId: number, value: 1 | -1) => void;
  markSynced: (statementId: number) => void;
  markFailed: (statementId: number) => void;
  reset: () => void;
}

/**
 * The record of votes this participant has cast this session: recorded
 * locally the instant a choice is made, reconciled with the server in
 * the background. A vote never blocks on the network to register, and
 * "queued" here is exactly what a slow connection looks like: entries
 * still marked pending or failed rather than synced.
 */
export const useVoteQueueStore = create<VoteQueueState>((set) => ({
  entries: [],
  answeredIds: new Set(),
  entryCount: 0,
  castLocally: (statementId, value) =>
    set((state) => ({
      entries: [...state.entries, { statementId, value, status: "pending" }],
      answeredIds: new Set(state.answeredIds).add(statementId),
      entryCount: state.entryCount + 1,
    })),
  markSynced: (statementId) =>
    set((state) => ({
      entries: state.entries.map((entry) =>
        entry.statementId === statementId ? { ...entry, status: "synced" } : entry,
      ),
    })),
  markFailed: (statementId) =>
    set((state) => ({
      entries: state.entries.map((entry) =>
        entry.statementId === statementId ? { ...entry, status: "failed" } : entry,
      ),
    })),
  reset: () => set({ entries: [], answeredIds: new Set(), entryCount: 0 }),
}));

export function pendingCount(entries: VoteEntry[]): number {
  return entries.filter((entry) => entry.status !== "synced").length;
}
