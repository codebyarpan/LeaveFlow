"""The reusable page bound and the wire envelope every list endpoint carries.

Implements: NFR-11 (every list endpoint enforces a server-side maximum page size), the
spine's *Pagination* convention, api-contracts §1 (the `items`, `page`, `page_size`,
`total` envelope; "a client asking for more receives the maximum, not the larger page").

--- Why this lives here, and why it is a module rather than an inlined route helper ---

This is Epic 1's FIRST list endpoint (Story 1.5's `GET /departments`), so it *establishes*
the pagination convention Stories 1.6, 2.7 and 3.1 reuse verbatim. Building it as a shared
module — the `PageParams` dependency and the generic `Page[T]` response model — is what
makes "one server-side maximum, chosen once" true for every later list rather than a
number re-typed per route and free to drift.

Query params and the wire envelope are an `api/` concern, so this module belongs in `api/`
and imports `fastapi`/`pydantic` only — nothing lower (AD-1). It computes and carries the
`limit`/`offset`; the `LIMIT`/`OFFSET` themselves are issued in `repositories/`.

--- Why the number is chosen HERE ---

The spine and api-contracts fix the *convention* and the *envelope* but no numeric maximum
(ARCHITECTURE-SPINE.md *Consistency Conventions*: "the pagination bound is fixed here" —
the bound, not the number). So the number is chosen once, in this module, and inherited.
"""

from typing import Annotated, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel

# The page bound, chosen once for every list endpoint (Trap 2). `DEFAULT_PAGE_SIZE` is what
# an unbounded request receives; `MAX_PAGE_SIZE` is the ceiling a client can never exceed —
# a larger `page_size` is CLAMPED to it, never rejected (AC3). Change these and every list
# endpoint's bound changes with them; that is the point of one home.
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100

# The `page` ceiling (Story 3.1, adopting deferred-work.md:58 by name): an astronomically
# large `page` would compute an `offset` beyond PostgreSQL's bigint OFFSET range and 500.
# Clamped downward like everything else here — never a 422; the clamped page is simply an
# empty page far past the data. 1,000,000 pages × the max size is orders of magnitude past
# NFR-10 scale while keeping `offset` comfortably inside bigint.
MAX_PAGE = 1_000_000

T = TypeVar("T")


class PageParams:
    """Parse and clamp the `page`/`page_size` query params into a `limit`/`offset`.

    A class-based FastAPI dependency: a route declares `params: PageParams = Depends()` and
    reads `params.limit` / `params.offset` to page a query, and `params.page` /
    `params.page_size` to echo back into the `Page` envelope.

    The clamp is done in code, NOT with `Query(le=MAX_PAGE_SIZE)`: `le` would make an
    over-max value a `422` rejection, but AC3 requires it to be *carried down to the
    maximum*, silently. `page < 1` and `page_size < 1` coerce to their minimum of 1 rather
    than erroring — a nonsensical page request degrades to the first page, it does not fail.

    The query params are declared with `Annotated[int, Query(...)]` and a REAL int default,
    not `= Query(default=...)`: the annotated form leaves the parameter's runtime default a
    plain `int`, so this class is directly constructable in a DB-free unit test
    (`PageParams(page=2, page_size=200)`) while FastAPI still reads the `Query` metadata
    from the annotation. The bare `= Query(...)` form would leave the default a `Query`
    marker object, unusable outside a request.
    """

    def __init__(
        self,
        page: Annotated[
            int,
            Query(description="1-based page number. A value below 1 is treated as 1."),
        ] = 1,
        page_size: Annotated[
            int,
            Query(
                description=(
                    "Rows per page. Clamped to the server maximum "
                    f"({MAX_PAGE_SIZE}); a larger value receives the maximum, not a 422."
                ),
            ),
        ] = DEFAULT_PAGE_SIZE,
    ) -> None:
        # `max(_, 1)` coerces a below-minimum value up to 1; `min(_, MAX)` clamps the page
        # size down to the ceiling. Order matters only in that both bounds are applied.
        self.page = min(max(page, 1), MAX_PAGE)
        self.page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
        self.limit = self.page_size
        self.offset = (self.page - 1) * self.page_size


class Page(BaseModel, Generic[T]):
    """The list envelope every paginated endpoint returns — exactly the four AC3 names.

    Parameterized per endpoint (`Page[DepartmentResponse]`) so the OpenAPI schema — the
    runtime source of truth per api-contracts §5 — names the item type precisely rather
    than an opaque object. `items` is the page of rows; `page`/`page_size` echo the
    (clamped) request so a client knows what it actually received; `total` is the full
    count across all pages, which is what lets a client compute how many pages exist.
    """

    items: list[T]
    page: int
    page_size: int
    total: int
