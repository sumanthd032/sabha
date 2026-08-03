interface ErrorNoteProps {
  heading: string;
  body: string;
}

/**
 * What happened and how to fix it, never an apology. Never coloured with
 * --flag: that colour is reserved for escalation state and coordination
 * warnings, and a routine error is neither.
 */
export function ErrorNote({ heading, body }: ErrorNoteProps) {
  return (
    <div className="error-note" role="alert">
      <p className="error-note__heading">{heading}</p>
      <p className="error-note__body">{body}</p>
    </div>
  );
}
