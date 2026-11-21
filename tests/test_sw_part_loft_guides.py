"""Offline contracts for native guide-curve boss and cut lofts."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class Feature:
    def __init__(self, name, model):
        self.Name = name
        self.model = model

    def Select2(self, append, mark):
        if not append:
            self.model.selected = []
        self.model.selected.append((self, mark))
        return True


class Manager:
    def __init__(self, model):
        self.model = model
        self.calls = []

    def InsertProtrusionBlend2(self, *args):
        self.calls.append((args, tuple(self.model.selected)))
        return Feature("Loft", self.model)

    def InsertCutBlend(self, *args):
        self.calls.append((args, tuple(self.model.selected)))
        return Feature("LoftCut", self.model)


class Extension:
    def __init__(self, model):
        self.model = model
        self.calls = []

    def SelectByID2(self, name, entity_type, x, y, z, append, mark, _callout, option):
        self.calls.append((name, entity_type, x, y, z, append, mark, option))
        if not append:
            self.model.selected = []
        feature = self.model.features.get(name)
        if feature is None:
            return False
        self.model.selected.append((feature, mark))
        return True


class Model:
    def __init__(self):
        self.selected = []
        self.features = {}
        self.FeatureManager = Manager(self)
        self.Extension = Extension(self)
        for name in ("Profile1", "Profile2", "Guide1", "Guide2", "Center"):
            self.features[name] = Feature(name, self)

    def FeatureByName(self, name):
        return self.features.get(name)

    def ClearSelection2(self, _clear_all):
        self.selected = []


class LoftGuideTests(unittest.TestCase):
    def test_uses_profile_guide_group_and_centerline_marks(self):
        model = Model()
        result = sw_part.loft_boss_with_guides(
            model, ("Profile1", "Profile2"), ("Guide1", "Guide2"),
            centerline="Center", guide_curve_influence=3,
        )
        self.assertEqual(result.Name, "Loft")
        args, selected = model.FeatureManager.calls[0]
        self.assertEqual(len(args), 18)
        self.assertEqual(args[-1], 3)
        self.assertEqual(
            selected,
            (
                (model.features["Profile1"], 1),
                (model.features["Profile2"], 1),
                (model.features["Guide1"], 4098),
                (model.features["Guide2"], 8194),
                (model.features["Center"], 4),
            ),
        )
        self.assertEqual(model.selected, [])

    def test_requires_profiles_guides_and_valid_influence(self):
        model = Model()
        with self.assertRaises(ValueError):
            sw_part.loft_boss_with_guides(model, ("Profile1",), ("Guide1",))
        with self.assertRaises(ValueError):
            sw_part.loft_boss_with_guides(model, ("Profile1", "Profile2"), ())
        with self.assertRaises(ValueError):
            sw_part.loft_boss_with_guides(
                model, ("Profile1", "Profile2"), ("Guide1",),
                guide_curve_influence=4,
            )

    def test_cut_uses_documented_profile_guide_and_centerline_marks(self):
        model = Model()
        result = sw_part.loft_cut_with_guides(
            model, ("Profile1", "Profile2"), ("Guide1", "Guide2"),
            centerline="Center", closed=True, keep_tangency=False,
        )
        self.assertEqual(result.Name, "LoftCut")
        args, selected = model.FeatureManager.calls[0]
        self.assertEqual(len(args), 12)
        self.assertEqual(args[:2], (True, False))
        self.assertEqual(args[-2:], (True, True))
        self.assertEqual(
            selected,
            (
                (model.features["Profile1"], 1),
                (model.features["Profile2"], 1),
                (model.features["Guide1"], 2),
                (model.features["Guide2"], 2),
                (model.features["Center"], 4),
            ),
        )
        self.assertEqual(model.selected, [])

    def test_cut_requires_profiles_and_guides(self):
        model = Model()
        with self.assertRaises(ValueError):
            sw_part.loft_cut_with_guides(model, ("Profile1",), ("Guide1",))
        with self.assertRaises(ValueError):
            sw_part.loft_cut_with_guides(model, ("Profile1", "Profile2"), ())

    def test_advanced_boss_centerline_thin_and_direction_tangency(self):
        model = Model()
        result = sw_part.loft_feature_advanced(
            model, ("Profile1", "Profile2"), centerline="Center",
            start_matching_type=2, end_matching_type=2,
            start_tangent_reference="Guide1",
            end_tangent_reference="Guide2",
            start_tangent_length=1.5, end_tangent_length=2.5,
            reverse_start_tangent=True,
            thin_type=3, thickness1=0.001, thickness2=0.002,
            merge=False, guide_curve_influence=2,
        )
        self.assertEqual(result.Name, "Loft")
        args, selected = model.FeatureManager.calls[0]
        self.assertEqual(len(args), 18)
        self.assertEqual(args[4:10], (2, 2, 1.5, 2.5, True, False))
        self.assertEqual(args[10:14], (True, 0.001, 0.002, 3))
        self.assertEqual(args[14:], (False, True, True, 2))
        self.assertEqual(
            selected,
            (
                (model.features["Profile1"], 1),
                (model.features["Profile2"], 1),
                (model.features["Center"], 4),
                (model.features["Guide1"], 8),
                (model.features["Guide2"], 32),
            ),
        )

    def test_advanced_cut_centerline_and_thin_contract(self):
        model = Model()
        result = sw_part.loft_feature_advanced(
            model, ("Profile1", "Profile2"), centerline="Center",
            cut=True, thin_type=2, thickness1=0.0015,
        )
        self.assertEqual(result.Name, "LoftCut")
        args, selected = model.FeatureManager.calls[0]
        self.assertEqual(args[6:10], (True, 0.0015, 0.0, 2))
        self.assertEqual(selected[-1], (model.features["Center"], 4))

    def test_advanced_validates_direction_refs_and_cut_only_limits(self):
        model = Model()
        with self.assertRaises(ValueError):
            sw_part.loft_feature_advanced(
                model, ("Profile1", "Profile2"), start_matching_type=2,
            )
        with self.assertRaises(ValueError):
            sw_part.loft_feature_advanced(
                model, ("Profile1", "Profile2"),
                start_tangent_reference="Guide1",
            )
        with self.assertRaises(ValueError):
            sw_part.loft_feature_advanced(
                model, ("Profile1", "Profile2"), cut=True,
                guide_curve_influence=1,
            )
        with self.assertRaises(ValueError):
            sw_part.loft_feature_advanced(
                model, ("Profile1", "Profile2"), cut=True,
                start_tangent_length=2.0,
            )
        with self.assertRaises(ValueError):
            sw_part.loft_feature_advanced(
                model, ("Profile1", "Profile2"), thickness1=0.001,
            )

    def test_advanced_selects_profiles_at_explicit_model_points(self):
        model = Model()
        result = sw_part.loft_feature_advanced(
            model, ("Profile1", "Profile2"),
            section_pick_points=((0.01, 0.02, 0.03), (0.04, 0.05, 0.06)),
        )
        self.assertEqual(result.Name, "Loft")
        self.assertEqual(
            model.Extension.calls,
            [
                ("Profile1", "SKETCH", 0.01, 0.02, 0.03, False, 1, 0),
                ("Profile2", "SKETCH", 0.04, 0.05, 0.06, True, 1, 0),
            ],
        )
        with self.assertRaises(ValueError):
            sw_part.loft_feature_advanced(
                model, ("Profile1", "Profile2"),
                section_pick_points=((0.0, 0.0, 0.0),),
            )


if __name__ == "__main__":
    unittest.main()
