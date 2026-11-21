"""Offline contracts for planar surface and thicken features."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class Body:
    def __init__(self, model): self.model = model
    def Select(self, append, mark): return mark == 1


class Feature:
    def __init__(self, name): self.Name, self.next = name, None
    def GetNextFeature(self): return self.next
    def Select2(self, append, mark): return True


class Extension:
    def SelectByID2(self, *args): return True


class Manager:
    def __init__(self, model): self.model = model; self.args = None; self.last = None
    def GetLastFeatureAdded(self): return self.last
    def FeatureBossThicken(self, *args): self.args = args; return Feature("Thicken1")


class Model:
    def __init__(self):
        self.features = [Feature("Sketch1")]; self.Extension = Extension()
        self.FeatureManager = Manager(self)
    def FirstFeature(self): return self.features[0]
    def FeatureByName(self, name): return self.features[0] if name == "Sketch1" else None
    def InsertPlanarRefSurface(self):
        feature = Feature("Surface-Planar1"); self.features[-1].next = feature
        self.features.append(feature); self.FeatureManager.last = feature; return True
    def ClearSelection2(self, _all): pass


class SurfaceTests(unittest.TestCase):
    def test_planar_surface_and_thicken_contracts(self):
        model = Model()
        surface = sw_part.planar_surface_from_sketch(model, "Sketch1")
        self.assertEqual(surface.Name, "Surface-Planar1")
        sw_part.thicken_surface(model, Body(model), .005, side=2)
        self.assertEqual(model.FeatureManager.args,
                         (.005, 2, 0, False, True, True, True))

    def test_invalid_thicken_side_is_rejected(self):
        with self.assertRaises(ValueError): sw_part.thicken_surface(Model(), Body(None), .005, side=3)


if __name__ == "__main__":
    unittest.main()
