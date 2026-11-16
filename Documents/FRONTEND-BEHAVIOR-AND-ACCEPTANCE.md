# Frontend Behavior And Acceptance

> **Later frozen state:** [TRD-4](./TRD-4.md) records the current UI cleanup, direct actions, restoration and notification clearing. This file is the dated October 15 behavior checkpoint; do not restore old standing notices or consent checkboxes from it.

Current implementation reference — 2026-10-15. Historical TRDs retain their dated
requirements/design status. This document describes the implemented console;
it does not establish enterprise authentication or production assurance.

## Reports And Findings

- History combines browser summaries, browser-saved SocMate references and eligible
  API ChatMate results. Selection order is independent of preview navigation and
  filtering. A combined management report needs two distinct selections.
- Remove controls use accessible confirmations, pending locks and error feedback.
  Summary removal retains assessment/findings and its recreation tombstone.
  SocMate removal retains server evidence. ChatMate explicitly offers permanent
  **Delete source run** through the existing API, which rejects active/unresolved
  workers. It is not report-only deletion.
- Removal prunes affected selections/previews without resetting unrelated filters,
  query parameters or reports. History owns the single unselected/empty state;
  there is no redundant preview banner.
- ChatMate Findings expands the selected run's validated details immediately below
  that row. Enter/Space, expanded/control/region relationships, query selection,
  close/reopen focus and stale-response protection are retained.

## Notification Contract

- Only run-start and run-end events are emitted. Queue/progress/selection/manual
  waiting/evaluation phases and Critic activity do not generate extra events.
  Never-started drafts do not invent starts. Outcomes distinguish failure,
  completion, rejection, abandonment, cancellation and timeout as supported.
- IDs are `<source>:<encoded-run-id>:run:start|end`; updates replace the same event.
  Sort globally by source timestamps, latest first; absent terminal dates are
  explicitly unknown instead of fabricated from creation/refresh time.
- Visible-page polling is nonoverlapping: 3 seconds with active runs, 5 otherwise.
  Panel opening, navigation, focus/visibility, reconnect and local/storage events
  trigger refresh. API history reads abort after 10 seconds.
- Validate every row before authoritative cache replacement: identity, lifecycle,
  presentation fields and optional verdict/date/availability types. A malformed or
  unavailable source preserves its last good snapshot with an error; other sources
  refresh independently. A valid empty source clears its old entries. Legacy
  phantom `undefined`/`null` events are excluded.
- Snapshots use `secmate.notifications.history.v2:<user>:<source>`. Existing
  `secmate.notifications.read.v1:<user>` IDs remain compatible; per-event receipts
  reduce cross-tab read-write losses. Mark all reads only current displayed events.
- Persistence is browser/origin-local per normalized user, not account/server or
  cross-device persistence. API histories request up to 500 runs/source; source
  snapshots/merged feed are bounded to 1,000 events and read-ID arrays to 5,000.
  This is not a permanent notification archive or authorization boundary.
- The list scrolls inside a viewport-bounded panel, with a persistent Mark all read
  footer and keyboard focus/dismissal behavior. A polite atomic live region updates
  unread counts without changing its text on unchanged polling results.

## Route Loading And Diagnostics

ChatMate, module pages and Settings load lazily. The shell remains usable while
page content loads or fails. Reload performs a real document reload so a previously
rejected lazy module can be fetched again; navigation away remains available.

`PageBoundary` also contains descendant render failures. It dispatches the local
`secmate:page-error` CustomEvent with `{code, route}` only: `CHUNK_LOAD` or
`PAGE_RENDER` and an allowlisted pathname. Bounded cause inspection supports wrapped
import failures. Exception text, stacks, chunk URLs and query/evidence values are
not emitted. This event is an integration point, not a server monitoring service.

## Verification And Remaining Acceptance

- Frontend full suite: **385 tests / 28 files**; TypeScript/Vite build passed.
  Main emitted JS is 286.44 kB minified; shared/deferred chunks are additional assets.
- Chrome fixture-backed desktop/mobile/keyboard checks passed for removal,
  disclosure, notification polling/read/reload/footer and source isolation.
- Production-preview chunk interception proved actual failure/fallback/reload
  recovery; a real descendant exception proved safe diagnostic events.
- Scoped WCAG 2/2.1 A/AA axe scans found zero violations in the removal dialog,
  report history, inline Findings and notification panel. These are scoped automated
  results, not full application WCAG certification or screen-reader acceptance.
- **Open:** a human must test NVDA/Narrator with Findings expansion, removal-dialog
  naming/focus/busy/error behavior and notification announcements/footer/read/Escape
  behavior, recording tool/browser versions and observed results.
- Browser scripts/screenshots were generated outside the repository in the approved
  temporary work directory; they are not a committed browser test harness. Unit
  regressions live in `apps/web/src/*test.tsx` and `notificationService.test.ts`.

Read the [ChatMate workflow](./CHATMATE-WORKFLOW-PRODUCT-INTEGRATION.md),
[current handoff](./TRD-4.md) and [API operations](./TRD-4.md#safe-agent-procedures) for evidence
and durable execution boundaries.
