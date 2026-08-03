interface RuleProps {
  tone?: "default" | "strong";
}

/** A 1px ledger rule, the structural signature used at every row and section boundary. */
export function Rule({ tone = "default" }: RuleProps) {
  const className = tone === "strong" ? "rule rule--strong" : "rule";
  return <hr className={className} />;
}
