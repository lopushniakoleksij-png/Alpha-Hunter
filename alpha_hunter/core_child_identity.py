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

# QA-only full-field readback.  The identity contract above must still pass
# first: equal counts and row identifiers alone cannot prove persisted content.
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation


_CORE_IDENTITIES = {
    "parent": ("run_id",),
    "symbols": ("run_id", "symbol"),
    "signals": ("run_id", "signal_id", "symbol"),
    "features": ("run_id", "signal_id", "symbol"),
    "readiness": ("run_id", "symbol"),
}
_TIME_FIELDS = frozenset({"collected_at_utc", "detected_at_utc", "observed_at_utc"})


def _canonical_json_value(value):
    """Strict JSON-style values: distinguish boolean from numeric and reject NaN."""
    if value is None:
        return ("null",)
    if type(value) is bool:
        return ("bool", value)
    if type(value) in (int, float):
        number = Decimal(str(value))
        if not number.is_finite():
            raise ValueError("Non-finite QA field")
        return ("number", number.normalize())
    if type(value) is str:
        return ("string", value)
    if type(value) is list:
        return ("list", tuple(_canonical_json_value(x) for x in value))
    if type(value) is dict and all(type(k) is str for k in value):
        return ("object", tuple(sorted(
            (k, _canonical_json_value(v)) for k, v in value.items()
        )))
    raise ValueError("Invalid QA JSON field")


def _same_stored_field(field, expected, observed):
    if field in _TIME_FIELDS and isinstance(expected, str) and isinstance(observed, str):
        try:
            a = datetime.fromisoformat(expected.replace("Z", "+00:00"))
            b = datetime.fromisoformat(observed.replace("Z", "+00:00"))
            if a.tzinfo is None or b.tzinfo is None:
                return False
            return a.astimezone(timezone.utc) == b.astimezone(timezone.utc)
        except ValueError:
            return False
    return _canonical_json_value(expected) == _canonical_json_value(observed)


def verify_core_child_content(expected, observed):
    """Check ALL submitted fields against an independent, untruncated GET.

    Database-added columns are allowed, but absent or altered submitted fields,
    missing/extra identities and malformed values fail closed. No SQL or I/O.
    """
    try:
        if not isinstance(expected, dict) or not isinstance(observed, dict):
            return False
        if set(expected) != set(_CORE_IDENTITIES) or set(observed) != set(_CORE_IDENTITIES):
            return False
        if len(expected["parent"]) != 1 or len(observed["parent"]) != 1:
            return False
        for family, fields in _CORE_IDENTITIES.items():
            want, got = expected[family], observed[family]
            if not isinstance(want, list) or not isinstance(got, list):
                return False
            if len(want) != len(got):
                return False
            if any(not isinstance(row, dict) for row in want + got):
                return False

            def keyed(rows):
                by_id = {}
                for row in rows:
                    identity = tuple(row.get(k) for k in fields)
                    if (any(type(v) is not str or not v for v in identity)
                            or identity in by_id):
                        raise ValueError("Malformed or duplicate QA identity")
                    by_id[identity] = row
                return by_id

            desired = keyed(want)
            actual = keyed(got)
            if set(desired) != set(actual):
                return False
            for identity, original_row in desired.items():
                persisted_row = actual[identity]
                if any(
                    field not in persisted_row or
                    not _same_stored_field(field, value, persisted_row[field])
                    for field, value in original_row.items()
                ):
                    return False
        return True
    except (TypeError, ValueError, InvalidOperation):
        return False
