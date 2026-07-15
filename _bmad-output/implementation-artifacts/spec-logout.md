---
title: 'Logout — sign out and return to the login screen'
type: 'feature'
created: '2026-07-15'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: '36b321b59b735f718d93e4c44589307cf3233e79'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** An authenticated user has no way to sign out. Once the Bearer token is in the browser the only exits are token expiry or clearing storage by hand — a real gap on any shared machine, where the next person inherits the live session and its cached, per-user data.

**Approach:** Add an explicit "Log out" control to the app shell header. On click, tear the session down entirely on the client — clear the stored token (memory + `localStorage`) and drop the whole TanStack Query cache — then flip the app back to the login screen. No backend change: the auth is stateless JWT with no revocation list by design (NFR-02), so logout is a client-side clear and the token simply expires server-side per its `exp`.

## Boundaries & Constraints

**Always:**
- Reuse the existing teardown seam. Logout must produce the *same* end state as the `SESSION_EXPIRED_EVENT` sign-out already does: `setSessionToken(null)` + `queryClient.clear()`. Logout additionally calls `clearToken()` (the expiry path already cleared it in `client.ts`, so that call lives on the logout side).
- All session I/O stays behind `api/session.ts` (`clearToken`) — no direct `localStorage` calls in components.
- `queryClient.clear()` is mandatory on logout: no cache key carries a per-user identity, so a residual cache would leak the previous user's data to the next login on the same browser.
- The logout control lives in `.shell__header` as an additional flex child; use existing CSS variables and the established plain-CSS pattern.
- The button is a real `<button type="button">` with an accessible label ("Log out").

**Ask First:**
- Any server-side change (logout endpoint, token blocklist). Decided out of scope for this feature — do not add one.

**Never:**
- No backend endpoint, no token blocklist, no change to `resolve_actor`/`services/auth.py`/`core/security.py`.
- No router, no new navigation model — the token-presence gate in `App.tsx` stays the single switch.
- Do not overload `SESSION_EXPIRED_EVENT` for a deliberate logout by dispatching it; call the shared teardown directly instead.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Logout happy path | Signed-in user clicks "Log out" | Token cleared (memory + storage); full query cache cleared; `App` re-renders `LoginPage`; shell + all panels unmount | N/A |
| Storage write denied | Same, but `localStorage.removeItem` throws (private mode / blocked) | Memory token still cleared; user still returns to login screen | Swallowed inside `clearToken` (existing behavior); never crashes render |
| Request in flight at logout | A query fires after the token is null | Request goes out with no `Authorization` header → server answers `401 TOKEN_INVALID`; already-handled expiry path, single bounce, no loop | Existing `client.ts` handling |

</frozen-after-approval>

## Code Map

- `frontend/src/App.tsx` -- the token-presence gate and the existing `onSessionExpired` teardown; add the shared sign-out helper and pass a logout handler into `AppShell`, which renders the button.
- `frontend/src/api/session.ts` -- `clearToken()` already clears memory + `localStorage` defensively; reused as-is, no change.
- `frontend/src/index.css` -- `.shell__header` flex row; add a `.shell__logout` button style using existing variables.
- `frontend/vite.config.ts` -- add the vitest `test` block (jsdom env, setup file).
- `frontend/package.json` -- add vitest + testing-library dev deps and a `test` script.
- `frontend/tsconfig.app.json` -- keep the production `tsc -b` build green with test files present (exclude them or add test types).

## Tasks & Acceptance

**Execution:**
- [x] `frontend/src/App.tsx` -- Extract the state+cache teardown (`setSessionToken(null)` + `queryClient.clear()`) into a shared `signOut` callback used by both the `onSessionExpired` listener and a new `handleLogout` (which additionally calls `clearToken()`). Pass `onLogout={handleLogout}` into `AppShell` and render a "Log out" `<button>` in `.shell__header`.
- [x] `frontend/src/index.css` -- Add `.shell__logout` styled as a subtle bordered button consistent with the shell.
- [x] `frontend/vite.config.ts` -- Switch `defineConfig` import to `vitest/config`; add `test: { environment: 'jsdom', globals: true, setupFiles: [...] }`.
- [x] `frontend/src/test/setup.ts` -- New: import `@testing-library/jest-dom/vitest`; register `afterEach(cleanup)`.
- [x] `frontend/package.json` -- Add dev deps (`vitest`, `jsdom`, `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/dom`, `@testing-library/user-event`) and script `"test": "vitest run"`.
- [x] `frontend/tsconfig.app.json` -- Add `vitest/globals` to `types` so `tsc -b` stays green with the test files present; Vite bundles only from the entry, so the orphan test files are type-checked but never shipped.
- [x] `frontend/src/api/session.test.ts` -- New: unit-test `setToken`→`getToken`→`clearToken` (memory + storage key removed), including the storage-denied branch.
- [x] `frontend/src/App.test.tsx` -- New: render `App` with a token present and `/me` fetch mocked; assert the shell renders, click "Log out", assert `LoginPage` returns, the shell is gone, and the token is cleared.

**Acceptance Criteria:**
- Given a signed-in user viewing the shell, when they click "Log out", then the app shows the login screen and no shell panel remains mounted.
- Given a logout just occurred, when `getToken()` is read, then it returns `null` and the `leaveflow.token` `localStorage` key is absent.
- Given a logout just occurred, when a new user signs in on the same browser, then no query resolves from the previous user's cache (the cache was cleared).
- Given `npm run test` is run, then the session unit test and the App logout-flow test pass.
- Given `npm run build` and `npm run lint` are run, then both succeed with the new test files and config present.

## Design Notes

Shared teardown in `App` (both paths converge on this):

```tsx
const signOut = useCallback(() => {
  setSessionToken(null)
  queryClient.clear()
}, [])

// expiry: client.ts already called clearToken(), so just tear down state+cache
useEffect(() => {
  window.addEventListener(SESSION_EXPIRED_EVENT, signOut)
  return () => window.removeEventListener(SESSION_EXPIRED_EVENT, signOut)
}, [signOut])

// deliberate logout: clear the token here, then the shared teardown
const handleLogout = useCallback(() => {
  clearToken()
  signOut()
}, [signOut])
```

The App logout test must wrap in `QueryClientProvider` and mock the `/me` request (e.g. `vi.stubGlobal('fetch', ...)` returning a valid profile envelope) so `AppShell` mounts; then assert the login email field reappears after clicking "Log out".

## Verification

**Commands:**
- `cd frontend && npm install` -- expected: new dev deps resolve
- `cd frontend && npm run test` -- expected: all tests pass (session + App logout flow)
- `cd frontend && npm run lint` -- expected: oxlint clean
- `cd frontend && npm run build` -- expected: `tsc -b && vite build` succeed

## Suggested Review Order

**The teardown seam (the design's core)**

- Entry point: the shared `signOut` both paths converge on — flips the token gate, drops the whole cache.
  [`App.tsx:244`](../../frontend/src/App.tsx#L244)

- The deliberate-logout handler: clears the token FIRST (the expiry path had already), then the shared teardown.
  [`App.tsx:264`](../../frontend/src/App.tsx#L264)

- The reused store: `clearToken` forgets memory + `localStorage`, defensively. Reused unchanged.
  [`session.ts:84`](../../frontend/src/api/session.ts#L84)

**The UI control**

- The header button, wired to `onLogout`; `AppShell` now takes the handler as a prop.
  [`App.tsx:95`](../../frontend/src/App.tsx#L95)

- Subtle secondary styling — bordered, not colored, so it never competes with primary actions.
  [`index.css:69`](../../frontend/src/index.css#L69)

**Tests (the feature's justification: cross-user leak prevention)**

- Logout empties the cache (asserts the effect, not just that `clear()` fired) and forgets the token.
  [`App.test.tsx:83`](../../frontend/src/App.test.tsx#L83)

- Next user on the same browser sees only their own data — no trace of the previous user.
  [`App.test.tsx:108`](../../frontend/src/App.test.tsx#L108)

- The refactored server-driven expiry path also returns to login and empties the cache.
  [`App.test.tsx:128`](../../frontend/src/App.test.tsx#L128)

- The session store's memory-vs-storage split and both storage-denied branches.
  [`session.test.ts:1`](../../frontend/src/api/session.test.ts#L1)

**Test infrastructure (new to the repo)**

- Vitest config: jsdom env + setup file.
  [`vite.config.ts:39`](../../frontend/vite.config.ts#L39)

- Isolated test tsconfig so production typecheck neither compiles tests nor inherits test globals.
  [`tsconfig.test.json:1`](../../frontend/tsconfig.test.json#L1)
