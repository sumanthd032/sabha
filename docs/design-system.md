# Design system

The tokens below are the only colours and sizes permitted anywhere in the
application. They live in `web/src/styles/tokens.css` as CSS custom
properties; nothing outside that file, and `components.css` which derives
from it, should contain a colour or size literal. A working reference of
every token and every component state renders at `/system`.

## Tokens

### Colour

| Token | Value | Use |
|---|---|---|
| `--ink` | `#14161a` | primary text, primary button fill, focus outline |
| `--ink-soft` | `#494e55` | secondary text, hover borders |
| `--ink-faint` | `#7c838c` | disabled text, captions |
| `--paper` | `#edeee8` | page background |
| `--paper-raised` | `#f5f6f1` | raised surfaces: inputs, cards, certificate ground |
| `--rule` | `#c9cbc0` | default hairline rule |
| `--rule-strong` | `#a9ac9f` | emphasised rule, default input border |
| `--consensus` | `#17594a` | reserved. The consensus certificate only. |
| `--flag` | `#8c2b1e` | reserved. Escalation state and coordination warnings only. |
| `--faction-1` through `--faction-5` | see tokens.css | opinion cluster colour, assigned by cluster index and arbitrary |

`--consensus` and `--flag` appearing anywhere outside their one reserved
use is a bug, not a style choice. A routine error, including a failed
network request or a validation failure, is neither an escalation nor a
coordination warning, and is never coloured with `--flag`. `ErrorNote`
communicates error state through weight and an ink border, not colour.

### Type

Faces: `--font-display` (Zilla Slab, weight 600 only), `--font-body` (IBM
Plex Sans with IBM Plex Sans Devanagari), `--font-mono` (IBM Plex Mono).
Loaded through `@fontsource` in `main.tsx`, never fetched from Google
Fonts at request time.

| Role | Tokens | Face and weight | Where |
|---|---|---|---|
| display-l | `--text-display-l-size` / `-line` | Zilla Slab 600, 44/48 | page titles only |
| display-s | `--text-display-s-size` / `-line` | Zilla Slab 600, 28/32 | certificate heading only |
| body-l | `--text-body-l-size` / `-line` | Plex Sans 400, 17/28 | statement text |
| body | `--text-body-size` / `-line` | Plex Sans 400, 15/24 | default |
| label | `--text-label-size` / `-line` / `-tracking` | Plex Sans 500, 13/16, 0.02em | field and column labels |
| figure | `--text-figure-size` / `-line` | Plex Mono 500, 15/24, tabular nums | every number, via `Figure` |
| code | `--text-code-size` / `-line` / `-tracking` | Plex Mono 400, 12/16, 0.04em | statement and filing codes, via `StatementCode` |

Zilla Slab is reserved for page titles and the certificate heading. It is
never used for body text, labels, or button copy.

### Spacing and layout

`--space-4` through `--space-96` follow the 4px base scale (4, 8, 12, 16,
24, 32, 48, 64, 96), on an 8px baseline. `--content-max-width` is 1120px
across `--grid-columns` of 12 with a `--grid-gutter` of 24px.

### Structure

`--rule-width` (1px) is the hairline used at the bottom of every list row
and section boundary; a row without one is a bug. `--radius-sm` (2px) is
the only radius in the application, permitted on buttons and inputs only.
Everything else is `--radius-none`. There are no shadows anywhere.

### Focus

`--focus-outline-width` (2px) and `--focus-outline-offset` (2px), always
in `--ink`, applied globally through a single `:focus-visible` rule in
`index.css`. No component overrides focus styling; removing an outline
without replacing it is a bug.

### Motion

`--dur-micro` (120ms), `--dur-settle` (240ms), `--dur-tally` (400ms),
`--ease`. The only motion in the base components is a border colour
change on hover, using `--dur-micro`. The one orchestrated moment, the
vote-cast settle and figure roll, lands in step 8 using `--dur-settle`
and `--dur-tally`. `prefers-reduced-motion: reduce` collapses every
transition and animation to near zero globally, in `tokens.css`.

## Components

All in `web/src/components/`.

- **Rule**: a 1px divider. `tone="default" | "strong"`.
- **Figure**: mono, tabular, right-aligned. Every number in the interface
  renders through this, never as plain text.
- **StatementCode**: a statement or filing reference such as `S-0142` or
  `FIL-0007`, mono, uppercase by convention.
- **Button**: `variant="primary" | "secondary"`. Native `<button>`,
  `type="button"` by default. A border colour change on hover is the only
  transition. Disabled state is a true `disabled` attribute, never a
  visual-only imitation.
- **Field**: a labelled input. `label` is required, so an unlabelled input
  cannot be built with this component. `error` renders the message linked
  by `aria-describedby` and sets `aria-invalid`.
- **LedgerRow**: a flex row with a bottom rule. The layout primitive for
  every list in the application.
- **EmptyState**: `heading`, `body`, optional `action`. The body always
  says what to do next, per the quality floor in section 5.7 of the build
  instructions.
- **ErrorNote**: `heading`, `body`, `role="alert"`. States what happened
  and how to fix it. Never an apology, never `--flag`.

## Routing

There is no router dependency: react-router is not on the approved
dependency list for a handful of top level pages, so `lib/router.tsx` is a
small Zustand store holding the current pathname plus a `Link` that
intercepts plain left-clicks. `/system` is the first route it serves, a
working reference of every token and component state above.
