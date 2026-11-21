"""Offline contracts for native Surface Flatten."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class Entity:
    def __init__(self): self.calls = []
    def Select4(self, append, data): self.calls.append((append, data.Mark)); return True


class SelectionData:
    Mark = 0


class SelectionManager:
    def CreateSelectData(self): return SelectionData()


class Feature:
    Name = "Surface-Flatten1"
    def GetTypeName2(self): return "FlattenSurface"
    def GetErrorCode(self): return 0


class Manager:
    def __init__(self): self.calls = []; self.feature = Feature()
    def InsertFlattenSurface2(self, *args): self.calls.append(args); return self.feature


class Model:
    def __init__(self):
        self.FeatureManager = Manager()
        self.SelectionManager = SelectionManager()
        self.SketchManager = type("SketchManager", (), {"ActiveSketch": None})()
    def FirstFeature(self): return None
    def ClearSelection2(self, all_items): pass


class FlattenSurfaceTests(unittest.TestCase):
    def test_creation_marks_and_signature(self):
        model, face, vertex = Model(), Entity(), Entity()
        feature = sw_part.flatten_surface(
            model, face, vertex, accuracy_factor=3,
        )
        self.assertIs(feature, model.FeatureManager.feature)
        self.assertEqual(face.calls, [(False, 1)])
        self.assertEqual(vertex.calls, [(True, 16)])
        self.assertEqual(model.FeatureManager.calls, [(3, False)])

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            sw_part.flatten_surface(Model(), (), Entity())
        with self.assertRaises(ValueError):
            sw_part.flatten_surface(Model(), Entity(), None)
        with self.assertRaises(ValueError):
            sw_part.flatten_surface(Model(), Entity(), Entity(), accuracy_factor=11)

    def test_evidence(self):
        class Definition:
            AccuracyFactor = 3
            Faces = (object(),)
            FixPointVertex = object()
            KeepInternalControlCurves = False
            ShouldMakeTears = False
            GuideEdges = ()
            TearEdges = ()
            MapEdges = ()
            def AccessSelections(self, model, component): return True
            def ReleaseSelectionAccess(self): return None
        class DefinedFeature(Feature):
            def GetDefinition(self): return Definition()
        evidence = sw_part.flatten_surface_evidence(DefinedFeature(), object())
        self.assertEqual(evidence["accuracy_factor"], 3)
        self.assertEqual(evidence["face_count"], 1)
        self.assertTrue(evidence["has_anchor_vertex"])
        self.assertFalse(evidence["should_make_tears"])


if __name__ == "__main__":
    unittest.main()
