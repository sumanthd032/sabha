interface StatementCodeProps {
  value: string;
}

/** A statement or filing reference, such as S-0142 or FIL-0007. Uppercase mono by convention. */
export function StatementCode({ value }: StatementCodeProps) {
  return <span className="statement-code">{value}</span>;
}
