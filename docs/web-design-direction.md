# Web UI design direction (PROVISIONAL)

Provisional: the owner will supply a UI notes list later; anything in that list overrides this page.

## Who and where
Owners, managers and attendants on ordinary Windows PCs (some with touch screens), in a busy
forecourt office: interrupted often, glancing at the screen, sometimes with wet or gloved hands.
The screen has to be **calm, fast, and hard to get wrong**.

## Principles
1. **Fast entry, keyboard first.** Every form is operable with Tab / Enter / Esc only; the first
   field is focused on open; Enter submits; Esc cancels. Sensible defaults (today's date, the
   last employee used, a quantity field that accepts the number straight away).
2. **Touch-safe.** Every control is at least 44 x 44 px (`--size-touch`). Dense table rows are
   40 px but their action buttons keep a 44 px hit area. No hover-only actions.
3. **Dense but readable.** Tables use tabular figures, right-aligned numbers at a fixed number
   of decimals (litres 3 dp, money 2 dp, exactly as the server sends them), generous row
   separators, sticky headers.
4. **Status is never colour alone.** Every status is colour + icon + word (for example
   "Low - 18%" with a down-arrow icon on amber). A tank gauge also prints its percentage.
5. **Every state is designed.** Loading (skeletons, not spinners that jump), empty (says what
   to do next), error (says what happened, what to try, with a Retry button), and
   permission-denied (explains who can do it).
6. **Hiding is not security.** Navigation and buttons are hidden or disabled by permission for
   clarity, but the server re-checks every call; a 403 is shown as a friendly message.
7. **Light and dark.** Follows the OS, can be forced from the top bar. Both meet WCAG 2.1 AA
   (4.5:1 text, 3:1 UI/graphics). Visible focus ring (3 px, never removed).

## Look
Not the stock "blue SaaS dashboard". A warm paper-and-ink base (off-white stone surfaces, near-
black green-tinted text) with a deep **spruce** primary and a **signal amber** reserved for
attention. The sidebar is a dark ink column so content reads as the bright "forecourt" beside
it. Numbers are the heroes: large tabular figures on stock gauges. Inter for text.

## Tokens (all CSS variables in `web/src/styles/tokens.css`)
- Colour: `--bg`, `--surface`, `--surface-2`, `--line`, `--text`, `--text-muted`, `--primary`,
  `--primary-contrast`, `--ok/--warn/--danger/--info` each with `-bg` and `-text`, `--focus`.
- Space (4 px base): `--space-1..8` = 4, 8, 12, 16, 24, 32, 48, 64.
- Type: `--text-xs..3xl` (12, 14, 16, 18, 22, 28, 36), line-heights 1.4-1.2, weights 400/500/600/700.
- Shape: `--radius-sm/md/lg` = 6 / 10 / 16; `--shadow-1/2`.
- Size: `--size-touch` 44 px, `--size-row` 40 px, `--sidebar-w` 248 px.
- Motion: 120-180 ms, disabled under `prefers-reduced-motion`.

## Offline
Fonts come from `@fontsource-variable/inter` (bundled), icons from `lucide-react` (bundled);
nothing is fetched from the internet. A build check fails if any external URL appears in the
output.
