"""Exact five-family identity comparison for independently persisted scan records.

Never interpret a POST acknowledgement as readback evidence. This pure
contract is shared by the production-code opt-in and isolated QA.
"""
from collections import Counter


def verify_core_child_identities(expected, observed):
    families = ("parent", "symbols", "signals", "features", "readiness")
    if not isinstance(expected, dict) or not isinstance(observed, dict):
        return False
    if set(expected) != set(families) or set(observed) != set(families):
        return False
    if any(not isinstance(expected[k], list) or not isinstance(observed[k], list)
           for k in families):
        return False
    if len(expected["parent"]) != 1 or len(observed["parent"]) != 1:
        return False
    for family in families:
        want, got = expected[family], observed[family]
        if any(not isinstance(key, tuple) or not key or
               any(not isinstance(part, str) or not part for part in key)
               for key in want + got):
            return False
        if len(want) != len(set(want)) or len(got) != len(set(got)):
            return False
        if Counter(want) != Counter(got):
            return False
    return True
