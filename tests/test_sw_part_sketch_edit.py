"""Offline contracts for editing and deleting existing sketch entities."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class Point:
    X = Y = Z = 0.0
    def SetCoords(self, x, y, z): self.X, self.Y, self.Z = x, y, z; return True


class Segment:
    def __init__(self, model): self.model = model; self.ConstructionGeometry = False
    def Select2(self, append, mark):
        if not append: self.model.selected = []
        self.model.selected.append(self); return mark == 0


class Sketch:
    def __init__(self, segments): self.segments = segments
    def GetSketchSegments(self): return self.segments


class Manager:
    def __init__(self, sketch): self.ActiveSketch = sketch


class Extension:
    def __init__(self, model): self.model = model
    def DeleteSelection2(self, _options):
        for entity in self.model.selected:
            self.model.SketchManager.ActiveSketch.segments.remove(entity)
        return True


class Model:
    def __init__(self):
        self.selected = []
        self.segments = [Segment(self), Segment(self)]
        self.SketchManager = Manager(Sketch(self.segments))
        self.Extension = Extension(self)
    def ClearSelection2(self, _all): self.selected = []


class SketchEditTests(unittest.TestCase):
    def test_move_construction_and_delete(self):
        self.assertEqual(sw_part.move_sketch_point(Point(), .012, .005), (.012, .005, 0.0))
        model = Model()
        sw_part.set_sketch_construction(model.segments[0], True)
        self.assertTrue(model.segments[0].ConstructionGeometry)
        result = sw_part.delete_sketch_entities(model, model.segments[1])
        self.assertEqual(result, {"deleted": 1, "remaining": 1})

    def test_invalid_edit_inputs_are_rejected(self):
        with self.assertRaises(ValueError): sw_part.move_sketch_point(Point(), float("nan"), 0)
        with self.assertRaises(ValueError): sw_part.set_sketch_construction((), True)


if __name__ == "__main__":
    unittest.main()
