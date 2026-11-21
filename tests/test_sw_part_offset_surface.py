"""Offline contracts for native offset surfaces."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class Face:
    def __init__(self, model): self.model = model
    def Select2(self, append, mark): return mark == 0


class Feature:
    def __init__(self, name): self.Name, self.next = name, None
    def GetNextFeature(self): return self.next


class Manager:
    def __init__(self): self.last = None
    def GetLastFeatureAdded(self): return self.last


class Model:
    def __init__(self):
        self.features = [Feature("Base")]; self.FeatureManager = Manager(); self.args = None
    def FirstFeature(self): return self.features[0]
    def ClearSelection2(self, _all): pass
    def InsertOffsetSurface(self, distance, reverse):
        self.args = (distance, reverse)
        feature = Feature("Offset-Surface1"); self.features[-1].next = feature
        self.features.append(feature); self.FeatureManager.last = feature; return None


class OffsetSurfaceTests(unittest.TestCase):
    def test_hresult_empty_return_recovers_offset_feature(self):
        model = Model()
        feature = sw_part.offset_surface(model, Face(model), .005, reverse=True)
        self.assertEqual(feature.Name, "Offset-Surface1")
        self.assertEqual(model.args, (.005, True))

    def test_invalid_offset_inputs_are_rejected(self):
        model = Model()
        with self.assertRaises(ValueError): sw_part.offset_surface(model, (), .005)
        with self.assertRaises(ValueError): sw_part.offset_surface(model, Face(model), -.001)


if __name__ == "__main__":
    unittest.main()
