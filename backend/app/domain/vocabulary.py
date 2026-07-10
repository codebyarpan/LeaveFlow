"""The canonical vocabulary. Every enumerated string in LeaveFlow is declared here.

Implements: AD-21 — every enumerated string is `UPPER_SNAKE_CASE`, declared exactly
once in `domain/`, and appears as a literal nowhere else.

This module is near-empty, and that is correct for Story 1.1. It creates no domain
table, implements no FR, and so brings no enumerated value into existence. The
module exists now so that the first story to need one has an unambiguous home for
it, rather than scattering literals across `api/` and `repositories/` and being
consolidated later — which never happens.

What arrives, and where:

- Story 1.2 — the error codes `AUTH_FAILED` and `TOKEN_INVALID`, the role values,
  and the standing check that asserts none of them appears as a literal elsewhere.
- Story 2.1 — the Leave Type codes, as seeded *data*, not as constants here.
  `SM-5` requires a fourth Leave Type to be addable with no code change; a constant
  in this module would be exactly the code change it forbids.
- Story 2.6 onward — `leave_request.status`, which *is* code: four states the
  application handles exhaustively, stored as TEXT with a CHECK constraint.

The distinction between those last two is the whole of AD-11: a Leave Type is a row,
a request status is a constant.
"""

__all__: list[str] = []
