import { LedgerRow } from "../../components/LedgerRow";
import { StatementCode } from "../../components/StatementCode";
import type { RankingEntry } from "../../lib/api";
import { RollingFigure } from "./RollingFigure";

const MAX_ROWS = 10;

interface RankingColumnProps {
  heading: string;
  entries: RankingEntry[];
}

function RankingColumn({ heading, entries }: RankingColumnProps) {
  return (
    <div className="rankings-comparison__column">
      <h3 className="rankings-comparison__heading">{heading}</h3>
      {entries.length === 0 ? (
        <p className="rankings-comparison__empty">Nothing ranked yet.</p>
      ) : (
        entries.slice(0, MAX_ROWS).map((entry) => (
          <LedgerRow key={entry.statement_id}>
            <StatementCode value={entry.code} />
            <span className="rankings-comparison__text">{entry.text}</span>
            <RollingFigure
              value={entry.score}
              ariaLabel={`${heading}, ${entry.code}, score ${entry.score.toFixed(2)}`}
            />
          </LedgerRow>
        ))
      )}
    </div>
  );
}

interface RankingsComparisonProps {
  bridging: RankingEntry[];
  majority: RankingEntry[];
}

/**
 * The bridging ranking beside the majority ranking, on purpose: the
 * disagreement between the two is the point being made, not a detail
 * to reconcile away.
 */
export function RankingsComparison({ bridging, majority }: RankingsComparisonProps) {
  return (
    <div className="rankings-comparison">
      <RankingColumn heading="Bridging ranking" entries={bridging} />
      <RankingColumn heading="Majority ranking" entries={majority} />
    </div>
  );
}
