# LeaveFlow frontend

Vite + React 19 + TypeScript SPA, with TanStack Query and a typed API client.

See the [repository README](../README.md) for setup. Two rules are worth knowing before
you write anything here.

## TypeScript is pinned to 6.0.3, and that is not an accident

TypeScript 7.0.2 is the current latest, and `npm install typescript` will resolve to it.

7.x is the native Go port, and it *hard-removes* what 6.x only deprecated: `target: es5`,
AMD/UMD/SystemJS modules, and `moduleResolution: node10`. `6.0.3` is the last release of
the 6.x line — there is no 6.1.

Verify after any dependency change:

```bash
npx tsc --version   # must print 6.0.3
```

Every version in `package.json` is an exact pin, not a range. Image builds use `npm ci`,
never `npm install`.

## No module here may know what a weekend is

`AD-2`: `domain.calendar.count_leave_days` on the server is the only code in the system
that knows what a weekend or a Company Holiday is. Every day count the client displays
comes from the server's preview endpoint, which returns the count, each excluded date
with its reason and the holiday's name, and the projected Available balance.

A client that recomputed the count would drift the moment an Admin changed the holiday
calendar, and would be wrong in a way nobody noticed until someone lost a leave day.

## Layout

| Directory | Holds |
| --- | --- |
| `src/api/` | The typed client, the error envelope, TanStack Query hooks. |
| `src/features/` | Per-role surfaces, one directory each. Empty until Story 1.2. |
| `src/components/` | Components shared by two or more features. |

Styling approach and component library are **deferred by the spine**. `src/index.css` is
plain CSS on purpose; do not introduce a component library without a story that asks for
one.

## Commands

```bash
npm run dev      # Vite dev server; proxies /api/v1 to the TLS proxy, without a rewrite
npm run build    # tsc -b && vite build — a type error fails the build
npm run lint     # oxlint
```
