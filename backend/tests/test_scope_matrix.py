"""The SM-3 coverage matrix: every identifier endpoint declares a scope, or the build fails.

Story 1.7's unique deliverable (AC4). This is the *harness* for `SM-3`, not its satisfaction.

SM-3 (PRD §8, verbatim): "Authorization is scoped to data, not to role. Target: for every
endpoint accepting a Leave Request identifier, an authenticated Manager who is not the
applicant's Manager receives the same response as for a nonexistent request. Zero endpoints
authorize on role name alone. Validates FR-03, DR-12."

No Leave Request table exists in Epic 1, so the *satisfaction* of SM-3 — the byte-identical-404
assertions for a non-report's Leave Request — lands in Epic 2. What this story builds is the
completeness gate: an explicit registry mapping every endpoint that accepts a resource
identifier to the scope(s) api-contracts §4 grants it, plus an assertion that EVERY such
endpoint the app actually exposes is in the registry. So an identifier endpoint added by a
later story but never given a scope fails this test with a message naming the offending
`(method, path)` — which is precisely epics.md line 837's "builds the harness and registers
Epic 1's endpoints; it does not claim to satisfy SM-3, which Epic 2 does."

--- Why it is modelled on the existing armed guardrails, not written from scratch ---

- Registry-plus-completeness shape → `tests/test_scoped_getters.py` (an explicit registry, a
  per-item parametrized test, and a vacuity guard `test_there_are_getters_to_inspect`).
- "Guard the guard" → `tests/test_architecture.py`'s
  `test_every_contract_in_pyproject_is_actually_exercised` (a registry silently emptied — or
  carrying a stale entry — must itself fail, or the completeness check is a false green).

--- "Accepts a resource identifier" ---

The path template carries a path parameter (`{...}`). `/me`, `/auth/*`, `/health`, and the
collection `GET`/`POST` on `/employees` and `/departments` carry no path parameter and are out
of the matrix. The five Epic 1 identifier endpoints are registered below, all scope `all`
(api-contracts §4.2 grants every `/employees` and the `/departments/{id}` writes to the Admin
alone). The registry VALUE is a `frozenset[Scope]` because §4 grants some endpoints more than
one scope by role (Epic 2's `GET /leave-requests/<id>` is `self, reports, all`); keeping it a
set now means Epic 2 extends values without reshaping the registry.

DB-free: it introspects the constructed app object only — no connection. `import app.main` is
what constructs the app and registers every route; without it `app.main.app.openapi()` would be
missing the routes this test exists to enumerate (Story 1.4 review finding: three domain tests
were false-green for want of this import).

Enumeration reads `app.openapi()["paths"]` rather than iterating `app.routes`. Under the pinned
FastAPI (0.139.0) an `include_router(prefix=...)` leaves `app.routes` holding a single opaque
`_IncludedRouter` whose nested `APIRoute`s are not exposed there, so `app.routes` enumerates
nothing — the generated OpenAPI is the reliable source of routed operations, already
prefix-resolved and with `HEAD`/`OPTIONS` excluded. It is the same source `test_employees.py`
(AC12's no-`delete` check) reads, kept consistent here.
"""

import pytest

import app.main  # noqa: F401 — constructs the app so every route is registered before enumeration
from app.repositories.scoping import Scope

# The v1 prefix every contracted path lives under; a path outside it is framework plumbing.
_API_PREFIX = "/api/v1"

# The HTTP verbs an OpenAPI path-item object may carry as operations. A path-item can also hold
# non-operation keys (`parameters`, `summary`, `description`); filtering against this set keeps
# those out of the enumerated operations. `HEAD`/`OPTIONS` are absent by design — FastAPI's
# generated schema does not emit them, so no explicit exclusion is needed.
_HTTP_METHODS = frozenset({"GET", "PUT", "POST", "DELETE", "PATCH", "TRACE"})

# The SM-3 scope registry: each identifier operation → the scope(s) api-contracts §4 grants it.
#
# Epic 1's five identifier endpoints, all scope `all` — §4.2 grants every `/employees` endpoint
# and the two `/departments/{id}` writes to the Admin alone, whose scope genuinely IS everyone.
# Epic 2 EXTENDS this registry with the Leave Request endpoints where SM-3 is actually
# *satisfied*: `GET /leave-requests/{id}` (`self, reports, all`), the approve/reject/cancel
# transitions (`reports`), and `GET /employees/{id}/balances` (`reports`, FR-07). A value is a
# frozenset because those Epic 2 endpoints grant more than one scope by role — Epic 1's are all
# single-element, but the shape is set from the start so Epic 2 adds values, not structure.
_SCOPE_REGISTRY: dict[tuple[str, str], frozenset[Scope]] = {
    ("GET", "/api/v1/employees/{employee_id}"): frozenset({Scope.ALL}),
    ("PATCH", "/api/v1/employees/{employee_id}"): frozenset({Scope.ALL}),
    ("POST", "/api/v1/employees/{employee_id}/deactivate"): frozenset({Scope.ALL}),
    ("PATCH", "/api/v1/departments/{department_id}"): frozenset({Scope.ALL}),
    ("DELETE", "/api/v1/departments/{department_id}"): frozenset({Scope.ALL}),
    # Story 2.2 — the holiday calendar is organization-wide (FR-10, scope `all`): §4.3 grants
    # `DELETE /holidays/{id}` to the Admin alone, whose scope genuinely IS everyone. Like the
    # `/departments/{id}` writes, this is `all`, not a per-Employee scope. (`POST`/`GET
    # /holidays` carry no path parameter, so they are out of the matrix.)
    ("DELETE", "/api/v1/holidays/{holiday_id}"): frozenset({Scope.ALL}),
    # Story 2.4 — the FIRST multi-scope entry (every Epic 1 entry above is a single `{Scope.ALL}`).
    # `GET /employees/{id}/balances` is granted to an Admin (scope `all` — anyone) AND a Manager
    # (scope `reports` — their Direct Reports only), api-contracts §4.4 / FR-07. `leave_balance`
    # is the first genuinely data-scoped resource, so a Manager naming a non-report gets a
    # byte-identical 404 (AD-10). (`GET /balances` has no path parameter → out of the matrix,
    # like `/me`.)
    ("GET", "/api/v1/employees/{employee_id}/balances"): frozenset(
        {Scope.REPORTS, Scope.ALL}
    ),
    # Story 2.7 — the four Leave Request identifier endpoints where SM-3 is first *satisfied* (the
    # integration suite proves the byte-identical 404). `GET /leave-requests/{id}` is granted to
    # every role by its own scope (Employee `self`, Manager `reports`, Admin `all`, api-contracts
    # §4.5); approve/reject are the Manager's alone (`reports`); cancel is the applicant's own
    # (`self`). (`GET /leave-requests`, `POST /leave-requests`, `POST /leave-requests/preview` carry
    # no path parameter → out of the matrix.)
    ("GET", "/api/v1/leave-requests/{request_id}"): frozenset(
        {Scope.SELF, Scope.REPORTS, Scope.ALL}
    ),
    ("POST", "/api/v1/leave-requests/{request_id}/approve"): frozenset({Scope.REPORTS}),
    ("POST", "/api/v1/leave-requests/{request_id}/reject"): frozenset({Scope.REPORTS}),
    ("POST", "/api/v1/leave-requests/{request_id}/cancel"): frozenset({Scope.SELF}),
}


def _identifier_operations() -> set[tuple[str, str]]:
    """Every `(METHOD, path_template)` the app exposes that accepts a resource identifier.

    An operation is in scope for the matrix iff its path is under `/api/v1` and its template
    carries a path parameter (`{...}`). Each path-item's operation verbs are expanded into one
    `(METHOD, path)` per verb (upper-cased; non-operation path-item keys filtered out). Read
    off `app.openapi()["paths"]`, the reliable routed-operation source under the pinned FastAPI
    (see the module docstring) — what OpenAPI documents as an operation is what is routed, which
    is what authorization actually guards.
    """
    operations: set[tuple[str, str]] = set()
    for path, path_item in app.main.app.openapi()["paths"].items():
        if path != _API_PREFIX and not path.startswith(_API_PREFIX + "/"):
            continue  # segment-boundary match so `/api/v10`/`/api/v1beta` never leak in
        if "{" not in path:  # no path parameter → not an identifier endpoint
            continue
        for method in path_item:
            if method.upper() in _HTTP_METHODS:
                operations.add((method.upper(), path))
    return operations


def test_there_are_identifier_operations_to_inspect() -> None:
    """Vacuity guard (mirrors `test_scoped_getters.py`'s `test_there_are_getters_to_inspect`).

    A completeness check over an empty set passes proving nothing. If enumeration ever finds no
    identifier operations, the introspection is broken — a moved router, a changed prefix, a
    dropped `import app.main` — and every assertion below is silently waving through emptiness.
    """
    assert _identifier_operations(), (
        "no identifier operations discovered under /api/v1 — route introspection broke "
        "(is `app.main` imported so the app is constructed?)"
    )


def test_discovery_finds_known_routes_independently_of_the_registry() -> None:
    """Guard the guard, third direction: discovery must be LIVE, not a mirror of the registry.

    `test_every_identifier_endpoint_is_registered` subtracts the registry from discovery. If
    `_identifier_operations()` ever regressed to return exactly the registered set — a refactor
    that read `_SCOPE_REGISTRY` instead of the app, or an enumeration bug — the completeness
    check, the vacuity guard, and the stale-registry check would all false-green together. Pin a
    specific route known to exist from the *app itself*, not from the registry, so a discovery
    mechanism that silently mirrors the registry fails here. This is the standing form of the
    spec's one-time adversarial-injection proof (`GET /leave-requests/{request_id}`).
    """
    discovered = _identifier_operations()
    assert ("GET", "/api/v1/employees/{employee_id}") in discovered, (
        "route discovery no longer finds a known identifier endpoint — enumeration is broken or "
        "has begun mirroring the registry instead of reading the app's routed operations"
    )


def test_the_registry_is_not_empty() -> None:
    """Guard the guard (mirrors `test_architecture.py`): an emptied registry must itself fail.

    A completeness check reads the registry; a registry silently emptied — to a bad merge, or
    to a developer hushing a failure — would leave `test_every_identifier_endpoint_is_registered`
    passing over an unenforced matrix. That is the exact failure this project cannot afford.
    """
    assert _SCOPE_REGISTRY, "the SM-3 scope registry is empty — the matrix enforces nothing"


def test_every_identifier_endpoint_is_registered() -> None:
    """The AC4 teeth: every identifier operation the app exposes MUST declare a scope.

    An identifier endpoint added by a later story but never registered here fails the build,
    named by `(method, path)`. This is what makes "an endpoint added by a later story but never
    registered fails the test" literally true — the harness Epic 2 relies on.
    """
    unregistered = _identifier_operations() - set(_SCOPE_REGISTRY)

    assert not unregistered, (
        "these identifier endpoints accept a resource identifier but declare no SM-3 scope — "
        "register each in _SCOPE_REGISTRY with the scope api-contracts §4 grants it (an "
        f"unscoped identifier endpoint is the exact FR-03/DR-12 gap SM-3 forbids): {sorted(unregistered)}"
    )


def test_no_registered_entry_names_a_route_the_app_does_not_expose() -> None:
    """Guard the guard, other direction: a stale registry entry is also a defect.

    A registry key that no longer names a routed identifier operation (a renamed path, a removed
    endpoint) would let the completeness check pass while the matrix quietly describes an app
    that no longer exists. Every registered key must be a real, exposed identifier operation.
    """
    stale = set(_SCOPE_REGISTRY) - _identifier_operations()

    assert not stale, (
        "these registry entries name no identifier operation the app actually exposes — the "
        f"registry is stale; remove or fix each: {sorted(stale)}"
    )


@pytest.mark.parametrize(
    "operation",
    sorted(_SCOPE_REGISTRY),
    ids=lambda op: f"{op[0]} {op[1]}",
)
def test_each_registered_operation_grants_at_least_one_scope(
    operation: tuple[str, str],
) -> None:
    """Every registered identifier operation grants at least one `Scope`.

    Parametrized per entry so a failure names the offending operation directly. A registry
    value that is an empty set would authorize on nothing — declaring an endpoint "in the
    matrix" while granting it no scope is the same false green as omitting it. For Epic 1 each
    value is exactly `{Scope.ALL}`; Epic 2's may hold several, but never zero.
    """
    scopes = _SCOPE_REGISTRY[operation]

    assert scopes, f"{operation[0]} {operation[1]} is registered with no scope"
    assert all(isinstance(scope, Scope) for scope in scopes)
