"""The pure functional core. No I/O, no ORM, no web framework, no settings.

Implements: AD-1, NFR-08 (exactly one implementation of the leave-day count),
NFR-15 / SM-2 (its tests need no database fixture).

Purity is what makes NFR-08 a structural fact rather than a review convention:
weekend-and-holiday logic can only be *expressed* in a package with no way to
reach a database.
"""
