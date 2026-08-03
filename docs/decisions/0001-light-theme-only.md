# 0001: light theme only

## Context

Sabha's interface direction is an Indian government register: ruled ledger
paper, numbered entries, mono figures in right aligned columns, stamped
endorsements. A dark theme would need a second, independently tuned set of
ink, paper, rule, and faction colours to hold the same contrast and the same
quiet hierarchy, and the build window does not allow for two design systems
executed to the same standard.

## Decision

Sabha ships with one theme. There is no dark mode, no theme toggle, and no
`prefers-color-scheme` branch anywhere in the styles. Every token in
`tokens.css` is defined once, for the pale ledger paper ground described in
section 5.2 of the build instructions.

## Consequence

One theme executed precisely is better than two executed adequately, and
the ledger concept this interface is built around is inherently a light,
paper-toned surface. A future dark theme, if ever wanted, is a new design
pass, not a variable swap, and is explicitly out of scope for this build.
