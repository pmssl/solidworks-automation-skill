"""Offline contracts for native extruded surfaces."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class Feature:
    def __init__(self, name, kind): self.Name, self.kind = name, kind
    def GetTypeName2(self): return self.kind
    def GetNextFeature(self): return None
    def Select2(self, _append, _mark): return True


class Manager:
    def __init__(self, after): self.after = after; self.args = None
    def FeatureExtruRefSurface3(self, *args): self.args = args; return None
    def GetLastFeatureAdded(self): return self.after


class Model:
    def __init__(self):
        self.sketch = Feature("Sketch1", "ProfileFeature")
        self.before = Feature("Sketch1", "ProfileFeature")
        self.after = Feature("Surface-Extrude1", "SurfExtrude")
        self.FeatureManager = Manager(self.after)
        self.SketchManager = type("SketchManager", (), {"ActiveSketch": None})()
    def FeatureByName(self, name): return self.sketch if name == "Sketch1" else None
    def FirstFeature(self): return self.before
    def ClearSelection2(self, _all): pass


class ExtrudeSurfaceTests(unittest.TestCase):
    def test_blind_surface_contract(self):
        model = Model()
        feature = sw_part.extrude_surface(model, "Sketch1", .025, direction=False)
        self.assertIs(feature, model.after)
        self.assertEqual(len(model.FeatureManager.args), 22)
        self.assertEqual(model.FeatureManager.args[:8], (True, False, 0, 0.0, 0, 0, .025, 0.0))

    def test_depth_must_be_positive(self):
        with self.assertRaises(ValueError): sw_part.extrude_surface(Model(), "Sketch1", 0)


if __name__ == "__main__":
    unittest.main()
