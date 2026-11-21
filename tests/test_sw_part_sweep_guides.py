"""Offline contracts for native guide-curve boss sweeps."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class Feature:
    def __init__(self, name, model): self.Name, self.model = name, model
    def Select2(self, append, mark):
        if not append: self.model.selected = []
        self.model.selected.append((self, mark)); return True


class Contour:
    def __init__(self, closed): self.closed = closed
    def IsClosed(self): return self.closed


class SketchDefinition:
    def __init__(self, closed): self.contours = [Contour(closed)]
    def GetSketchContours(self): return self.contours


class SketchFeature(Feature):
    def __init__(self, name, model, closed):
        super().__init__(name, model)
        self.definition = SketchDefinition(closed)
    def GetSpecificFeature2(self): return self.definition


class Manager:
    def __init__(self, model): self.model, self.calls = model, []
    def InsertProtrusionSwept4(self, *args):
        self.calls.append(("boss", args, tuple(self.model.selected)))
        return Feature("Sweep", self.model)
    def InsertCutSwept5(self, *args):
        self.calls.append(("cut", args, tuple(self.model.selected)))
        return Feature("CutSweep", self.model)
    def InsertProtrusionSwept(self, *args):
        self.calls.append(("boss_legacy", args, tuple(self.model.selected)))
        return Feature("Sweep", self.model)
    def InsertCutSwept(self, *args):
        self.calls.append(("cut_legacy", args, tuple(self.model.selected)))
        return Feature("CutSweep", self.model)


class Model:
    def __init__(self):
        self.selected = []
        self.features = {name: Feature(name, self) for name in ("Profile", "Path", "Guide1", "Guide2")}
        self.FeatureManager = Manager(self)
    def FeatureByName(self, name): return self.features.get(name)
    def ClearSelection2(self, _all): self.selected = []


class SweepGuideTests(unittest.TestCase):
    def test_uses_documented_profile_path_and_guide_marks(self):
        model = Model()
        feature = sw_part.sweep_boss_with_guides(
            model, "Profile", "Path", ("Guide1", "Guide2"),
            twist_control=2, path_alignment=1, merge_smooth_faces=False,
        )
        self.assertEqual(feature.Name, "Sweep")
        kind, args, selected = model.FeatureManager.calls[0]
        self.assertEqual(kind, "boss")
        self.assertEqual(len(args), 20)
        self.assertEqual(args[2], 2)
        self.assertEqual(args[11], 1)
        self.assertFalse(args[16])
        self.assertEqual(args[15], 0.0)
        self.assertEqual(args[19], 0)
        self.assertEqual(
            selected,
            ((model.features["Profile"], 1), (model.features["Path"], 4),
             (model.features["Guide1"], 2), (model.features["Guide2"], 2)),
        )
        self.assertEqual(model.selected, [])

    def test_requires_guide_curve(self):
        with self.assertRaises(ValueError):
            sw_part.sweep_boss_with_guides(Model(), "Profile", "Path", ())

    def test_cut_sweep_uses_full_insert_cut_swept5_contract(self):
        model = Model()
        feature = sw_part.sweep_cut_with_guides(
            model, "Profile", "Path", ("Guide1", "Guide2"),
            twist_control=3, path_alignment=2, merge_smooth_faces=False,
        )
        self.assertEqual(feature.Name, "CutSweep")
        kind, args, selected = model.FeatureManager.calls[0]
        self.assertEqual(kind, "cut")
        self.assertEqual(len(args), 22)
        self.assertEqual(args[2], 3)
        self.assertEqual(args[11], 2)
        self.assertTrue(args[12])
        self.assertTrue(args[13])
        self.assertFalse(args[15])
        self.assertEqual(args[16:19], (False, False, False))
        self.assertEqual(args[19:], (False, 0.0, 0))
        self.assertEqual(
            selected,
            ((model.features["Profile"], 1), (model.features["Path"], 4),
             (model.features["Guide1"], 2), (model.features["Guide2"], 2)),
        )
        self.assertEqual(model.selected, [])

    def test_cut_sweep_requires_guide_curve(self):
        with self.assertRaises(ValueError):
            sw_part.sweep_cut_with_guides(Model(), "Profile", "Path", ())

    def test_thin_midplane_boss_uses_total_thickness(self):
        model = Model()
        feature = sw_part.sweep_thin_feature(
            model, "Profile", "Path", 0.002,
            guide_curves=("Guide1",), thin_type=2,
            twist_control=1, path_alignment=2,
            twist_angle=0.3, direction=1,
        )
        self.assertEqual(feature.Name, "Sweep")
        kind, args, selected = model.FeatureManager.calls[0]
        self.assertEqual(kind, "boss")
        self.assertEqual(len(args), 20)
        self.assertTrue(args[7])
        self.assertEqual((args[8], args[9], args[10]), (0.002, 0.0, 2))
        self.assertEqual((args[2], args[11]), (1, 2))
        self.assertEqual(args[15], 0.3)
        self.assertEqual(args[19], 1)
        self.assertEqual(
            selected,
            ((model.features["Profile"], 1), (model.features["Path"], 4),
             (model.features["Guide1"], 2)),
        )

    def test_thin_two_wall_cut_uses_insert_cut_swept5(self):
        model = Model()
        feature = sw_part.sweep_thin_feature(
            model, "Profile", "Path", 0.0015,
            thin_type=3, thickness2=0.0025, cut=True, direction=2,
        )
        self.assertEqual(feature.Name, "CutSweep")
        kind, args, _selected = model.FeatureManager.calls[0]
        self.assertEqual(kind, "cut")
        self.assertEqual(len(args), 22)
        self.assertTrue(args[7])
        self.assertEqual((args[8], args[9], args[10]), (0.0015, 0.0025, 3))
        self.assertEqual(args[21], 2)

    def test_simple_thin_sweep_uses_verified_short_contract(self):
        model = Model()
        sw_part.sweep_thin_feature(
            model, "Profile", "Path", 0.002, thin_type=2,
        )
        kind, args, selected = model.FeatureManager.calls[0]
        self.assertEqual(kind, "boss_legacy")
        self.assertEqual(len(args), 14)
        self.assertTrue(args[0])
        self.assertTrue(args[7])
        self.assertEqual((args[8], args[9], args[10]), (0.002, 0.0, 2))
        self.assertEqual(
            selected,
            ((model.features["Profile"], 1), (model.features["Path"], 4)),
        )

    def test_thin_sweep_validates_wall_and_direction(self):
        with self.assertRaises(ValueError):
            sw_part.sweep_thin_feature(Model(), "Profile", "Path", 0.0)
        with self.assertRaises(ValueError):
            sw_part.sweep_thin_feature(
                Model(), "Profile", "Path", 0.001, thin_type=3,
            )
        with self.assertRaises(ValueError):
            sw_part.sweep_thin_feature(
                Model(), "Profile", "Path", 0.001, direction=3,
            )

    def test_thin_sweep_rejects_open_sketch_profile_before_com_call(self):
        model = Model()
        model.features["Profile"] = SketchFeature(
            "Profile", model, closed=False,
        )

        with self.assertRaisesRegex(ValueError, "requires closed sketch contours"):
            sw_part.sweep_thin_feature(
                model, "Profile", "Path", 0.002, thin_type=2,
            )

        self.assertEqual(model.FeatureManager.calls, [])

    def test_advanced_bidirectional_constant_twist_boss(self):
        model = Model()
        feature = sw_part.sweep_feature_advanced(
            model, "Profile", "Path",
            direction=1, twist_control=8, twist_angle=1.25,
            merge=False, merge_smooth_faces=False,
        )
        self.assertEqual(feature.Name, "Sweep")
        kind, args, selected = model.FeatureManager.calls[0]
        self.assertEqual(kind, "boss")
        self.assertEqual(len(args), 20)
        self.assertEqual(args[2], 8)
        self.assertEqual(args[15], 1.25)
        self.assertFalse(args[12])
        self.assertFalse(args[16])
        self.assertEqual(args[19], 1)
        self.assertEqual(
            selected,
            ((model.features["Profile"], 1), (model.features["Path"], 4)),
        )

    def test_advanced_cut_preserves_guide_selection(self):
        model = Model()
        sw_part.sweep_feature_advanced(
            model, "Profile", "Path", guide_curves=("Guide1",),
            cut=True, direction=2,
        )
        kind, args, selected = model.FeatureManager.calls[0]
        self.assertEqual(kind, "cut")
        self.assertEqual(len(args), 22)
        self.assertEqual(args[21], 2)
        self.assertEqual(
            selected,
            ((model.features["Profile"], 1), (model.features["Path"], 4),
             (model.features["Guide1"], 2)),
        )

    def test_advanced_sweep_validates_twist_and_direction(self):
        with self.assertRaises(ValueError):
            sw_part.sweep_feature_advanced(
                Model(), "Profile", "Path", twist_control=4,
            )
        with self.assertRaises(ValueError):
            sw_part.sweep_feature_advanced(
                Model(), "Profile", "Path", twist_control=0, twist_angle=0.2,
            )
        with self.assertRaises(ValueError):
            sw_part.sweep_feature_advanced(
                Model(), "Profile", "Path", direction=-1,
            )


if __name__ == "__main__":
    unittest.main()
