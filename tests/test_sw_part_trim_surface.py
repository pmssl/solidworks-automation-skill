"""Offline contracts for standard native Surface Trim."""

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


class Tool:
    def Select2(self, append, mark): return mark == 0


class Extension:
    def __init__(self): self.calls = []
    def SelectByID2(self, *args): self.calls.append(args); return args[1] == "SURFACEBODY"


class Manager:
    def __init__(self, feature):
        self.feature = feature
        self.pre = None
        self.sew = None
        self.SolidForTrim = None
    def PreTrimSurface(self, *args): self.pre = args; return True
    def PostTrimSurface(self, sew): self.sew = sew; return self.feature


class Model:
    def __init__(self):
        self.before = Feature("Surface-Plane1", "PlanarSurface")
        self.after = Feature("Surface-Trim1", "SurfaceTrim")
        self.FeatureManager = Manager(self.after)
        self.Extension = Extension()
    def ClearSelection2(self, _all): pass
    def FirstFeature(self): return self.before


class TrimSurfaceTests(unittest.TestCase):
    def test_standard_trim_contract(self):
        model = Model()
        feature = sw_part.trim_surface_standard(model, Tool(), ((.015, 0, 0),))
        self.assertIs(feature, model.after)
        self.assertEqual(model.FeatureManager.pre, (False, True, False, False))
        self.assertFalse(model.FeatureManager.sew)
        self.assertEqual(model.Extension.calls[0][1], "SURFACEBODY")

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError): sw_part.trim_surface_standard(Model(), (), ((0, 0, 0),))
        with self.assertRaises(ValueError): sw_part.trim_surface_standard(Model(), Tool(), ())
        with self.assertRaises(ValueError): sw_part.trim_surface_standard(Model(), Tool(), ((0, 0),))
        with self.assertRaises(ValueError):
            sw_part.trim_surface_standard(
                Model(), Tool(), ((0, 0, 0),), mutual_trim=True,
            )

    def test_mutual_trim_contract(self):
        model = Model()
        feature = sw_part.trim_surface_standard(
            model, (Tool(), Tool()), ((.015, 0, 0),), mutual_trim=True,
            remove_picked=True,
            mutual_surface_points=((.01, 0, 0), (0, .01, 0)),
        )
        self.assertIs(feature, model.after)
        self.assertEqual(model.FeatureManager.pre, (True, True, False, True))
        self.assertFalse(model.FeatureManager.SolidForTrim)
        self.assertEqual([call[1] for call in model.Extension.calls], [
            "SURFACEBODY", "SURFACEBODY", "SURFACEBODY",
        ])


if __name__ == "__main__":
    unittest.main()
