"""Offline regression tests for semantic edge selection and edge features."""

import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class FakeVertex:
    def __init__(self, point):
        self.point = point

    def GetPoint(self):
        return self.point


class FakeEdge:
    def __init__(self, model, start, end):
        self.model = model
        self.start = FakeVertex(start)
        self.end = FakeVertex(end)

    def GetStartVertex(self):
        return self.start

    def GetEndVertex(self):
        return self.end

    def GetLength(self):
        return math.dist(self.start.point, self.end.point)

    def Select2(self, append, mark):
        if not append:
            self.model.selected = []
        self.model.selected.append(self)
        return mark == 0


class FakeBody:
    def __init__(self, edges):
        self.edges = edges

    def GetEdges(self):
        return self.edges


class FakeSelectionManager:
    def __init__(self, model):
        self.model = model

    def GetSelectedObjectCount2(self, _mark):
        return len(self.model.selected)


class FakeFeature:
    pass


class FakeFeatureManager:
    def __init__(self, model):
        self.model = model
        self.fillet_calls = []
        self.chamfer_calls = []

    def FeatureFillet(self, *args):
        self.fillet_calls.append((args, tuple(self.model.selected)))
        return FakeFeature()

    def InsertFeatureChamfer(self, *args):
        self.chamfer_calls.append((args, tuple(self.model.selected)))
        return FakeFeature()


class FakeModel:
    def __init__(self):
        self.selected = []
        self.SelectionManager = FakeSelectionManager(self)
        self.FeatureManager = FakeFeatureManager(self)
        self.edges = [
            FakeEdge(self, (-0.02, -0.015, 0.0), (-0.02, -0.015, 0.02)),
            FakeEdge(self, (0.02, -0.015, 0.0), (0.02, -0.015, 0.02)),
            FakeEdge(self, (-0.02, -0.015, 0.0), (0.02, -0.015, 0.0)),
        ]
        self.body = FakeBody(self.edges)

    def GetBodies2(self, body_type, visible_only):
        assert (body_type, visible_only) == (0, False)
        return [self.body]

    def ClearSelection2(self, _clear_all):
        self.selected = []


class EdgeFeatureTests(unittest.TestCase):
    def test_find_solid_edges_uses_unoriented_direction_and_midpoint(self):
        model = FakeModel()
        matches = sw_part.find_solid_edges(
            model,
            length=0.02,
            direction=(0, 0, -1),
            midpoint=(-0.02, -0.015, 0.01),
        )
        self.assertEqual(matches, (model.edges[0],))
        geometry = sw_part.edge_geometry(matches[0])
        for actual, expected in zip(geometry["direction"], (0.0, 0.0, 1.0)):
            self.assertAlmostEqual(actual, expected)

    def test_fillet_selects_explicit_edges_and_clears_selection(self):
        model = FakeModel()
        feature = sw_part.fillet(model, 0.003, edges=model.edges[:2])
        self.assertIsInstance(feature, FakeFeature)
        args, selected = model.FeatureManager.fillet_calls[0]
        self.assertEqual(args[:2], (195, 0.003))
        self.assertEqual(selected, tuple(model.edges[:2]))
        self.assertEqual(model.selected, [])

    def test_chamfer_selects_edge_and_preserves_asymmetric_angle(self):
        model = FakeModel()
        feature = sw_part.chamfer(model, 0.002, 37.0, edges=[model.edges[0]])
        self.assertIsInstance(feature, FakeFeature)
        args, selected = model.FeatureManager.chamfer_calls[0]
        self.assertEqual(args[:3], (4, 1, 0.002))
        self.assertAlmostEqual(args[3], math.radians(37.0))
        self.assertEqual(selected, (model.edges[0],))
        self.assertEqual(model.selected, [])

    def test_edge_features_reject_invalid_parameters(self):
        for operation, args in (
            (sw_part.fillet, (0.0,)),
            (sw_part.chamfer, (-0.001, 45.0)),
            (sw_part.chamfer, (0.001, 90.0)),
        ):
            with self.subTest(operation=operation.__name__, args=args):
                with self.assertRaises(ValueError):
                    operation(FakeModel(), *args)


if __name__ == "__main__":
    unittest.main()
