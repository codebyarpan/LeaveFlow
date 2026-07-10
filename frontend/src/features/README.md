# `src/features/` — per-role surfaces

Empty in Story 1.1, and named in the spine's source tree, so it exists now.

One directory per role-facing surface, from Story 1.2 onward: `auth/`, `departments/`,
`employees/`, `leave-requests/`, `calendar/`, `dashboard/`.

Two rules bind everything that lands here:

- **AD-2** — no module under `src/` may reference a weekday or a Company Holiday. Every
  leave-day count comes from the server's preview endpoint, which returns the count, each
  excluded date with its reason and the holiday's name, and the projected Available
  balance. A client that recomputed the count would drift the moment the holiday calendar
  changed, and would be wrong in a way nobody noticed until someone lost a leave day.
- Features import the API through `src/api`, never by reaching into `src/api/client`.

React state shape below the page level is deliberately left unspecified by the spine.
