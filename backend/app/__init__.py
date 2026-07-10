"""LeaveFlow backend application package.

Implements: AD-1 (one-way dependency direction), NFR-13 (structure is mechanical).

Import direction, enforced by `tests/test_architecture.py`:

    api -> services -> {repositories, domain}
    repositories -> domain

`api/` never imports `repositories/` or `domain/`. `repositories/` never imports
`services/`. `domain/` is pure: no ORM, no web framework, no I/O.
"""
