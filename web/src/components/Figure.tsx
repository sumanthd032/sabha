interface FigureProps {
  value: string | number;
  "aria-label"?: string;
}

/** A mono, tabular, right-aligned number. Every figure in the interface renders through this. */
export function Figure({ value, "aria-label": ariaLabel }: FigureProps) {
  return (
    <span className="figure" aria-label={ariaLabel}>
      {value}
    </span>
  );
}
