/**
 * The shape of the statement panel that is about to fill, not a spinner,
 * per the loading state rule in section 5.7. No animation: a static
 * placeholder is the honest picture of "not here yet", not motion for
 * its own sake.
 */
export function StatementPanelSkeleton() {
  return (
    <div className="statement-panel statement-panel--skeleton" aria-hidden="true">
      <div className="statement-panel__meta">
        <div className="statement-panel__skeleton-block statement-panel__skeleton-block--code" />
        <div className="statement-panel__skeleton-block statement-panel__skeleton-block--entry" />
      </div>
      <div className="statement-panel__skeleton-block statement-panel__skeleton-block--line" />
      <div className="statement-panel__skeleton-block statement-panel__skeleton-block--line-short" />
      <div className="statement-panel__actions">
        <div className="statement-panel__skeleton-block statement-panel__skeleton-block--action" />
        <div className="statement-panel__skeleton-block statement-panel__skeleton-block--action" />
        <div className="statement-panel__skeleton-block statement-panel__skeleton-block--action" />
      </div>
    </div>
  );
}
