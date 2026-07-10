"""Settings, security, and the error envelope. A leaf, not a layer.

Implements: AD-1 (by exclusion), NFR-20 (configuration from the environment).

Read by `api/`, `services/` and `jobs/`. Never by `domain/`: `core/` reads the
environment, which is I/O, and `domain/` performs none. That exclusion is enforced
by an import-linter contract, not by convention.
"""
