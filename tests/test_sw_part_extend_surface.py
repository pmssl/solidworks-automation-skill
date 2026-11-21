"""Offline contracts for native Surface Extend."""

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


class Edge:
    def __init__(self): self.calls = []
    def Select2(self, append, mark): self.calls.append((append, mark)); return True


class SelectionData:
    Mark = 0


class SelectionManager:
    def CreateSelectData(self): return SelectionData()


class Model:
    def __init__(self):
        self.before = Feature("Surface-Planar1", "PlanarSurface")
        self.after = Feature("Surface-Extend1", "SurfaceExtend")
        self.SelectionManager = SelectionManager()
        self.SketchManager = type("SketchManager", (), {"ActiveSketch": None})()
        self.calls = []
    def FirstFeature(self): return self.before
    def ClearSelection2(self, all_items): pass
    def InsertExtendSurface(self, *args):
        self.calls.append(args); self.before.next = self.after


class ExtendSurfaceTests(unittest.TestCase):
    def test_distance_contract(self):
        model, edge = Model(), Edge()
        feature = sw_part.extend_surface_distance(
            model, edge, 0.010, linear=True,
        )
        self.assertIs(feature, model.after)
        self.assertEqual(model.calls, [(True, 0, 0.010)])
        self.assertEqual(edge.calls, [(False, 0)])

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            sw_part.extend_surface_distance(Model(), (), 0.010)
        with self.assertRaises(ValueError):
            sw_part.extend_surface_distance(Model(), Edge(), 0.0)
        with self.assertRaises(ValueError):
            sw_part.extend_surface(
                Model(), Edge(), end_condition=1,
            )
        with self.assertRaises(ValueError):
            sw_part.extend_surface(
                Model(), Edge(), end_condition=2,
                terminal_reference=Edge(), distance=0.01,
            )

    def test_reference_end_condition_contract(self):
        model, edge, target = Model(), Edge(), Edge()
        sw_part.extend_surface(
            model, edge, linear=False, end_condition=2,
            terminal_reference=target,
        )
        self.assertEqual(model.calls, [(False, 2, 0.0)])
        self.assertEqual(edge.calls, [(False, 0)])
        self.assertEqual(target.calls, [(True, 0)])

    def test_evidence(self):
        class Definition:
            Type = 1
            EndCondition = 0
            Distance = 0.010
            def AccessSelections(self, model, component): return True
            def ReleaseSelectionAccess(self): return None
            def GetItemsCount(self): return 1
            def GetPropagatingEdgesCount(self): return 0
        class ExtendedFeature:
            Name = "Surface-Extend1"
            def GetTypeName2(self): return "SurfaceExtend"
            def GetDefinition(self): return Definition()
            def GetErrorCode(self): return 0
        evidence = sw_part.extend_surface_evidence(ExtendedFeature(), object())
        self.assertEqual(evidence["type"], 1)
        self.assertEqual(evidence["end_condition"], 0)
        self.assertAlmostEqual(evidence["distance"], 0.010)
        self.assertEqual(evidence["item_count"], 1)


if __name__ == "__main__":
    unittest.main()
