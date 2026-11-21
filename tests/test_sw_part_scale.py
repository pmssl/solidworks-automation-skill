"""Offline contracts for native Scale features."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class Data:
    Type = 1
    IsUniform = False
    ScaleX = 1.5
    ScaleY = 0.5
    ScaleZ = 2.0
    CoordinateSystem = None
    def GetBodiesCount(self): return 1


class Feature:
    Name = "Scale1"
    def GetTypeName2(self): return "Scale"
    def GetDefinition(self): return Data()
    def GetErrorCode(self): return 0
    def GetNextFeature(self): return None


class Body:
    def __init__(self): self.calls = []
    def Select2(self, append, mark):
        self.calls.append((append, mark))
        return True


class Manager:
    def __init__(self): self.args = None; self.feature = Feature()
    def InsertScale(self, *args): self.args = args; return self.feature


class Model:
    def __init__(self): self.FeatureManager = Manager(); self.clears = 0
    def ClearSelection2(self, all_items): self.clears += 1
    def FirstFeature(self): return None


class ScaleTests(unittest.TestCase):
    def test_nonuniform_origin_scale_and_body_selection(self):
        model, first, second = Model(), Body(), Body()
        feature = sw_part.scale_feature(
            model, 1.5, 0.5, 2.0, about="origin", bodies=(first, second),
        )
        self.assertIs(feature, model.FeatureManager.feature)
        self.assertEqual(model.FeatureManager.args, (1, False, 1.5, 0.5, 2.0))
        self.assertEqual(first.calls, [(False, 0)])
        self.assertEqual(second.calls, [(True, 0)])

    def test_uniform_centroid_scale(self):
        model = Model()
        sw_part.scale_feature(model, 0.75)
        self.assertEqual(model.FeatureManager.args, (0, True, 0.75, 0.75, 0.75))

    def test_uniform_coordinate_system_scale_with_body_scope(self):
        model, coordinate_system, body = Model(), Body(), Body()
        sw_part.scale_feature(
            model, 2.0, about="coordinate_system",
            coordinate_system=coordinate_system, bodies=(body,),
        )
        self.assertEqual(model.FeatureManager.args, (2, True, 2.0, 2.0, 2.0))
        self.assertEqual(coordinate_system.calls, [(False, 0)])
        self.assertEqual(body.calls, [(True, 0)])

    def test_validates_factors_and_mode(self):
        with self.assertRaises(ValueError): sw_part.scale_feature(Model(), 0.0)
        with self.assertRaises(ValueError): sw_part.scale_feature(Model(), 1.0, 2.0)
        with self.assertRaises(ValueError): sw_part.scale_feature(Model(), 1.0, about="coordinate_system")
        with self.assertRaises(ValueError):
            sw_part.scale_feature(Model(), 1.0, coordinate_system=Body())

    def test_reads_native_feature_data(self):
        evidence = sw_part.scale_feature_evidence(Feature())
        self.assertEqual(evidence["about"], "origin")
        self.assertEqual(evidence["factors"], (1.5, 0.5, 2.0))
        self.assertEqual(evidence["coordinate_system"], "")
        self.assertEqual(evidence["selected_body_count"], 1)
        self.assertEqual(evidence["scope"], "selected_bodies")
        self.assertEqual(evidence["error_code"], 0)


if __name__ == "__main__":
    unittest.main()
