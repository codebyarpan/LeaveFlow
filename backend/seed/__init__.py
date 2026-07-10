"""The seed command. Data enters LeaveFlow here, never through a migration.

Implements: AD-11 (Leave Type rows are seeded as data, never inserted by a migration),
AC1 (the seed command is command three of the setup sequence), AC6 (it seeds nothing
in Story 1.1), NFR-21 (reproducible setup).

Invoked as a single documented command:

    python -m seed

It seeds NOTHING in this story, and exits 0. `department` and `employee` do not exist
until Story 1.2, and `leave_type` until Story 2.1. Exiting 0 is what lets AC1's
three-command sequence complete against a schema that has no tables.

Idempotent from the outset, deliberately. Story 1.2 and Story 2.1 extend it, and by
then "run the seed twice" must already be a safe operation rather than a habit someone
has to acquire — the setup sequence is documented, and documented commands get re-run.
"""
