"""Offline contracts for native Radiate Surface."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class Feature:
    def __init__(self, name, kind):
        self.Name, self.kind, self.next = name, kind, None
    def GetTypeName2(self): return self.kind
    def GetNextFeature(self): return self.next


class SelectionData:
    Mark = 0


class SelectionManager:
    def CreateSelectData(self): return SelectionData()


class Entity:
    def __init__(self): self.calls = []
    def Select4(self, append, data):
        self.calls.append((append, data.Mark))
        return True


class Model:
    def __init__(self):
        self.before = Feature("Boss-Extrude1", "Boss")
        self.after = Feature("Surface-Radiate1", "SurfaceRadiate")
        self.SelectionManager = SelectionManager()
        self.SketchManager = type("SketchManager", (), {"ActiveSketch": None})()
        self.calls = []
    def FirstFeature(self): return self.before
    def ClearSelection2(self, all_items): pass
    def InsertRadiateSurface(self, *args):
        self.calls.append(args)
        self.before.next = self.after


class RadiateSurfaceTests(unittest.TestCase):
    def test_selection_marks_and_arguments(self):
        model, edge1, edge2, direction = Model(), Entity(), Entity(), Entity()
        feature = sw_part.radiate_surface(
            model, (edge1, edge2), direction, 0.012,
            flip=True, propagate_tangent=True,
        )
        self.assertIs(feature, model.after)
        self.assertEqual(model.calls, [(0.012, True, True)])
        self.assertEqual(edge1.calls, [(False, 2)])
        self.assertEqual(edge2.calls, [(True, 2)])
        self.assertEqual(direction.calls, [(True, 1)])

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            sw_part.radiate_surface(Model(), (), Entity(), 0.01)
        with self.assertRaises(ValueError):
            sw_part.radiate_surface(Model(), Entity(), None, 0.01)
        with self.assertRaises(ValueError):
            sw_part.radiate_surface(Model(), Entity(), Entity(), 0.0)

    def test_evidence(self):
        class Definition:
            Distance = 0.012
            Flip = True
            PropagateToTangentFaces = False
            DirectionReference = object()
            def AccessSelections(self, model, component): return True
            def ReleaseSelectionAccess(self): return None
            def GetRadiatedEntitiesCount(self): return 2
        class RadiateFeature:
            Name = "Surface-Radiate1"
            def GetTypeName2(self): return "SurfaceRadiate"
            def GetDefinition(self): return Definition()
            def GetErrorCode(self): return 0
        evidence = sw_part.radiate_surface_evidence(RadiateFeature(), object())
        self.assertAlmostEqual(evidence["distance"], 0.012)
        self.assertTrue(evidence["flip"])
        self.assertFalse(evidence["propagate_tangent_faces"])
        self.assertEqual(evidence["radiated_entity_count"], 2)
        self.assertTrue(evidence["has_direction_reference"])


if __name__ == "__main__":
    unittest.main()
