# Frontend: notes for Claude Code

## UX rules (from spec "UX — CORE")

- Phone and desktop both first-class; **phone breaks ties**. Bottom tabs on phone, collapsible sidebar on desktop.
- Plain words ("cupboard", "use soon", "tubs left"), never database words.
- Undo, not "Are you sure?" (two exceptions: signing out with unsent changes; removing a line from the shopping list, cabledrawer 20 Oct). Optimistic updates. One switch component for every on/off.
- Auto · Light · Dark switch always in plain sight. A designed dark theme, not inverted.
- Vertical scrolling only; no chunky scrollbars.
- Show connection status (offline bar with waiting changes; "Back online — all saved").
- WCAG AA in both themes; touch targets ≥ 44 px.

## Running the frontend tests

The unit tests run in headless Chromium. `./check` installs it for you. If you run `npm test` by hand in a fresh checkout, run this once first (`npm test` no longer does it):

```sh
cd frontend && npx playwright install chromium-headless-shell
```
