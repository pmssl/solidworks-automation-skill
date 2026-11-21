"""Offline contracts for native Surface-Knit."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class SurfaceBody:
    def Select(self, append, mark): return mark == 1


class Manager:
    def __init__(self): self.args = None
    def InsertSewRefSurface(self, *args): self.args = args; return object()


class SelectionManager:
    def GetSelectedObjectCount2(self, _mark): return 2
    def GetSelectedObjectType3(self, _index, _mark): return 70


class Model:
    def __init__(self): self.FeatureManager = Manager(); self.SelectionManager = SelectionManager()
    def ClearSelection2(self, _all): pass


class KnitSurfaceTests(unittest.TestCase):
    def test_knit_parameter_contract(self):
        model = Model()
        sw_part.knit_surfaces(
            model, (SurfaceBody(), SurfaceBody()), try_form_solid=True,
            merge_entities=False, use_gap_filters=True,
            knit_tolerance=.00001, max_gap=.0002,
        )
        self.assertEqual(model.FeatureManager.args,
                         (True, True, False, .00001, .0002))

    def test_invalid_knit_inputs_are_rejected(self):
        with self.assertRaises(ValueError): sw_part.knit_surfaces(Model(), (SurfaceBody(),))
        with self.assertRaises(ValueError):
            sw_part.knit_surfaces(Model(), (SurfaceBody(), SurfaceBody()),
                                  knit_tolerance=.001, max_gap=.0001)


if __name__ == "__main__":
    unittest.main()
