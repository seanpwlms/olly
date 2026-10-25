# Olly Dashboard Design

Olly is a triage tool. Someone opens it because a check fired, or to confirm
nothing did. Every screen should answer "what needs me, and where is it?"
quickly, then get out of the way. The look should be calm and precise, like a
well-set instrument panel, not a marketing page.

Tokens live in `frontend/src/styles/global.css`. To add a value, add it to the
token table below and to `global.css` in the same change.

## Principles

1. **Data first.** Tables and numbers are the product. Decoration that doesn't
   help someone read or act on data gets cut.
2. **Say it once.** Each fact gets one visual signal. Severity is a badge *or*
   a colored count, never a badge plus a stripe plus a tinted row.
3. **Color means something.** Red, amber and green are reserved for
   severity and health. The accent marks interaction (links, focus,
   selection, the primary button) and work in flight (the "in progress"
   status). Nothing else gets color.
4. **Flat by default.** Content sits on the page. A container needs a reason:
   a chart, a grouped form, or something that floats.

## Tokens

The literal values a design-system check compares against. Tailwind utilities
(`text-accent-700`, `bg-gray-50`, …) resolve to these. Declare the theme with
`@theme static` so every token is emitted as a CSS variable, including the ones
that charts reference with `var()`.

### Color

| Token | Value | Token | Value |
|---|---|---|---|
| `accent-50` | `oklch(0.975 0.012 225)` | `gray-50` | `oklch(0.984 0.002 225)` |
| `accent-100` | `oklch(0.945 0.025 225)` | `gray-100` | `oklch(0.965 0.004 225)` |
| `accent-200` | `oklch(0.885 0.045 225)` | `gray-200` | `oklch(0.925 0.006 225)` |
| `accent-300` | `oklch(0.8 0.07 225)` | `gray-300` | `oklch(0.87 0.008 225)` |
| `accent-400` | `oklch(0.71 0.09 225)` | `gray-400` | `oklch(0.71 0.012 225)` |
| `accent-500` | `oklch(0.6 0.1 225)` | `gray-500` | `oklch(0.555 0.014 225)` |
| `accent-600` | `oklch(0.5 0.095 225)` | `gray-600` | `oklch(0.45 0.014 225)` |
| `accent-700` | `oklch(0.43 0.085 225)` | `gray-700` | `oklch(0.375 0.013 225)` |
| `accent-800` | `oklch(0.36 0.07 225)` | `gray-800` | `oklch(0.28 0.012 225)` |
| `accent-900` | `oklch(0.3 0.055 225)` | `gray-900` | `oklch(0.21 0.01 225)` |
| `accent-950` | `oklch(0.21 0.04 225)` | `gray-950` | `oklch(0.155 0.008 225)` |

Status hues use Tailwind's stock `red-*`, `amber-*` and `emerald-*` scales
unchanged. No other hue families: no `blue`, `purple`, `green`, `indigo`, `sky`
and so on. White (`#ffffff`) is the only literal color outside these scales.

### Type, radius, motion

| Token | Value |
|---|---|
| `font-sans` | `"IBM Plex Sans", ui-sans-serif, system-ui, sans-serif` |
| `font-mono` | `"IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace` |
| Font sizes | 12px `text-xs` · 14px `text-sm` · 18px `text-lg` · 24px `text-2xl` |
| Font weights | 400 · 500 · 600 (the only weights loaded) |
| Radii | 4px `rounded` · 8px `rounded-lg` · 9999px `rounded-full` |
| Durations | 150ms (hover, chevron) · 200ms (sidebar collapse) |

## Typography

| Role | Family | Size / weight |
|---|---|---|
| UI and body | Plex Sans | `text-sm` / 400 |
| Page title (h1) | Plex Sans | `text-2xl` / 600 |
| Section heading (h2) | Plex Sans | `text-lg` / 600 |
| Sub-heading (h3, chart and panel titles) | Plex Sans | `text-sm` / 600 |
| Table header, meta, captions | Plex Sans | `text-xs` / 500, muted |
| Stat value | Plex Sans | `text-2xl` / 600 |
| Identifiers (`schema.table`, columns, node ids, SQL, types) | Plex Mono | inherits size |

- Four sizes only, and nothing under 12px. No arbitrary `text-[…]` values. Plex
  Sans and Plex Mono are designed to pair at the same size, so identifiers
  inherit their context size rather than being scaled down.
- The sidebar wordmark ("olly") is the one exception: `text-xl` / 600. It's the
  logo, not a text style.
- Sentence case everywhere: headings, labels, stat labels, buttons, table
  headers and option labels ("Not started", "Tables monitored"). No all-caps
  letter-spaced labels.
- Numbers are tabular (set on `body`) so columns of counts line up.
- Fonts are self-hosted via `@fontsource`; the dashboard must work offline.

## Color usage

| Color | Use |
|---|---|
| `gray-*` | Text, borders, surfaces |
| `accent-*` | Links (`accent-700` / dark `accent-300`), focus rings (`accent-500`), selection, primary button (`accent-600`), "in progress" status |
| `red-*` | Errors, failed checks, removed columns |
| `amber-*` | Warnings, stale. Text on light backgrounds is `amber-700`; `amber-600` fails contrast |
| `emerald-*` | Healthy, completed, added columns |

- Page `gray-50` / dark `gray-950`. Raised surface `white` / dark `gray-900`.
  Sidebar `gray-900` in both themes.
- Text roles (light / dark):
  - primary `gray-900` / `gray-100`
  - secondary `gray-600` / `gray-400`
  - muted `gray-500` / `gray-400`
- Never use `gray-400` or lighter for text on a light surface, or `gray-500`
  or darker for text on a dark surface; both fail 4.5:1. Icons, rules and
  disabled controls are exempt, since they only need 3:1.
- No gradients, glows, or blurred backdrops.
- Status: not started = gray, in progress = accent, no action = muted gray,
  completed = emerald.

## Shape, depth and spacing

- Radius by shape, not by size:
  - `rounded-full` for things that are pill- or dot-shaped by nature: filter
    chips, count pills, status dots, progress bars.
  - `rounded-lg` for anything rectangular you type into or that contains
    content: inputs, selects, buttons, panels, popovers, dialogs.
  - `rounded` for badges and inline `code`.
  - Nothing else.
- Borders: 1px `gray-200` / dark `gray-800`. Row dividers `gray-100` /
  dark `gray-800/70`.
- Shadows only on things that float above the page: popovers (`shadow-lg`) and
  dialogs (`shadow-xl`). Never on cards, tables, or stats, and never as a hover
  effect.
- Spacing: sections `mb-6`; heading-to-content `mb-3`; table cells `px-3 py-2.5`;
  stat cells `px-4 py-3`. Keep related things tight and separate groups clearly.
  Don't use one gap for everything.

## Components

- **Tables (`DataTable`)** sit directly on the page: a header rule, row
  dividers and a subtle row hover. No card, no zebra stripes, no left-border
  accents. Expandable rows use the `Chevron` button. Several stacked tables use
  `fixed` + column `className` widths so they align.
- **Stats (`StatsRow` + `StatCard`)** form one framed strip divided by hairlines.
  The label comes above the value, and severity colors only the value. Use them
  for a few context numbers. If the table below already shows a count, write a
  summary line instead (see Findings).
- **Badges** (`rounded`, `px-1.5`, `text-xs` / 500) label a categorical
  state: severity, status, change type. They hold words, not numbers.
- **Count pills** (`rounded-full`, `px-1.5`, `text-xs` / 600, tinted
  background) hold a number next to a navigation item or filter chip, e.g.
  the sidebar's error/warning counts. They are not used in tables or prose,
  where a colored count ("3 errors") is used instead.
- **Identifiers** always go through `TableRef`: monospace, the schema prefix
  muted, linked unless `plain`.
- **Empty values** in a table cell or stat are a single em dash `—` in muted
  text. This is the only place an em dash appears (see Copy).
- **Empty and healthy states** are one line of text, muted. A green notice is
  reserved for "all checks passing".
- **Filters**: primary facets as chips; secondary ones in `FilterPopover`;
  everything applied shown as removable chips in `ActiveFilters`.
- **Navigation**: the left sidebar shows per-section counts and the last-check
  time. Pages don't repeat the last-check time.

## Charts

Recharts takes colors as strings. Pass token variables
(`stroke="var(--color-accent-500)"`), never hex literals, so charts follow the
palette and dark mode.

| Series role | Color |
|---|---|
| The measured value (row count, cost, run time) | `accent-500` |
| A second, comparison series (previous period, average) | `gray-400`, dashed |
| Error counts, failed runs, anomaly markers | `red-500` |
| Event markers that aren't severity (schema change) | `--chart-axis`, dashed |
| Warning counts | `amber-500` |
| Area fills under a severity line | the same hue at 15% opacity |
| Gridlines / axes | `--chart-grid` / `--chart-axis` |

- Red and amber in a chart mean exactly what they mean elsewhere. The measured
  value is never red just because red is next in a list.
- One accent series per chart. If a chart needs more than two non-severity
  series, it's two charts.
- No gradients, no 3D, no drop shadows on lines. Points stay small (radius
  3px or less). Axis and annotation text is 12px, the same floor as everywhere else.
- Chart panels are the one routine container: `rounded-lg`, 1px border, white /
  `gray-900`, with an h3 title.

## Focus and accessibility

- Every interactive element shows a visible keyboard focus. A base rule in
  `global.css` gives links, buttons, selects and checkboxes a 2px `accent-500`
  outline on `:focus-visible`, so components don't restate it. Text fields
  use `focus:outline-none focus:ring-2 focus:ring-accent-500/40` instead.
  Never `outline-none` without a ring.
- Anything clickable is a `<button>` or a link. A clickable row or `div` is
  allowed only as a mouse shortcut for a real control in the same row.
- Never nest an interactive element inside a `<button>` or a link.
- Disclosure controls carry `aria-expanded`; sortable headers carry `aria-sort`;
  icon-only buttons carry `aria-label`.
- Color is never the only signal: severity always comes with a word ("error")
  or a count label.

## Responsive

- At `lg` (1024px) and above, the sidebar is fixed. Below that it becomes a
  drawer behind a top bar.
- Tables scroll horizontally inside their own wrapper (`overflow-x-auto`) and
  never make the page scroll sideways. Identifier and description columns may
  wrap; numeric, time and status columns don't (`whitespace-nowrap`).
- Stat strips reflow with `auto-fit` (minimum 140px per cell). The toolbar
  wraps; the search field goes full width below `sm`.
- The page gutter is `px-6` on desktop and `px-4` below `sm`.

## Formatting

- **Counts**: `toLocaleString()` (1,234,567). With a unit, pluralize properly
  ("1 error", "3 errors").
- **Money**: `$1,234.56`, always two decimals, en-US grouping.
- **Percent**: one decimal for changes (`+12.5%`), whole numbers for shares
  (`40%`). Signed values always show the sign.
- **Durations**: `12.4s` under a minute, `3m 5s` above. One `formatDuration`
  in `utils/`, not a copy per component.
- **Timestamps**: everything goes through `utils/time.ts`. Lists use
  `<RelativeTime>` ("3h ago", with the absolute time in a tooltip). Detail
  views show `formatTimestamp`. Never slice ISO strings inline.
- **Pending text** ends with a real ellipsis: "Saving…", "Search findings…".

## Icons

- Inline SVG only, drawn with `currentColor` so they follow text color. No
  emoji or Unicode symbols as icons (☀ ▼ ✓ ×). Use `Chevron`, `CloseIcon` and
  `NavIcon`. Typographic arrows in text ("source → target", sort ↑↓) are text,
  not icons, and are fine.
- Sizes: 20px (`h-5 w-5`) in navigation, 16px (`h-4 w-4`) inline with text.
- No icon tiles, meaning no icon inside a colored rounded square.
- Icons support a label and never replace one, except in the collapsed sidebar,
  where the label moves to a tooltip and `aria-label`.

## Motion

- Only state transitions: color on hover (`transition-colors`, 150ms), chevron
  rotation (150ms), and the sidebar collapse (200ms). No bounce or elastic
  easing, no pulsing dots, and no entrance animations on content.
- Skeletons may pulse while loading.
- `prefers-reduced-motion` is handled globally in `global.css`: transitions
  and animations are cut to near zero, so components don't need `motion-safe:`.

## Copy

- Plain and specific: "9 errors · 3 errors more than the previous check", not
  "Critical Issues Detected".
- Say only what the data supports. Run-to-run comparisons are net totals, so
  write "more/fewer than the previous check", never "new" or "resolved", until
  findings are matched across runs.
- No em dashes in sentences. Use a full stop, or a middle dot (`·`) between
  items in a list. The em dash is reserved for empty values (see Components).
- Use the same word for the same concept everywhere. It's "status" in the UI,
  even though the API field is `disposition`.

## Enforcement

`npm run lint:design` (in `frontend/`, script at `scripts/design-lint.mjs`)
greps `src/` and fails on the mechanical items: stripes, card shadows,
uppercase labels, arbitrary text sizes, `font-bold`, off-palette hues, hex
colors outside `global.css`, off-scale radii, `outline-none` without a ring,
and Unicode icons. The judgment calls (Title Case, contrast on a given
surface, severity shown twice) stay on the checklist below.

## Don'ts (quick check before merging UI)

- [ ] Colored left stripe on a card or row
- [ ] Shadow on a non-floating element, or a hover shadow
- [ ] Uppercase + tracking-wide label, or Title Case label
- [ ] Text under 12px, an arbitrary `text-[…]` size, or text that fails 4.5:1
- [ ] Severity shown more than once for the same item
- [ ] Card inside a card
- [ ] A hue outside accent / gray / red / amber / emerald, or a hex color in a component
- [ ] Interactive element nested inside a `<button>`; clickable `div` with no
      keyboard path; missing focus style
- [ ] Hand-rolled `<table>` or `schema.table` link
- [ ] Emoji or Unicode symbol used as an icon
- [ ] Em dash in a sentence
