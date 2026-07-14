"""AC2: the rollover is a CLI entrypoint — no endpoint triggers it, no scheduler runs it.

Implements the test side of: AC2 / AD-7 ("The rollover is a CLI entrypoint, `python -m
app.jobs.rollover --year YYYY`, invoked by an external scheduler. No scheduler is registered inside
the FastAPI application.").

--- Why this file exists at all ---

Every other invariant in this codebase has a MECHANICAL guard — `test_architecture.py` (the import
contracts), `test_scope_matrix.py`, `test_scoped_getters.py`, `test_migrations_insert_nothing.py`.
AC2 had none: "no scheduler, no endpoint" was enforced by nothing but the developer's good
intentions and a reviewer's eye. So it gets one, and it is two asserts.

The failure it is built to catch is not this story's — it is the NEXT story's. A dev who adds an
`@app.on_event("startup")` hook, or a well-meaning `POST /rollover` "so Admins can trigger it from
the UI", breaks AD-7 in a way no existing test notices: under `uvicorn --workers 4` an in-process
scheduler fires the job FOUR times, and the double-run is silent because the rollover is idempotent
on the balances but appends a second `rollover_run` row per worker. This file fails the build first.

DB-free: it imports the app object and reads its router. No fixture, no server, no clock (AC9).
"""

from app.main import app


def test_no_endpoint_triggers_the_rollover() -> None:
    """No route anywhere in the application mentions the rollover (AC2, AD-7).

    The rollover is invoked by cron, not by a request. There is no `POST /rollover`, no
    `/rollover-runs` read surface (Open Decision #5 — no AC asks to read the table), and nothing in
    the scope matrix for either.

    Enumeration reads `app.openapi()["paths"]`, not `app.routes`, for the reason
    `tests/test_scope_matrix.py` already documents: under the pinned FastAPI an
    `include_router(prefix=...)` leaves `app.routes` holding a single opaque `_IncludedRouter` whose
    nested routes are not exposed there. The OpenAPI schema is the app's real, complete path list —
    and it is what a client would see, which is the right thing to assert "there is no endpoint"
    against.
    """
    paths = list(app.openapi()["paths"])

    offenders = [path for path in paths if "rollover" in path.lower()]

    assert offenders == [], (
        "The rollover must have NO HTTP surface (AC2, AD-7): it is a CLI entrypoint invoked by an "
        f"external scheduler. Found route(s): {offenders}. If a read surface for `rollover_run` is "
        "genuinely wanted, it is a follow-up story with a scope-matrix row — not an endpoint added "
        "here."
    )


def test_no_scheduler_is_registered_inside_the_application() -> None:
    """The app registers no startup or shutdown hook — so nothing schedules the job in-process.

    AD-7's reason is concrete: under `uvicorn --workers 4`, an in-process scheduler would fire the
    rollover once per worker. A CLI job invoked by an external scheduler runs exactly once, and is
    directly callable from a test with no running server (AC9, NFR-15).

    Asserting the hook lists are EMPTY — rather than merely "contain no rollover" — is deliberate:
    the moment this application grows its first startup hook, whoever adds it must come here and
    justify it against AD-7. That is the conversation this assert is for.
    """
    assert list(app.router.on_startup) == [], (
        "No startup hook may be registered (AD-7): under `uvicorn --workers 4` an in-process "
        "scheduler fires the rollover once per worker. The rollover is `python -m app.jobs.rollover "
        "--year YYYY`, invoked by cron."
    )
    assert list(app.router.on_shutdown) == [], (
        "No shutdown hook may be registered (AD-7) — same reason as the startup hook above."
    )
