"""Offline contract for native 2D sketch points."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class Manager:
    def __init__(self): self.AddToDB = False; self.args = None; self.point = object()
    def CreatePoint(self, *args): self.args = args; return self.point


class Model:
    def __init__(self): self.SketchManager = Manager()


class SketchPointTests(unittest.TestCase):
    def test_create_native_sketch_point_and_restore_add_to_db(self):
        model = Model(); result = sw_part.sketch_point(model, .005, -.006)
        self.assertIs(result, model.SketchManager.point)
        self.assertEqual(model.SketchManager.args, (.005, -.006, 0.0))
        self.assertFalse(model.SketchManager.AddToDB)


if __name__ == "__main__":
    unittest.main()
