"""Offline contracts for native 3D sketch primitives."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class Sketch:
    Name = "3DSketch1"

    def __init__(self):
        self.segments = []

    def Is3D(self):
        return True

    def GetSketchSegments(self):
        return tuple(self.segments)


class Manager:
    def __init__(self):
        self.ActiveSketch = None
        self.AddToDB = False
        self.insert_calls = []
        self.line_args = None
        self.point_args = None
        self.spline_args = None

    def Insert3DSketch(self, update):
        self.insert_calls.append(update)
        self.ActiveSketch = Sketch() if self.ActiveSketch is None else None

    def CreateLine(self, *args):
        self.line_args = args
        line = object()
        self.ActiveSketch.segments.append(line)
        return line

    def CreatePoint(self, *args):
        self.point_args = args
        return object()

    def CreateSpline2(self, points, simplify):
        self.spline_args = (points, simplify)
        spline = object()
        self.ActiveSketch.segments.append(spline)
        return spline


class Model:
    def __init__(self):
        self.SketchManager = Manager()


class Sketch3DTests(unittest.TestCase):
    def test_point_uses_full_xyz_coordinates(self):
        model = Model()
        sw_part.start_3d_sketch(model)
        sw_part.sketch_point_3d(model, 0.001, -0.002, 0.003)
        self.assertEqual(model.SketchManager.point_args, (0.001, -0.002, 0.003))
        self.assertFalse(model.SketchManager.AddToDB)

    def test_start_and_line_use_full_xyz_coordinates(self):
        model = Model()
        sw_part.start_3d_sketch(model)
        sw_part.sketch_line_3d(model, (0.001, -0.002, 0.003), (0.011, 0.012, 0.023))
        self.assertEqual(
            model.SketchManager.line_args,
            (0.001, -0.002, 0.003, 0.011, 0.012, 0.023),
        )
        self.assertFalse(model.SketchManager.AddToDB)

    def test_spline_marshals_three_dimensional_points(self):
        model = Model()
        sw_part.start_3d_sketch(model)
        sw_part.sketch_spline_3d(
            model, ((0, 0, 0), (0.01, -0.002, 0.02), (0.02, 0.004, 0.03))
        )
        variant, simplify = model.SketchManager.spline_args
        self.assertEqual(tuple(variant.value), (0.0, 0.0, 0.0, 0.01, -0.002, 0.02, 0.02, 0.004, 0.03))
        self.assertFalse(simplify)

    def test_validation_rejects_invalid_geometry(self):
        model = Model()
        with self.assertRaises(RuntimeError):
            sw_part.sketch_line_3d(model, (0, 0, 0), (1, 0, 0))
        with self.assertRaises(RuntimeError):
            sw_part.sketch_point_3d(model, 0, 0, 0)
        sw_part.start_3d_sketch(model)
        with self.assertRaises(ValueError):
            sw_part.sketch_line_3d(model, (0, 0, 0), (0, 0, 0))
        with self.assertRaises(ValueError):
            sw_part.sketch_spline_3d(model, ((0, 0, 0), (1, 0, 0)))


if __name__ == "__main__":
    unittest.main()
