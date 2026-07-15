"""CLI entrypoint for the Leave Year rollover: `python -m app.jobs.rollover --year YYYY`.

Implements: AC2 (a CLI entrypoint, not a scheduler — invoked by an EXTERNAL scheduler; no scheduler
is registered inside the FastAPI application and no endpoint triggers it), AC9 (directly callable
from a test with no running server and no clock manipulation), AD-7, AD-1, NFR-15.

Mirrors the shape of `python -m seed`, the other CLI entrypoint the spine calls for — seed's own
module docstring says so. `configure_logging()`, `main() -> int`, typed exceptions → `logger.error`
→ `return 1`, `sys.exit(main())` at the bottom. An operator error exits with a sentence; an
UNANTICIPATED exception still tracebacks, and should — that is a bug here, not an operator mistake.

--- A thin shell over `services/`, and nothing more (AD-1, import-linter contract 7) ---

Contract 7 ("jobs/ never imports api/") says the job "orchestrates through `services/` like any
other entrypoint", and this file honours that literally: it parses `--year`, calls ONE service
function, and maps exceptions to an exit code. There is no SQL here, no `Session`, and no business
rule. `app.jobs` is deliberately absent from contract 1's layer list, so `jobs → services →
repositories → domain` is permitted exactly as written — and `pyproject.toml` therefore needs no
change (`tests/test_architecture.py` pins all seven contracts byte-for-byte and fails the build on
an addition, a rename or a loss).

--- Why `--year` is REQUIRED, and why that IS the AC9 guarantee ---

There is no `date.today()` in this file and there must not be one, not even to default the year.
Making the year a mandatory ARGUMENT is precisely what lets a test call the rollover with no clock
mocked anywhere: `run_rollover(2026)` is an ordinary function call. A job that defaulted its own
year would force every test to monkeypatch a clock, and AC9 would be untestable rather than
satisfied. The clock lives in the shell (AD-1) — and here, the shell is the operator's crontab.

The year it names must be a CLOSED Leave Year: `--year 2026` CLOSES 2026 and materializes 2027. The
scheduler owns that precondition; the job has no clock with which to police it.
"""

import argparse
import logging
import sys

from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from app.core.logging import configure_logging
from app.services.rollover import run_rollover

logger = logging.getLogger("rollover")

# A four-digit sanity range. Not a business rule — the Leave Year is simply the calendar year (DR-8),
# and no artifact bounds it — but `--year 20226` is a typo, not an instruction, and it should be
# refused with a sentence rather than quietly materializing balances twenty thousand years out.
_MIN_YEAR = 1000
_MAX_YEAR = 9999


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse `--year`, the one option. Required: there is no clock here to default it from (AC9)."""
    parser = argparse.ArgumentParser(
        prog="python -m app.jobs.rollover",
        description=(
            "Close a Leave Year and open the next one: carry forward what carries, lapse what "
            "lapses. --year names the year to CLOSE, so --year 2026 reads 2026's balances and "
            "materializes 2027's. Invoked by an external scheduler (AD-7), never by the server."
        ),
    )
    parser.add_argument(
        "--year",
        type=int,
        required=True,
        metavar="YYYY",
        help="The Leave Year to CLOSE (a four-digit calendar year). Must already be over.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the rollover for `--year`, returning a process exit status.

    Every anticipated failure exits `1` with a message legible as an operator mistake — "that year
    is not a year", "postgres is not up", "your .env is incomplete" — never a raw traceback. An
    unanticipated failure still tracebacks: it is a bug here, not an operator error.

    Calls `services.rollover.run_rollover(year)` and nothing else, then logs the summary it returns.
    """
    configure_logging()

    args = _parse_args(argv)

    if not _MIN_YEAR <= args.year <= _MAX_YEAR:
        logger.error(
            "--year %d is not a four-digit calendar year (expected %d–%d). The Leave Year is the "
            "calendar year (DR-8), and --year names the year to CLOSE.",
            args.year,
            _MIN_YEAR,
            _MAX_YEAR,
        )
        return 1

    try:
        summary = run_rollover(args.year)
    except OperationalError as unreachable:
        logger.error(
            "Cannot connect to the database: %s\nIs the stack running? `docker compose up -d`.",
            unreachable.orig,
        )
        return 1
    except ValidationError as invalid:
        logger.error(
            "Settings are incomplete or still placeholders — fix .env (see .env.example):\n%s",
            invalid,
        )
        return 1

    logger.info(
        "Rollover complete: Leave Year %d closed, %d opened. %d balance rows written "
        "(%d Employees × %d Leave Types); %d had no %d row and were materialized from zero; "
        "%d pairs refused and flagged for Admin review.",
        summary.leave_year,
        summary.next_leave_year,
        summary.balances_written,
        summary.employees,
        summary.leave_types,
        summary.missing_source_rows,
        summary.leave_year,
        summary.refused_pairs,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
