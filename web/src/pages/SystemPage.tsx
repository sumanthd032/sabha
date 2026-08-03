import { useState } from "react";

import { Button } from "../components/Button";
import { EmptyState } from "../components/EmptyState";
import { ErrorNote } from "../components/ErrorNote";
import { Field } from "../components/Field";
import { Figure } from "../components/Figure";
import { LedgerRow } from "../components/LedgerRow";
import { Rule } from "../components/Rule";
import { StatementCode } from "../components/StatementCode";

const COLOURS: Array<{ name: string; token: string }> = [
  { name: "ink", token: "--ink" },
  { name: "ink soft", token: "--ink-soft" },
  { name: "ink faint", token: "--ink-faint" },
  { name: "paper", token: "--paper" },
  { name: "paper raised", token: "--paper-raised" },
  { name: "rule", token: "--rule" },
  { name: "rule strong", token: "--rule-strong" },
  { name: "consensus, certificate only", token: "--consensus" },
  { name: "flag, escalation only", token: "--flag" },
  { name: "faction 1", token: "--faction-1" },
  { name: "faction 2", token: "--faction-2" },
  { name: "faction 3", token: "--faction-3" },
  { name: "faction 4", token: "--faction-4" },
  { name: "faction 5", token: "--faction-5" },
];

const TYPE_SCALE: Array<{
  role: string;
  note: string;
  fontFamily: string;
  fontSize: string;
  lineHeight: string;
  fontWeight: number;
  letterSpacing?: string;
}> = [
  {
    role: "display-l",
    note: "Zilla Slab 600, 44/48, page titles only",
    fontFamily: "var(--font-display)",
    fontSize: "var(--text-display-l-size)",
    lineHeight: "var(--text-display-l-line)",
    fontWeight: 600,
  },
  {
    role: "display-s",
    note: "Zilla Slab 600, 28/32, certificate heading only",
    fontFamily: "var(--font-display)",
    fontSize: "var(--text-display-s-size)",
    lineHeight: "var(--text-display-s-line)",
    fontWeight: 600,
  },
  {
    role: "body-l",
    note: "Plex Sans 400, 17/28, statement text",
    fontFamily: "var(--font-body)",
    fontSize: "var(--text-body-l-size)",
    lineHeight: "var(--text-body-l-line)",
    fontWeight: 400,
  },
  {
    role: "body",
    note: "Plex Sans 400, 15/24, default",
    fontFamily: "var(--font-body)",
    fontSize: "var(--text-body-size)",
    lineHeight: "var(--text-body-line)",
    fontWeight: 400,
  },
  {
    role: "label",
    note: "Plex Sans 500, 13/16, tracking 0.02em, field and column labels",
    fontFamily: "var(--font-body)",
    fontSize: "var(--text-label-size)",
    lineHeight: "var(--text-label-line)",
    fontWeight: 500,
    letterSpacing: "var(--text-label-tracking)",
  },
  {
    role: "figure",
    note: "Plex Mono 500, 15/24, tabular nums, every number",
    fontFamily: "var(--font-mono)",
    fontSize: "var(--text-figure-size)",
    lineHeight: "var(--text-figure-line)",
    fontWeight: 500,
  },
  {
    role: "code",
    note: "Plex Mono 400, 12/16, tracking 0.04em, statement and filing codes",
    fontFamily: "var(--font-mono)",
    fontSize: "var(--text-code-size)",
    lineHeight: "var(--text-code-line)",
    fontWeight: 400,
    letterSpacing: "var(--text-code-tracking)",
  },
];

const SPACING_SCALE = [4, 8, 12, 16, 24, 32, 48, 64, 96];

/**
 * A working reference of every design token and every base component
 * state. Not part of the public consultation flow: this is the page a
 * reader checks against docs/design-system.md while building later steps.
 */
export function SystemPage() {
  const [fieldValue, setFieldValue] = useState("");

  return (
    <main
      style={{
        maxWidth: "var(--content-max-width)",
        margin: "0 auto",
        padding: "var(--space-32) var(--space-24)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-48)",
      }}
    >
      <header>
        <h1
          style={{
            fontFamily: "var(--font-display)",
            fontWeight: 600,
            fontSize: "var(--text-display-l-size)",
            lineHeight: "var(--text-display-l-line)",
            margin: 0,
          }}
        >
          System reference
        </h1>
        <p style={{ color: "var(--ink-soft)", marginTop: "var(--space-8)" }}>
          Every token in tokens.css and every state of every base component. Not a
          screen a participant ever sees.
        </p>
      </header>

      <section aria-labelledby="colour-heading">
        <h2 id="colour-heading" className="field__label">
          Colour
        </h2>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))",
            gap: "var(--space-16)",
            marginTop: "var(--space-16)",
          }}
        >
          {COLOURS.map((colour) => (
            <div key={colour.token} style={{ display: "flex", flexDirection: "column", gap: "var(--space-8)" }}>
              <div
                style={{
                  height: "var(--space-48)",
                  background: `var(${colour.token})`,
                  border: "var(--rule-width) solid var(--rule)",
                }}
              />
              <span style={{ fontSize: "var(--text-body-size)" }}>{colour.name}</span>
              <StatementCode value={colour.token} />
            </div>
          ))}
        </div>
      </section>

      <Rule tone="strong" />

      <section aria-labelledby="type-heading">
        <h2 id="type-heading" className="field__label">
          Type
        </h2>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-24)", marginTop: "var(--space-16)" }}>
          {TYPE_SCALE.map((spec) => (
            <div key={spec.role}>
              <p
                style={{
                  fontFamily: spec.fontFamily,
                  fontSize: spec.fontSize,
                  lineHeight: spec.lineHeight,
                  fontWeight: spec.fontWeight,
                  letterSpacing: spec.letterSpacing,
                  margin: 0,
                }}
              >
                Statement S-0142 finds broad agreement
              </p>
              <p style={{ color: "var(--ink-faint)", fontSize: "var(--text-code-size)", marginTop: "var(--space-4)" }}>
                {spec.role}, {spec.note}
              </p>
            </div>
          ))}
        </div>
      </section>

      <Rule tone="strong" />

      <section aria-labelledby="spacing-heading">
        <h2 id="spacing-heading" className="field__label">
          Spacing
        </h2>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", gap: "var(--space-16)", marginTop: "var(--space-16)" }}>
          {SPACING_SCALE.map((size) => (
            <div key={size} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "var(--space-8)" }}>
              <div style={{ width: `${size}px`, height: `${size}px`, background: "var(--ink)" }} />
              <Figure value={`${size}`} />
            </div>
          ))}
        </div>
      </section>

      <Rule tone="strong" />

      <section aria-labelledby="rule-heading">
        <h2 id="rule-heading" className="field__label">
          Rule
        </h2>
        <div style={{ marginTop: "var(--space-16)", display: "flex", flexDirection: "column", gap: "var(--space-16)" }}>
          <Rule />
          <Rule tone="strong" />
        </div>
      </section>

      <section aria-labelledby="button-heading">
        <h2 id="button-heading" className="field__label">
          Button
        </h2>
        <div style={{ marginTop: "var(--space-16)", display: "flex", flexWrap: "wrap", gap: "var(--space-16)" }}>
          <Button variant="primary">File the clause set</Button>
          <Button variant="secondary">Review before filing</Button>
          <Button variant="primary" disabled>
            File the clause set
          </Button>
        </div>
      </section>

      <section aria-labelledby="field-heading">
        <h2 id="field-heading" className="field__label">
          Field
        </h2>
        <div style={{ marginTop: "var(--space-16)", display: "flex", flexWrap: "wrap", gap: "var(--space-24)", maxWidth: "480px" }}>
          <Field
            label="Consultation title"
            value={fieldValue}
            onChange={(event) => setFieldValue(event.target.value)}
            placeholder="Platform and gig work regulation"
          />
          <Field label="Statutory deadline" value="" onChange={() => {}} disabled />
          <Field
            label="Ministry email"
            value="not-an-address"
            onChange={() => {}}
            error="Enter a complete email address, such as name@ministry.gov.in"
          />
        </div>
      </section>

      <section aria-labelledby="ledger-row-heading">
        <h2 id="ledger-row-heading" className="field__label">
          Ledger row
        </h2>
        <div style={{ marginTop: "var(--space-16)" }}>
          <LedgerRow>
            <StatementCode value="S-0142" />
            <span>Platform aggregators must disclose algorithmic ranking criteria</span>
            <Figure value="0.81" />
          </LedgerRow>
          <LedgerRow>
            <StatementCode value="S-0087" />
            <span>Gig workers should be classified as employees in every case</span>
            <Figure value="0.34" />
          </LedgerRow>
        </div>
      </section>

      <section aria-labelledby="empty-state-heading">
        <h2 id="empty-state-heading" className="field__label">
          Empty state
        </h2>
        <div style={{ marginTop: "var(--space-16)" }}>
          <EmptyState
            heading="No statements are open for voting yet"
            body="This consultation has not been seeded. Load a statement set before inviting participants."
            action={<Button variant="secondary">Load statements</Button>}
          />
        </div>
      </section>

      <section aria-labelledby="error-note-heading">
        <h2 id="error-note-heading" className="field__label">
          Error note
        </h2>
        <div style={{ marginTop: "var(--space-16)" }}>
          <ErrorNote
            heading="Your vote did not reach the server"
            body="It is saved on this device and will send automatically once the connection returns."
          />
        </div>
      </section>
    </main>
  );
}
