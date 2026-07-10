"""CLI entrypoints invoked by cron, not by a scheduler thread inside the server.

Implements: AD-1. The Leave Year rollover lands here in Story 2.10, as
`python -m app.jobs.rollover --year YYYY`. Under `uvicorn --workers 4` an
in-process scheduler would fire the job four times; a CLI job is also directly
callable from a test (NFR-15), with no running server.
"""
