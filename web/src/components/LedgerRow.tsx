import type { ReactNode } from "react";

interface LedgerRowProps {
  children: ReactNode;
}

/** A row with a bottom rule. A row without one is a bug, so this is the only way to lay one out. */
export function LedgerRow({ children }: LedgerRowProps) {
  return <div className="ledger-row">{children}</div>;
}
