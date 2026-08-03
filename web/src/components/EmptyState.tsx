import type { ReactNode } from "react";

interface EmptyStateProps {
  heading: string;
  body: string;
  action?: ReactNode;
}

/** What to show instead of nothing. Always says what to do next, per section 5.7. */
export function EmptyState({ heading, body, action }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <p className="empty-state__heading">{heading}</p>
      <p className="empty-state__body">{body}</p>
      {action}
    </div>
  );
}
