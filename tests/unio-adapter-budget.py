#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Shared budget telemetry shape: strict build, strict read, honest Unknown."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('unio_adapter_budget', ROOT / 'tools/adapter-budget.py')
budget = importlib.util.module_from_spec(spec)
spec.loader.exec_module(budget)


class Build(unittest.TestCase):
    def test_reported_estimated_and_unknown_meters(self):
        value = budget.telemetry(
            tokens=budget.meter(201286, 12000000, 'reported'),
            turns=budget.meter(15, 180, 'estimated'),
            usd=budget.meter(.2888, 5.0, 'reported'))
        self.assertEqual(budget.validate(value), value)
        self.assertEqual(budget.summary(value),
                         'tokens 201286/12000000 reported; turns 15/180 estimated; usd 0.2888/5.0 reported')

    def test_absent_meters_stay_unknown_not_zero(self):
        value = budget.telemetry()
        for name in budget.METERS:
            self.assertEqual(value[name], dict(used=None, cap=None, provenance='unknown'))
        self.assertEqual(budget.summary(value),
                         'tokens unknown/none unknown; turns unknown/none unknown; usd unknown/none unknown')

    def test_builder_rejects_fabrications(self):
        for kwargs in (
            dict(used=10, cap=1, provenance='invented'),
            dict(used=None, cap=1, provenance='reported'),
            dict(used=None, cap=1, provenance='estimated'),
            dict(used=10, cap=1, provenance='unknown'),
            dict(used=-1, cap=1, provenance='reported'),
            dict(used=True, cap=1, provenance='reported'),
            dict(used=10, cap=-1, provenance='reported'),
            dict(used=10, cap=True, provenance='reported'),
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    budget.meter(**kwargs)
        with self.assertRaises(ValueError):
            budget.telemetry(tokens=budget.meter(1.5, 10, 'reported'))
        with self.assertRaises(ValueError):
            budget.telemetry(turns=budget.meter(1, 1.5, 'estimated'))
        with self.assertRaises(ValueError):
            budget.telemetry(tokens=budget.meter(1, 1, 'reported'), notes=('ok', 'x' * 241))
        with self.assertRaises(ValueError):
            budget.telemetry(tokens=budget.meter(1, 1, 'reported'), notes=[''] * 1)
        with self.assertRaises(ValueError):
            budget.telemetry(tokens=budget.meter(1, 1, 'reported'),
                            notes=['n%d' % i for i in range(budget.MAX_NOTES + 1)])


class Read(unittest.TestCase):
    def test_validate_accepts_only_the_exact_shape(self):
        good = budget.telemetry(tokens=budget.meter(5, 10, 'estimated'))
        self.assertEqual(budget.validate(good), good)
        for mutate in (
            lambda v: v.update(schema_version=2),
            lambda v: v.update(schema_version=True),
            lambda v: v.pop('turns'),
            lambda v: v.update(extra='secret'),
            lambda v: v['tokens'].update(used=-1),
            lambda v: v['tokens'].update(used=True),
            lambda v: v['tokens'].update(used=1.5),
            lambda v: v['tokens'].update(provenance='guessed'),
            lambda v: v['tokens'].update(used=None),
            lambda v: v['usd'].update(used=1, provenance='unknown'),
            lambda v: v.update(notes='not a list'),
            lambda v: v.update(notes=['ok', '']),
            lambda v: v.update(notes=['x' * 241]),
            lambda v: v.update(notes=['n%d' % i for i in range(budget.MAX_NOTES + 1)]),
        ):
            with self.subTest(mutate=mutate):
                import copy
                value = copy.deepcopy(good)
                mutate(value)
                self.assertIsNone(budget.validate(value))
        self.assertIsNone(budget.validate(None))
        self.assertIsNone(budget.validate([]))
        self.assertIsNone(budget.validate('tokens 1/2 reported'))

    def test_nonfinite_and_fractional_values_are_rejected(self):
        for used in (float('nan'), float('inf'), float('-inf')):
            with self.subTest(used=used):
                with self.assertRaises(ValueError):
                    budget.meter(used, 10, 'reported')
        nan_value = budget.telemetry(usd=budget.meter(1, 1, 'reported'))
        nan_value['usd']['used'] = float('nan')
        self.assertIsNone(budget.validate(nan_value))
        inf_cap = budget.telemetry(tokens=budget.meter(1, 1, 'reported'))
        inf_cap['tokens']['cap'] = float('inf')
        self.assertIsNone(budget.validate(inf_cap))

    def test_summary_of_unsafe_telemetry_is_unknown(self):
        self.assertEqual(budget.summary(None), 'Unknown')
        self.assertEqual(budget.summary({}), 'Unknown')
        forged = budget.telemetry(tokens=budget.meter(1, 1, 'reported'))
        forged['tokens']['provenance'] = 'secret'
        self.assertEqual(budget.summary(forged), 'Unknown')

    def test_fixed_resend_note_is_part_of_the_shared_module(self):
        self.assertIn('re-sends its whole context', budget.NOTE_RESENDS)
        self.assertIn('unknown, not zero', budget.NOTE_NO_EXPORT)


if __name__ == '__main__':
    unittest.main()
