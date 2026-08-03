import { Button } from "../../components/Button";
import { Figure } from "../../components/Figure";
import { StatementCode } from "../../components/StatementCode";
import type { Statement } from "../../lib/api";

interface StatementPanelProps {
  statement: Statement;
  entryNumber: number;
  onAgree: () => void;
  onDisagree: () => void;
  onSkip: () => void;
}

/**
 * One statement, three actions. No colour codes agree or disagree: the
 * only meaning either colour carries in this application belongs to
 * the consensus certificate and to escalation, and a single statement
 * is neither.
 */
export function StatementPanel({
  statement,
  entryNumber,
  onAgree,
  onDisagree,
  onSkip,
}: StatementPanelProps) {
  return (
    <div className="statement-panel">
      <div className="statement-panel__meta">
        <StatementCode value={statement.code} />
        <span className="statement-panel__entry">
          <span className="statement-panel__entry-label">Entry</span>
          <Figure value={entryNumber} aria-label={`Ledger entry ${entryNumber}`} />
        </span>
      </div>

      <p className="statement-panel__text" lang={statement.language}>
        {statement.text}
      </p>

      {statement.author_type === "generated" ? (
        <p className="statement-panel__provenance">
          Proposed reformulation of a participant statement.
        </p>
      ) : null}

      <div className="statement-panel__actions">
        <Button variant="secondary" onClick={onAgree}>
          Agree
          <kbd className="statement-panel__key">A</kbd>
        </Button>
        <Button variant="secondary" onClick={onDisagree}>
          Disagree
          <kbd className="statement-panel__key">D</kbd>
        </Button>
        <button type="button" className="statement-panel__skip" onClick={onSkip}>
          Skip
          <kbd className="statement-panel__key">S</kbd>
        </button>
      </div>
    </div>
  );
}
