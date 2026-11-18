"""Offline P0 E8 receipt-completeness contract; no network or production access.

A successful HTTP upsert status is not evidence that every expected child row
was persisted. This deliberately independent verifier compares exact identities,
not merely counts, and refuses duplicate or malformed rows.
"""
from collections import Counter


def verify_core_child_identities(expected, observed):
    """Return False unless all five core families have exact persisted identities.

    Inputs are mappings of family -> list of identity tuples. Callers must
    obtain *observed* rows from an independent database read, not a POST receipt.
    """
    families = ("parent", "symbols", "signals", "features", "readiness")
    if not isinstance(expected, dict) or not isinstance(observed, dict):
        return False
    if set(expected) != set(families) or set(observed) != set(families):
        return False
    for family in families:
        want, got = expected[family], observed[family]
        if not isinstance(want, list) or not isinstance(got, list):
            return False
        if any(not isinstance(key, tuple) or not key or
               any(not isinstance(part, str) or not part for part in key)
               for key in want + got):
            return False
        if len(want) != len(set(want)) or len(got) != len(set(got)):
            return False
        if Counter(want) != Counter(got):
            return False
    return True
