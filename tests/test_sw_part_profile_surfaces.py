"""Offline contracts for revolved, swept, and lofted surfaces."""

from pathlib import Path
import math
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class Feature:
    def __init__(self, name, kind): self.Name, self.kind = name, kind; self.calls = []; self.next = None
    def GetTypeName2(self): return self.kind
    def GetNextFeature(self): return self.next
    def Select2(self, append, mark): self.calls.append((append, mark)); return True


class Manager:
    def __init__(self, before, after): self.before, self.after = before, after; self.calls = []
    def InsertRevolvedRefSurface(self, *args): self.calls.append(("revolve", args)); self.before.next = self.after; return self.after
    def InsertSweepSurface3(self, *args): self.calls.append(("sweep", args)); self.before.next = self.after; return self.after
    def GetLastFeatureAdded(self): return self.after


class Model:
    def __init__(self):
        self.features = {name: Feature(name, "ProfileFeature") for name in ("Sketch1", "Sketch2", "Sketch3")}
        self.before = Feature("Sketch3", "ProfileFeature")
        self.after = Feature("Surface1", "SurfaceFeature")
        self.FeatureManager = Manager(self.before, self.after)
        self.SketchManager = type("SketchManager", (), {"ActiveSketch": None})()
        self.loft_args = None
    def FeatureByName(self, name): return self.features.get(str(name))
    def FirstFeature(self): return self.before
    def ClearSelection2(self, _all): pass
    def InsertLoftRefSurface2(self, *args): self.loft_args = args; self.before.next = self.after; return None


class ProfileSurfaceTests(unittest.TestCase):
    def test_revolve_surface_contract(self):
        model = Model()
        sw_part.revolve_surface(model, "Sketch1", math.pi, reverse_direction=True)
        self.assertEqual(model.FeatureManager.calls[-1], ("revolve", (math.pi, True, 0.0, 0)))

    def test_sweep_surface_marks_and_signature(self):
        model = Model()
        sw_part.sweep_surface(
            model, "Sketch1", "Sketch2", guide_curves=("Sketch3",),
        )
        self.assertEqual(model.features["Sketch1"].calls, [(False, 1)])
        self.assertEqual(model.features["Sketch2"].calls, [(True, 4)])
        self.assertEqual(model.features["Sketch3"].calls, [(True, 2)])
        self.assertEqual(len(model.FeatureManager.calls[-1][1]), 14)

    def test_sweep_surface_rejects_incompatible_guides(self):
        with self.assertRaises(ValueError):
            sw_part.sweep_surface(
                Model(), "Sketch1", "Sketch2",
                guide_curves=("Sketch3",), direction=1,
            )
        with self.assertRaises(ValueError):
            sw_part.sweep_surface(
                Model(), "Sketch1", "Sketch2",
                guide_curves=("Sketch3",), twist_control=8,
            )

    def test_sweep_surface_evidence(self):
        class Definition:
            TwistControlType = 2
            PathAlignmentType = 0
            Direction = 0
            StartTangencyType = 0
            EndTangencyType = 0
            MergeSmoothFaces = True
            def AccessSelections(self, model, component): return True
            def ReleaseSelectionAccess(self): return None
            def GetGuideCurvesCount(self): return 1
            def GetTwistAngle(self): return 0.25
            def IsBossFeature(self): return False
        class SweepFeature:
            Name = "Surface-Sweep1"
            def GetTypeName2(self): return "SweepRefSurface"
            def GetDefinition(self): return Definition()
            def GetErrorCode(self): return 0
        evidence = sw_part.sweep_surface_evidence(SweepFeature(), object())
        self.assertEqual(evidence["guide_curve_count"], 1)
        self.assertEqual(evidence["twist_control_type"], 2)
        self.assertAlmostEqual(evidence["twist_angle"], 0.25)
        self.assertFalse(evidence["is_boss"])

    def test_loft_surface_contract(self):
        model = Model()
        sw_part.loft_surface(model, ("Sketch1", "Sketch2"))
        self.assertEqual(model.loft_args, (False, False, False, 1.0, 0, 0))

    def test_loft_surface_guides_centerline_and_direction_marks(self):
        model = Model()
        guide = Feature("Guide", "ProfileFeature")
        centerline = Feature("Centerline", "ProfileFeature")
        start_reference = Feature("StartAxis", "RefAxis")
        end_reference = Feature("EndAxis", "RefAxis")
        sw_part.loft_surface(
            model, ("Sketch1", "Sketch2"),
            guide_curves=(guide,), centerline=centerline,
            start_matching_type=2, end_matching_type=2,
            start_tangent_reference=start_reference,
            end_tangent_reference=end_reference,
        )
        self.assertEqual(model.features["Sketch1"].calls, [(False, 1)])
        self.assertEqual(model.features["Sketch2"].calls, [(True, 1)])
        self.assertEqual(guide.calls, [(True, 2)])
        self.assertEqual(centerline.calls, [(True, 4)])
        self.assertEqual(start_reference.calls, [(True, 8)])
        self.assertEqual(end_reference.calls, [(True, 32)])
        self.assertEqual(model.loft_args, (False, False, False, 1.0, 2, 2))

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError): sw_part.revolve_surface(Model(), "Sketch1", 0)
        with self.assertRaises(ValueError): sw_part.loft_surface(Model(), ("Sketch1",))
        with self.assertRaises(ValueError): sw_part.loft_surface(
            Model(), ("Sketch1", "Sketch2"), start_matching_type=2,
        )
        with self.assertRaises(ValueError): sw_part.loft_surface(
            Model(), ("Sketch1", "Sketch2"), start_matching_type=9,
        )

    def test_loft_surface_evidence(self):
        class Definition:
            Centerline = object()
            StartDirectionVector = object()
            EndDirectionVector = object()
            StartTangencyType = 2
            EndTangencyType = 2
            Close = False
            def AccessSelections(self, model, component): return True
            def ReleaseSelectionAccess(self): return None
            def GetProfileCount(self): return 2
            def GetGuideCurvesCount(self): return 1
            def IsBossFeature(self): return False
            def IsThinFeature(self): return False
        class LoftFeature:
            def GetDefinition(self): return Definition()
            def GetErrorCode(self): return 0
        evidence = sw_part.loft_surface_evidence(LoftFeature(), object())
        self.assertEqual(evidence["profile_count"], 2)
        self.assertEqual(evidence["guide_curve_count"], 1)
        self.assertTrue(evidence["has_centerline"])
        self.assertTrue(evidence["has_start_direction_reference"])
        self.assertTrue(evidence["has_end_direction_reference"])
        self.assertFalse(evidence["is_boss"])
        self.assertTrue(evidence["feature_data_available"])

    def test_loft_surface_evidence_without_feature_data(self):
        class SurfaceFeature:
            Name = "Surface-Loft1"
            def GetTypeName2(self): return "BlendRefSurface"
            def GetDefinition(self): return None
            def GetParents(self): return ()
            def GetErrorCode(self): return 0
        evidence = sw_part.loft_surface_evidence(SurfaceFeature())
        self.assertFalse(evidence["feature_data_available"])
        self.assertEqual(evidence["feature_type"], "BlendRefSurface")
        self.assertEqual(evidence["feature_error_code"], 0)


if __name__ == "__main__":
    unittest.main()
