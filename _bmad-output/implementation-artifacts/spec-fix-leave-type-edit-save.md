---
title: 'Fix the Leave Types edit Save button reading as a stuck loading state'
type: 'bugfix'
created: '2026-07-16'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: '592ad5185d9949436ea2e75696693470befef793'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** An Admin editing a Leave Type reports that Save "shows a loading symbol and can't be clicked, and doesn't save." The backend `PATCH /leave-types/{id}` is verified healthy (200 in ~30ms for name-only and balance-affecting edits). The real cause is the frontend: the Save button is *disabled* whenever `isPending || blocked || nothingChanged`, and the disabled style uses `cursor: progress` — a loading cursor — so a button that is merely waiting for the Admin to pick a Recalculate/Preserve disposition (or that has no changes yet) looks like a permanent hang, with no visible reason why it won't save.

**Approach:** Make a disabled control read as *disabled*, not *busy* — change the disabled-button cursor from `progress` to `not-allowed` — and add a short inline hint beside the Save button naming why it is disabled (choose a disposition / no changes yet). No backend change; the edit already works once the disposition is chosen.

## Boundaries & Constraints

**Always:** The server stays the guard — this is a usability fix layered on the existing `POLICY_DISPOSITION_REQUIRED` behavior, never a replacement for it (AC5/AC10). The disposition is still required for a balance-affecting edit; the button stays disabled until one is chosen. The genuine in-flight state keeps its own signal via the existing button label ("Saving…"/"Adding…"). Branch on the same `blocked`/`nothingChanged`/`isPending` values already computed in `EditPolicyForm` — do not recompute change-detection differently.

**Ask First:** Introducing any new loading-cursor mechanism (e.g. `aria-busy` plumbing across screens) beyond the label-based signal. Changing the disposition-gate semantics themselves.

**Never:** No backend/API/DB changes. No change to `changedFields`, `needsDisposition`, or the disposition-gate rules. No soft-delete/archive work — that is split to `deferred-work.md`. Do not add a spinner component or a component library.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Balance-affecting edit, no disposition | Admin changes `annual_entitlement`/carry-forward, disposition unset | Save disabled with `cursor: not-allowed`; hint reads that a Recalculate/Preserve choice is needed | N/A |
| Balance-affecting edit, disposition chosen | Same, then a disposition radio selected | Save enabled; clicking it PATCHes and closes the form | Server refusal → existing `editErrorMessage` line |
| Name-only edit | Admin changes only `name` | Save enabled immediately (no disposition, no hint) | N/A |
| No effective change | Form equals stored values (or reverted) | Save disabled with `cursor: not-allowed`; hint reads that no change has been made | N/A |
| Save in flight | Mutation `isPending` | Button shows "Saving…" and is disabled; no "why disabled" hint (it is working, not blocked) | N/A |

</frozen-after-approval>

## Code Map

- `frontend/src/index.css` -- lines 234, 279, 405: the three `…button:disabled` rules (`.login__submit`, `.dept-* / .dept-actions`, `.emp-form-actions / .emp-actions`) all set `cursor: progress`. The Leave Types Save/Cancel/Add buttons are styled by `.emp-form-actions button`.
- `frontend/src/features/leaveTypes/LeaveTypesPage.tsx` -- `EditPolicyForm` (from ~L490) computes `mustChoose`, `nothingChanged`, `blocked` and renders the Save button `disabled={isPending || blocked || nothingChanged}` inside `.emp-form-actions` with no adjacent reason.
- `frontend/src/App.test.tsx` -- reference pattern for a fetch-stubbed `@testing-library/react` + `vitest` test (stubFetch, QueryClientProvider render).

## Tasks & Acceptance

**Execution:**
- [x] `frontend/src/index.css` -- Change `cursor: progress` to `cursor: not-allowed` ONLY in the `.emp-form-actions / .emp-actions button:disabled` rule (the rule that styles the Leave Types edit Save button). The `.login__submit:disabled` and `.dept-* button:disabled` rules are left as `cursor: progress`: those buttons are disabled solely while a request is in flight, so `progress` is the correct cursor there — see Spec Change Log 2026-07-16.
- [x] `frontend/src/features/leaveTypes/LeaveTypesPage.tsx` -- In `EditPolicyForm`, render a short `muted` hint next to the Save button, shown only when the button is disabled for a *blocking* reason (i.e. `!isPending && (blocked || nothingChanged)`): `blocked` → "Choose Recalculate or Preserve above to save."; `nothingChanged` → "Make a change to save." -- directly answers "why won't it save?" for both disabled reasons without touching the gate logic. Do not show the hint while `isPending`.
- [x] `frontend/src/features/leaveTypes/LeaveTypesPage.test.tsx` -- New test (mirror `App.test.tsx`'s fetch stub) covering the I/O matrix rows: balance-affecting-without-disposition keeps Save disabled and shows the disposition hint; selecting a disposition enables Save; a name-only edit enables Save with no hint; a no-change form shows the "make a change" hint.

**Acceptance Criteria:**a
- Given an Admin has opened the edit form and changed a balance-affecting attribute without choosing a disposition, when they look at Save, then it is disabled with a `not-allowed` cursor and a visible hint tells them to choose Recalculate or Preserve.
- Given the Admin then selects a disposition, when they click Save, then the PATCH is sent and the form closes on success (unchanged from today's behavior).
- Given the Admin changes only the name, when the form renders, then Save is enabled immediately with no hint and no disposition prompt.
- Given no field differs from the stored Leave Type, when the form renders, then Save is disabled with a `not-allowed` cursor and a hint stating no change has been made.
- Given a save is in flight, when the button is disabled, then it reads "Saving…" and shows no "why disabled" hint.

## Spec Change Log

- **2026-07-16 (review — patch, no loopback).** Blind Hunter + Edge Case Hunter both flagged that changing `cursor: progress → not-allowed` on the shared `.login__submit:disabled` and `.dept-* button:disabled` rules is scope creep that mislabels genuine loading: those buttons are disabled ONLY while their request is in flight, so `progress` is the correct cursor there. **Amended:** narrowed the CSS change to the `.emp-form-actions / .emp-actions button:disabled` rule alone (the rule that styles the Leave Types edit Save button, the reported screen). Known-bad state avoided: unrelated Login/Departments screens showing a "forbidden" cursor while legitimately working. **KEEP:** the inline reason hint and its `!isPending && (blocked || nothingChanged)` guard (both reviewers judged the React logic sound); `not-allowed` on the `.emp-*` rule (correct for the edit Save button's validation-blocked state). **Deferred to human (Ask First):** fully distinguishing "loading" from "blocked" via `aria-busy`, so an in-flight `.emp-*` Save keeps a progress cursor — both reviewers' convergent recommendation, but the spec reserved the aria-busy mechanism as an Ask-First decision. Added a test covering the `!isPending` guard.

## Design Notes

The loading signal for a genuine save already exists — the button text flips to "Saving…" (and "Adding…" on create) — so removing the `progress` cursor loses no information; it only stops *non-loading* disabled buttons from impersonating a loading one. The hint reuses the existing `.muted` class and the `blocked`/`nothingChanged` booleans already in scope, so no new state or change-detection is added. The disposition explanation block above the radios stays as-is; the new hint is button-adjacent so the cause sits where the user is looking when Save won't respond.

## Verification

**Commands:**
- `cd frontend && npm run build` -- expected: `tsc -b && vite build` succeed with no type errors.
- `cd frontend && npm run lint` -- expected: oxlint clean.
- `cd frontend && npm run test` -- expected: the new `LeaveTypesPage.test.tsx` passes with the rest of the suite.

**Manual checks (if no CLI):**
- In the running app (proxy on https://localhost:8443, admin@example.com), open Leave Types → Edit policy on "Earned Leave", change Annual entitlement without picking a disposition: Save is greyed with a `not-allowed` cursor and the hint appears; pick Recalculate → Save enables and persists. Editing only the Name enables Save immediately.

## Suggested Review Order

**The fix — why Save "won't respond"**

- The reason hint: renders only when Save is blocking (not while saving); `blocked`/`nothingChanged` are mutually exclusive.
  [`LeaveTypesPage.tsx:628`](../../frontend/src/features/leaveTypes/LeaveTypesPage.tsx#L628)

- Disabled = "not allowed," not "busy": scoped to the `.emp-*` rule only (login/dept stay `progress` — they disable solely while loading).
  [`index.css:405`](../../frontend/src/index.css#L405)

**Verification**

- Balance-affecting-without-disposition keeps Save disabled + shows the disposition hint.
  [`LeaveTypesPage.test.tsx:127`](../../frontend/src/features/leaveTypes/LeaveTypesPage.test.tsx#L127)

- The one non-obvious branch: the hint stays hidden while a save is in flight.
  [`LeaveTypesPage.test.tsx:155`](../../frontend/src/features/leaveTypes/LeaveTypesPage.test.tsx#L155)
