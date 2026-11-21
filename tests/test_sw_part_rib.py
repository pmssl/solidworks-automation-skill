"""Offline regression tests for the SW2025 native rib signature."""

import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class SketchFeature:
    def __init__(self, model): self.model = model
    def Select2(self, append, mark):
        self.model.selected = [self]
        return not append and mark == 0


class SelectionManager:
    def __init__(self, model): self.model = model
    def GetSelectedObjectCount2(self, _mark): return len(self.model.selected)


class SketchManager:
    ActiveSketch = None


class Extension:
    def SelectByID2(self, *_args): return False


class FeatureManager:
    def __init__(self): self.calls = []
    def InsertRib(self, *args): self.calls.append(args); return object()


class Model:
    def __init__(self):
        self.selected = []
        self.sketch = SketchFeature(self)
        self.SelectionManager = SelectionManager(self)
        self.SketchManager = SketchManager()
        self.Extension = Extension()
        self.FeatureManager = FeatureManager()
    def FeatureByName(self, name): return self.sketch if name == "Sketch2" else None
    def ClearSelection2(self, _all): self.selected = []


class RibTests(unittest.TestCase):
    def test_rib_uses_all_ten_sw2025_parameters(self):
        model = Model()
        sw_part.rib_feature(
            model, "Sketch2", 0.003,
            two_sided=False, reverse_thickness=True, reverse_material=True,
            reference_edge_index=2, draft_angle_rad=math.radians(7),
            draft_outward=True, normal_to_sketch=True, draft_from_wall=True,
        )
        args = model.FeatureManager.calls[0]
        self.assertEqual(len(args), 10)
        self.assertEqual(args[:5], (False, True, 0.003, 2, True))
        self.assertEqual(args[5:7], (True, True))
        self.assertAlmostEqual(args[7], math.radians(7))
        self.assertEqual(args[8:], (True, True))
        self.assertEqual(model.selected, [])

    def test_rib_rejects_invalid_parameters(self):
        with self.assertRaises(ValueError): sw_part.rib_feature(Model(), "Sketch2", 0)
        with self.assertRaises(ValueError):
            sw_part.rib_feature(Model(), "Sketch2", 0.003, draft_angle_rad=math.pi / 2)
        with self.assertRaises(ValueError):
            sw_part.rib_feature(Model(), "Sketch2", 0.003, reference_edge_index=-1)


if __name__ == "__main__":
    unittest.main()
