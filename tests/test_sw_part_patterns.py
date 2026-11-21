"""Offline regression tests for definition-based native feature patterns."""

import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class FakeFeature:
    def __init__(self, name, model=None):
        self.Name = name
        self.model = model

    def Select2(self, append, mark):
        if not append:
            self.model.selected = []
        self.model.selected.append((self, mark))
        return True


class FakeDefinition:
    pass


class FakeFeatureManager:
    def __init__(self, model):
        self.model = model
        self.calls = []

    def FeatureLinearPattern3(self, *args):
        self.calls.append(("linear", args, tuple(self.model.selected)))
        return FakeFeature("Linear Pattern")

    def FeatureCircularPattern4(self, *args):
        self.calls.append(("circular", args, tuple(self.model.selected)))
        return FakeFeature("Circular Pattern")

    def InsertMirrorFeature2(self, *args):
        self.calls.append(("mirror", args, tuple(self.model.selected)))
        return FakeFeature("Mirror")


class FakeExtension:
    def __init__(self, model):
        self.model = model

    def SelectByID2(self, name, _entity_type, _x, _y, _z, append, mark, _callout, _option):
        feature = self.model.features.get(name)
        if feature is None:
            return False
        return feature.Select2(append, mark)


class FakeModel:
    def __init__(self):
        self.selected = []
        self.FeatureManager = FakeFeatureManager(self)
        self.features = {
            "Seed": FakeFeature("Seed", self),
            "Right Plane": FakeFeature("Right Plane", self),
        }
        self.Extension = FakeExtension(self)

    def FeatureByName(self, name):
        return self.features.get(name)

    def ClearSelection2(self, _clear_all):
        self.selected = []


class PatternTests(unittest.TestCase):
    def test_linear_pattern_uses_feature_definition_and_object_axis(self):
        model = FakeModel()
        axis = FakeFeature("Axis", model)
        result = sw_part.linear_pattern_feature(model, "Seed", axis, 0.017, 4, reverse=True)
        self.assertIsInstance(result, FakeFeature)
        kind, args, selected = model.FeatureManager.calls[0]
        self.assertEqual(kind, "linear")
        self.assertEqual(args[:6], (4, 0.017, 1, 0.0, True, False))
        self.assertEqual(selected, ((axis, 1), (model.features["Seed"], 4)))
        self.assertEqual(model.selected, [])

    def test_circular_pattern_preserves_asymmetric_angle(self):
        model = FakeModel()
        axis = FakeFeature("Axis", model)
        angle = math.radians(233.0)
        sw_part.circular_pattern_feature(model, [model.features["Seed"]], axis, angle, 5)
        kind, args, selected = model.FeatureManager.calls[0]
        self.assertEqual(kind, "circular")
        self.assertEqual(args[0], 5)
        self.assertAlmostEqual(args[1], angle)
        self.assertTrue(args[5])
        self.assertEqual(selected, ((axis, 1), (model.features["Seed"], 4)))

    def test_mirror_resolves_named_plane_and_seed(self):
        model = FakeModel()
        sw_part.mirror_feature_objects(model, "Seed", "Right Plane", geometry_pattern=True)
        kind, args, selected = model.FeatureManager.calls[0]
        self.assertEqual(kind, "mirror")
        self.assertEqual(args, (False, True, False, False, 0))
        self.assertEqual(selected, ((model.features["Seed"], 1), (model.features["Right Plane"], 2)))

    def test_pattern_validation_rejects_invalid_counts_and_angles(self):
        model = FakeModel()
        with self.assertRaises(ValueError):
            sw_part.linear_pattern_feature(model, "Seed", FakeFeature("Axis", model), 0.01, 1)
        with self.assertRaises(ValueError):
            sw_part.circular_pattern_feature(model, "Seed", FakeFeature("Axis", model), math.tau + 0.01, 3)
        with self.assertRaises(ValueError):
            sw_part.mirror_feature_objects(model, (), "Right Plane")


if __name__ == "__main__":
    unittest.main()
