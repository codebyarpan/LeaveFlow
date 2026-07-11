# Deferred Work

## Deferred from: code review of 1-1-project-foundation-and-reproducible-setup (2026-07-10)

- `configure_logging()` runs as an import side effect of `app.main` ([backend/app/main.py:24](../../backend/app/main.py)), replacing the root logger's handlers for any process that imports the module — pytest included (`tests/test_health.py` imports `app.main` at collection). Low consequence today; revisit if `caplog`-based tests arrive or if a host application ever embeds the app. Candidate fix: move configuration behind an app factory or uvicorn `log_config`.
- A top-level pip package literally named `seed` is installed into site-packages (`include = ["app*", "seed*"]` in [backend/pyproject.toml:54](../../backend/pyproject.toml)), and the api image keeps a duplicate source copy at `/srv` on `sys.path` alongside the installed one. `seed` is a collision-prone module name and two copies of a package on `sys.path` is an ambiguity waiting for a symptom — but the story's prescribed source tree fixes `backend/seed/`, so renaming is a spec change, not a patch.

## Deferred from: code review of 1-5-manage-departments (2026-07-11)

- **Enveloped server-side validation for department `name` (and free-text writes generally).** Empty/whitespace names are currently accepted (`POST/PATCH /departments {"name": ""}`), violating the server-as-guard invariant (NFR-03). Blocked on an architecture decision: how validation failures are enveloped in the NFR-17 `{code,message,details}` contract (new vocabulary code + status mapping), since a raw pydantic 422 bypasses it. This is the first free-text write; the convention set here will apply to every later validated field. [backend/app/api/v1/departments.py, backend/app/services/departments.py]
- **Pagination controls for the Departments UI.** The backend pagination convention is fully built (bound 50/100), but the frontend requests only the first page and renders no next/prev controls, so departments past the first page are unmanageable via the UI. Deferred until a real >50-department need appears. [frontend/src/api/departments.ts, frontend/src/features/departments/DepartmentsPage.tsx]
