"""Imperative shell. Opens the transaction, loads rows, calls the pure core, writes.

Implements: AD-1. Raises typed domain exceptions (`domain.errors`) and imports no
HTTP: mapping an exception to a status code is `api/`'s concern, never this layer's.
"""
