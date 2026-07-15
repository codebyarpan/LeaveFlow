"""The page bound is enforced in `PageParams`, and it clamps rather than rejects.

Implements the test side of: AC3 (a `page_size` above the server maximum "carries the
server maximum, not the larger page"), NFR-11 (a bounded result set). DB-free: `PageParams`
is a pure parse/clamp over two integers, so this pins the convention without a database —
the integration test (`test_departments.py`) proves the same clamp end-to-end through the
`Page` envelope.

This is the cheaper of the two AC3 proofs, and the one that pins the *number*: if a future
story raised `MAX_PAGE_SIZE`, this test would move with it, and every later list endpoint
inherits the clamp these assertions describe.
"""

from app.api.v1.pagination import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE,
    MAX_PAGE_SIZE,
    Page,
    PageParams,
)


def test_a_page_size_above_the_maximum_is_clamped_not_rejected() -> None:
    """AC3: `page_size` larger than the server maximum carries the maximum, silently."""
    params = PageParams(page=1, page_size=MAX_PAGE_SIZE + 500)

    assert params.page_size == MAX_PAGE_SIZE
    assert params.limit == MAX_PAGE_SIZE


def test_a_page_size_at_or_below_the_maximum_is_preserved() -> None:
    """A request within the bound is carried unchanged — the clamp only bites above the max."""
    params = PageParams(page=1, page_size=25)

    assert params.page_size == 25
    assert params.limit == 25


def test_the_default_page_size_is_the_server_default() -> None:
    """An omitted `page_size` receives `DEFAULT_PAGE_SIZE`, not the maximum."""
    params = PageParams()

    assert params.page_size == DEFAULT_PAGE_SIZE
    assert params.page == 1
    assert params.offset == 0


def test_a_below_minimum_page_coerces_to_the_first_page() -> None:
    """`page < 1` degrades to page 1 rather than erroring (Trap 2)."""
    params = PageParams(page=0, page_size=DEFAULT_PAGE_SIZE)
    assert params.page == 1

    negative = PageParams(page=-5, page_size=DEFAULT_PAGE_SIZE)
    assert negative.page == 1


def test_a_below_minimum_page_size_coerces_to_one() -> None:
    """`page_size < 1` coerces to the minimum of 1, never a 422."""
    assert PageParams(page=1, page_size=0).page_size == 1
    assert PageParams(page=1, page_size=-10).page_size == 1


def test_an_unbounded_page_is_clamped_never_a_bigint_offset() -> None:
    """Story 3.1 (deferred-work.md:58): an absurd `page` clamps to `MAX_PAGE`, never a 500.

    Without the clamp, `page=10**18` computes an `offset` past PostgreSQL's bigint OFFSET
    range — a raw 500 for any authenticated caller. Clamped downward like `page_size`
    (never a 422), the request degrades to a far-off empty page.
    """
    params = PageParams(page=10**18, page_size=MAX_PAGE_SIZE)

    assert params.page == MAX_PAGE
    assert params.offset == (MAX_PAGE - 1) * MAX_PAGE_SIZE
    # The clamped offset stays far inside bigint (2**63 - 1).
    assert params.offset < 2**63 - 1

    # At or below the ceiling is preserved unchanged.
    assert PageParams(page=MAX_PAGE, page_size=1).page == MAX_PAGE
    assert PageParams(page=MAX_PAGE - 1, page_size=1).page == MAX_PAGE - 1


def test_offset_is_computed_from_the_clamped_page_and_size() -> None:
    """`offset = (page - 1) * page_size`, over the CLAMPED values, so the SQL page is stable."""
    params = PageParams(page=3, page_size=20)
    assert params.offset == 40
    assert params.limit == 20

    # The offset uses the clamped size, not the requested one: page 2 of an over-max
    # request steps by the maximum, not the larger number the client asked for.
    clamped = PageParams(page=2, page_size=MAX_PAGE_SIZE + 1)
    assert clamped.page_size == MAX_PAGE_SIZE
    assert clamped.offset == MAX_PAGE_SIZE


def test_page_envelope_carries_exactly_the_four_contract_fields() -> None:
    """AC3: the response body carries `items`, `page`, `page_size` and `total` — no more."""
    page: Page[int] = Page(items=[1, 2, 3], page=1, page_size=50, total=3)

    assert set(page.model_dump()) == {"items", "page", "page_size", "total"}
    assert page.items == [1, 2, 3]
    assert page.total == 3
