#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Shared per-run budget telemetry shape for the optional adapters.

Every supported adapter receipt may carry one bounded, strictly typed
`budget_telemetry` object built here. Each meter (tokens, turns, usd) reports
a used value, the configured cap and an explicit provenance:

- "reported": the native CLI, library or adapter transport reported the value
  for this run.
- "estimated": an adapter-side counter or bounded owned stream observation;
  the receipt notes say exactly what was counted.
- "unknown": no trustworthy evidence exists for this run. Unknown is never
  zero, and no usage is ever inferred from an exit code, answer text or a
  configured limit alone.

The object is additive evidence: it never changes an adapter exit, a Source
outcome label, readiness, acceptance, policy or account availability, and it
is not a remaining-allowance or provider-quota measurement. Agents resend
their whole context every turn, so cumulative token usage grows with each
turn and can exhaust a cumulative cap while single turns stay small; the
fixed note below keeps that mechanism explicit next to the numbers.
"""
import math

SCHEMA_VERSION = 1
METERS = ("tokens", "turns", "usd")
PROVENANCE = ("reported", "estimated", "unknown")
MAX_NOTES = 8
MAX_NOTE_CHARS = 240
# Fixed explanation, always relevant to cumulative token meters.
NOTE_RESENDS = ("token totals are cumulative: the agent re-sends its whole context "
                "every turn, so usage grows with each turn and a run can exhaust a "
                "cumulative cap while single turns stay small")
NOTE_NO_EXPORT = ("the native CLI exported no usage for this run; token and USD "
                  "usage are unknown, not zero")
NOTE_TURNS_COUNTED = ("turns are the adapter's count of observed assistant responses; "
                      "the native CLI exports no turn count")


def _number(value, integral=False):
    if value is None:
        return True
    if type(value) is bool or not isinstance(value, (int, float)):
        return False
    if integral and type(value) is not int:
        return False
    try:
        return math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def meter(used, cap, provenance, integral=False):
    """Build one meter; used None means unknown, never zero."""
    if provenance not in PROVENANCE:
        raise ValueError("provenance")
    if used is None and provenance != "unknown":
        raise ValueError("missing used value")
    if used is not None and provenance == "unknown":
        raise ValueError("unknown provenance with a value")
    if not _number(used, integral) or not _number(cap, integral):
        raise ValueError("used or cap")
    return dict(used=used, cap=cap, provenance=provenance)


def telemetry(tokens=None, turns=None, usd=None, notes=()):
    """Build the bounded receipt object; absent meters stay unknown."""
    values = {}
    for name, item, integral in (("tokens", tokens, True), ("turns", turns, True), ("usd", usd, False)):
        if item is None:
            item = meter(None, None, "unknown")
        else:
            if not isinstance(item, dict) or set(item) != {"used", "cap", "provenance"}:
                raise ValueError(name)
            item = meter(item["used"], item["cap"], item["provenance"], integral)
        values[name] = item
    clean = []
    for note in notes:
        if not isinstance(note, str) or not note.strip() or len(note) > MAX_NOTE_CHARS:
            raise ValueError("note")
        clean.append(note)
    if len(clean) > MAX_NOTES:
        raise ValueError("too many notes")
    return dict(schema_version=SCHEMA_VERSION, tokens=values["tokens"],
                turns=values["turns"], usd=values["usd"], notes=clean)


def validate(value):
    """Strict reader: exact shape and types, or None (treated as absent)."""
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION \
            or type(value.get("schema_version")) is not int:
        return None
    if not set(value) <= {"schema_version", *METERS, "notes"} or not set(value) >= {"schema_version", *METERS}:
        return None
    for name in METERS:
        item = value[name]
        if not isinstance(item, dict) or set(item) != {"used", "cap", "provenance"}:
            return None
        try:
            checked = meter(item["used"], item["cap"], item["provenance"], name != "usd")
        except (ValueError, TypeError):
            return None
        if checked != item:
            return None
    notes = value.get("notes", [])
    if not isinstance(notes, list) or len(notes) > MAX_NOTES:
        return None
    for note in notes:
        if not isinstance(note, str) or not note.strip() or len(note) > MAX_NOTE_CHARS:
            return None
    return value


def _meter_text(name, item):
    used = "unknown" if item["used"] is None else str(item["used"])
    cap = "none" if item["cap"] is None else str(item["cap"])
    return name + " " + used + "/" + cap + " " + item["provenance"]


def summary(value):
    """One bounded human line for reports, or the honest Unknown label."""
    value = validate(value)
    if value is None:
        return "Unknown"
    return "; ".join(_meter_text(name, value[name]) for name in METERS)
