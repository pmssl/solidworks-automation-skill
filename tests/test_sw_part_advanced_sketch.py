"""Offline contracts for ellipse, parabola, equation curve and sketch text."""

import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class SketchManager:
    def __init__(self): self.calls = []
    def CreateEllipse(self, *args): self.calls.append(("ellipse", args)); return object()
    def CreateParabola(self, *args): self.calls.append(("parabola", args)); return object()
    def CreateEquationSpline2(self, *args): self.calls.append(("equation", args)); return object()


class Model:
    def __init__(self): self.SketchManager = SketchManager(); self.text_calls = []
    def InsertSketchText(self, *args): self.text_calls.append(args); return object()


class AdvancedSketchTests(unittest.TestCase):
    def test_rotated_ellipse_builds_orthogonal_axis_points(self):
        model = Model()
        sw_part.sketch_ellipse(model, .01, -.02, .03, .012, math.pi / 2)
        args = model.SketchManager.calls[0][1]
        self.assertAlmostEqual(args[3], .01)
        self.assertAlmostEqual(args[4], .01)
        self.assertAlmostEqual(args[6], -.002)
        self.assertAlmostEqual(args[7], -.02)

    def test_parabola_and_equation_curve_preserve_non_symmetric_inputs(self):
        model = Model()
        sw_part.sketch_parabola(model, (0, .01), (0, 0), (-.02, .04), (.03, .05))
        self.assertEqual(model.SketchManager.calls[0][1],
                         (0, .01, 0.0, 0, 0, 0.0, -.02, .04, 0.0, .03, .05, 0.0))
        sw_part.sketch_equation_curve(model, "0.01*t", "0.002*t^2", -2, 3)
        args = model.SketchManager.calls[1][1]
        self.assertEqual(args[:5], ("0.01*t", "0.002*t^2", "", -2.0, 3.0))

    def test_text_and_parameter_validation(self):
        model = Model()
        sw_part.sketch_text(model, .01, .02, "SW", width_factor=1.25, character_spacing=.1)
        self.assertEqual(model.text_calls[0][3], "SW")
        self.assertEqual(model.text_calls[0][7:], (1.25, .1))
        with self.assertRaises(ValueError): sw_part.sketch_ellipse(model, 0, 0, .01, .02)
        with self.assertRaises(ValueError): sw_part.sketch_equation_curve(model, "t", "", 0, 1)
        with self.assertRaises(ValueError): sw_part.sketch_text(model, 0, 0, "")


if __name__ == "__main__":
    unittest.main()
