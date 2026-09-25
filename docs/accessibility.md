# Accessibility audit (Phase 9)

Winnow aims for WCAG 2.2 AA (guide section 14). This is the audit behind that claim:
how it is run, what it found, and what is still open.

## How it is checked

`e2e/tests/a11y.spec.ts` builds a fixture review with something on every page and visits
all of them. The review holds imported records, a duplicate pair, a screening conflict,
full texts to screen, and an extraction form with two different extractions; its owner
is an instance admin.

**What it visits: 43 stops.**

- 6 signed-out pages: sign in, create an account, forgot password, reset password,
  confirm email, invitation.
- 37 signed-in stops: every workspace, admin, review, report, extraction, risk-of-bias
  and settings page, a single record, a single conflict, a single study, the "page not
  found" page, and the command palette and notification menu while open.

**Each stop runs at the four breakpoints the guide names, in light and dark.** 360 and
768 px run as touch screens; 1024 and 1440 px run with a mouse.

| Check | Where | Passes when |
| --- | --- | --- |
| axe-core: WCAG 2.0, 2.1 and 2.2 A/AA rules, plus axe's best practices | every stop, both themes | no serious or critical violation |
| Nothing scrolls sideways | 360 px | the page is no wider than the screen (scroll areas excepted) |
| Touch targets | 360 and 768 px | every control's hit area is at least 44 × 44 px |
| Focus is visible | 1440 px | Tab reaches up to 60 controls per page, and each shows an outline or ring |
| Reduced motion | sign-in page | with `prefers-reduced-motion: reduce`, nothing transitions or animates |

Findings of every impact are collected before anything is asserted, so a failing run
lists every problem at once. To write the findings as JSON as well:

```bash
cd e2e && A11Y_REPORT=/tmp/a11y pnpm exec playwright test tests/a11y.spec.ts --project=desktop
```

Other checks cover what the sweep does not:

- The journey specs run axe at the steps they reach, such as a decision just made or a
  dialog open.
- `features/screening/screening.test.tsx` checks the screen-reader announcement after
  each decision ("Included. Next record: …").

## Result

All four breakpoints pass: zero serious or critical axe violations, no sideways
scrolling, no small touch targets, and no focus without an indicator. One finding
remains, of moderate impact and accepted (see below).

## Found and fixed

| Problem | Where | Fix |
| --- | --- | --- |
| Text below 4.5:1 contrast (teal on a teal tint) | New review: the current step | Normal text colour; a solid primary border marks the step |
| A link told apart only by colour | Screening: the "N conflicts" link | Always underlined |
| Focus shown only as a faint tint | Records: the list's rows | The same focus ring as every other control |
| The home link outside any landmark | Sidebar | The whole sidebar is the "Main" navigation landmark |
| Tables that scroll sideways but cannot be reached by keyboard | Statistics, extraction table fields, consensus, form preview | `ScrollRegion`: a named, focusable region that the arrow keys scroll |
| Controls 28–40 px tall on touch screens, icon buttons 32–36 px wide | Almost every page | Every control is at least 44 × 44 px on a coarse pointer. Checkboxes and switches keep their look and get a 44 px hit area. Labels around native checkboxes and radios are 44 px tall |
| The sidebar's edge rail, 16 px wide | Every page on a tablet | Hidden on touch screens, where the menu button does the same job |
| The invite email field squeezed to 36 px wide | Settings → Team, at tablet width | The form uses two columns until the screen is wide enough for three |
| Rows wider than the screen | Settings → Exclusion reasons at 360 px | Rows wrap, and the move and delete buttons get a line of their own |
| A 13 px radio button with its text beside it | Duplicates: "Keep this one" | The whole column heading is its label |
| A table's scroll area counted as disabled | Extraction form preview | Its controls are disabled one by one, not through the fieldset |

The audit also found a bug unrelated to accessibility. The admin health page counted
only the records of reviews the admin belongs to. It now counts every review's records
(see `docs/decisions.md`).

## Accepted

- **Open menus sit outside the page's landmarks.** This is axe's `region` rule, of
  moderate impact and a best practice, not a WCAG requirement. Radix renders menus at
  the end of the page so that they are never clipped, and focus moves into a menu when
  it opens, so keyboard and screen-reader users land in it. Rendering menus inside the
  header instead would misplace them, because the header's backdrop blur changes how
  fixed-position elements are placed.

## Not covered yet

- **Only Chromium is automated.** Firefox and WebKit are not.
- **No screen reader has been run.** Neither VoiceOver nor NVDA has been used on the
  whole journey. Automated checks cannot judge whether announcements make sense in
  order. A manual pass is due before launch: sign in, import, screen ten records,
  resolve a conflict, export.
- **Contrast is measured, never judged.** axe cannot measure text over images, such as
  the PRISMA diagram and the risk-of-bias plots, which the server draws. Their colours
  come from the same palette.
