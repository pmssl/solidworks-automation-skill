"""Offline contracts for native multibody Combine features."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class Manager:
    def __init__(self): self.calls = []
    def InsertCombineFeature(self, *args): self.calls.append(args); return object()


class Model:
    def __init__(self): self.FeatureManager = Manager()


class CombineTests(unittest.TestCase):
    def test_add_intersect_and_cut_contracts(self):
        model, first, second = Model(), object(), object()
        sw_part.combine_bodies(model, 15903, (first, second))
        sw_part.combine_bodies(model, 15901, (first, second))
        sw_part.combine_bodies(model, 15902, (first, second), main_body=first)
        self.assertEqual([call[0] for call in model.FeatureManager.calls],
                         [15903, 15901, 15902])
        self.assertIs(model.FeatureManager.calls[2][1], first)

    def test_invalid_combine_inputs_are_rejected(self):
        model, body = Model(), object()
        with self.assertRaises(ValueError): sw_part.combine_bodies(model, 0, (body,))
        with self.assertRaises(ValueError): sw_part.combine_bodies(model, 15903, (body,))
        with self.assertRaises(ValueError): sw_part.combine_bodies(model, 15902, (body,))


if __name__ == "__main__":
    unittest.main()
