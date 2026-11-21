"""Offline contracts for native Fill Surface."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class Feature:
    Name = "Surface-Fill1"
    def GetTypeName2(self): return "FillSurface"


class Boundary:
    def __init__(self): self.marks = []
    def Select2(self, append, mark): self.marks.append((append, mark)); return mark == 1


class Constraint:
    def __init__(self): self.marks = []
    def Select2(self, append, mark): self.marks.append((append, mark)); return mark == 4


class ControlledBoundary(Boundary):
    def Select2(self, append, mark): self.marks.append((append, mark)); return mark in (257, 513)


class DirectionFace:
    pass


class Manager:
    def __init__(self): self.args = None; self.feature = Feature()
    def InsertFillSurface2(self, *args): self.args = args; return self.feature


class Model:
    def __init__(self): self.FeatureManager = Manager(); self.clears = 0
    def ClearSelection2(self, _all): self.clears += 1
    def FirstFeature(self): return None


class FillSurfaceTests(unittest.TestCase):
    def test_single_boundary_contract(self):
        model, boundary = Model(), Boundary()
        feature = sw_part.fill_surface(model, boundary, resolution=3, optimize=False)
        self.assertIs(feature, model.FeatureManager.feature)
        self.assertEqual(boundary.marks, [(False, 1)])
        self.assertEqual(model.FeatureManager.args[:2], (3, 0))
        self.assertEqual(tuple(model.FeatureManager.args[2].value), (boundary,))
        self.assertEqual(tuple(model.FeatureManager.args[3].value), (0,))

    def test_invalid_inputs(self):
        model = Model()
        with self.assertRaises(ValueError): sw_part.fill_surface(model, ())
        with self.assertRaises(ValueError): sw_part.fill_surface(model, Boundary(), resolution=4)
    def test_internal_constraint_curve_uses_mark_four_and_argument(self):
        model, boundary, constraint = Model(), Boundary(), Constraint()
        sw_part.fill_surface(
            model, boundary, resolution=2, constraint_curves=(constraint,),
        )
        self.assertEqual(boundary.marks, [(False, 1)])
        self.assertEqual(constraint.marks, [(True, 4)])
        self.assertEqual(tuple(model.FeatureManager.args[5].value), (constraint,))

    def test_tangent_boundary_uses_mark_513_and_direction_face(self):
        model, boundary, face = Model(), ControlledBoundary(), DirectionFace()
        sw_part.fill_surface(
            model, boundary, contact_types=(1,), direction_faces=(face,),
        )
        self.assertEqual(boundary.marks, [(False, 513)])
        self.assertEqual(tuple(model.FeatureManager.args[3].value), (1,))
        self.assertEqual(tuple(model.FeatureManager.args[4].value), (face,))

    def test_continuity_contract_validation(self):
        model, boundary = Model(), ControlledBoundary()
        with self.assertRaises(ValueError):
            sw_part.fill_surface(model, boundary, contact_types=(3,))
        with self.assertRaises(ValueError):
            sw_part.fill_surface(model, boundary, contact_types=(1,))
        with self.assertRaises(ValueError):
            sw_part.fill_surface(
                model, boundary, contact_types=(1,), direction_faces=(None,),
            )


if __name__ == "__main__":
    unittest.main()
