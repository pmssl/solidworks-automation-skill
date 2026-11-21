"""Offline contracts for native Untrim Surface."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class Feature:
    Name = "Surface-Untrim1"
    def GetTypeName2(self): return "SurfaceExtend"


class Face:
    def Select2(self, append, mark): return not append and mark == 0


class Manager:
    def __init__(self): self.args = None; self.feature = Feature()
    def InsertUntrimSurface2(self, *args): self.args = args; return self.feature


class Model:
    def __init__(self): self.FeatureManager = Manager()
    def ClearSelection2(self, _all): pass
    def FirstFeature(self): return None


class UntrimSurfaceTests(unittest.TestCase):
    def test_untrim_contract(self):
        model = Model()
        feature = sw_part.untrim_surface(model, Face(), trim_opposite_side=True)
        self.assertIs(feature, model.FeatureManager.feature)
        self.assertEqual(model.FeatureManager.args, (0, 2, 0.0, False, True))

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError): sw_part.untrim_surface(Model(), ())
        with self.assertRaises(ValueError): sw_part.untrim_surface(Model(), Face(), face_untrim_type=4)
        with self.assertRaises(ValueError): sw_part.untrim_surface(Model(), Face(), distance=-1)


if __name__ == "__main__":
    unittest.main()
