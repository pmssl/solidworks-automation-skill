"""Offline contracts for semantic vertices and native reference geometry."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class Vertex:
    def __init__(self, point, model=None): self.point, self.model = point, model
    def GetPoint(self): return self.point
    def Select2(self, append, mark):
        if not append: self.model.selected = []
        self.model.selected.append((self, mark))
        return mark == 0


class Body:
    def __init__(self, vertices): self.vertices = vertices
    def GetVertices(self): return self.vertices


class Face(Vertex):
    pass


class Edge:
    def __init__(self, model, start, end): self.model, self.start, self.end = model, start, end
    def GetStartVertex(self): return self.start
    def GetEndVertex(self): return self.end
    def GetLength(self):
        return sum((a - b) ** 2 for a, b in zip(self.start.point, self.end.point)) ** .5
    def Select2(self, append, mark):
        if not append: self.model.selected = []
        self.model.selected.append((self, mark)); return True


class Feature:
    def __init__(self, name): self.Name, self.next = name, None
    def GetNextFeature(self): return self.next


class Manager:
    def __init__(self, model): self.model, self.last, self.coordinate_args = model, None, None
    def GetLastFeatureAdded(self): return self.last
    def CreateCoordinateSystemUsingNumericalValues(self, *args):
        self.coordinate_args = args
        self.last = self.model.add_feature("Coordinate System")
        return self.last
    def InsertReferencePoint(self, *args):
        self.reference_args = args
        return (self.model.add_feature("Point1"),)


class Model:
    def __init__(self):
        self.selected = []
        self.features = [Feature("Origin")]
        self.FeatureManager = Manager(self)
        self.vertices = [Vertex((0.01, 0.02, 0.03), self), Vertex((-0.01, 0, 0), self)]
    def GetBodies2(self, _body_type, _visible): return [Body(self.vertices + [self.vertices[0]])]
    def FirstFeature(self): return self.features[0]
    def add_feature(self, name):
        feature = Feature(name)
        self.features[-1].next = feature
        self.features.append(feature)
        self.FeatureManager.last = feature
        return feature
    def ClearSelection2(self, _all): self.selected = []
    def InsertRefPoint(self): self.add_feature("Point1"); return True
    def InsertAxis2(self, auto_size): self.auto_size = auto_size; self.add_feature("Axis1"); return True


class ReferenceGeometryTests(unittest.TestCase):
    def test_vertices_are_semantic_and_deduplicated(self):
        model = Model()
        self.assertEqual(len(sw_part.solid_vertices(model)), 2)
        found = sw_part.find_solid_vertices(model, (0.01, 0.02, 0.03))
        self.assertEqual(found, (model.vertices[0],))

    def test_reference_point_axis_and_coordinate_system(self):
        model = Model()
        point = sw_part.reference_point_face_center(model, Face((0, 0, .01), model))
        axis = sw_part.reference_axis_from_vertices(model, *model.vertices)
        coordinate = sw_part.coordinate_system_numeric(
            model, (0.007, -0.004, 0.003), (0.1, 0.2, 0.3)
        )
        self.assertEqual((point.Name, axis.Name, coordinate.Name),
                         ("Point1", "Axis1", "Coordinate System"))
        self.assertEqual(model.FeatureManager.coordinate_args,
                         (True, 0.007, -0.004, 0.003, True, 0.1, 0.2, 0.3))
        self.assertEqual(model.FeatureManager.reference_args, (4, 0, 0.0, 1))

    def test_invalid_reference_geometry_is_rejected(self):
        model = Model()
        with self.assertRaises(ValueError):
            sw_part.reference_axis_from_vertices(model, model.vertices[0], model.vertices[0])
        with self.assertRaises(ValueError):
            sw_part.coordinate_system_numeric(model, (0, 0), (0, 0, 0))

    def test_reference_axis_from_two_planes_uses_selection_driven_axis(self):
        model = Model(); first = Face((0, 0, 0), model); second = Face((0, 0, 0), model)
        axis = sw_part.reference_axis_from_planes(model, first, second, auto_size=False)
        self.assertEqual(axis.Name, "Axis1")
        self.assertFalse(model.auto_size)

    def test_reference_axis_from_point_and_plane(self):
        model = Model(); point = model.vertices[0]; plane = Face((0, 0, 0), model)
        axis = sw_part.reference_axis_from_point_and_plane(model, point, plane)
        self.assertEqual(axis.Name, "Axis1")

    def test_reference_axis_from_straight_edge(self):
        model = Model(); edge = Edge(model, *model.vertices)
        axis = sw_part.reference_axis_from_straight_edge(model, edge)
        self.assertEqual(axis.Name, "Axis1")

    def test_reference_point_semantic_wrappers(self):
        model = Model(); edge = Edge(model, *model.vertices); face = Face((0, 0, 0), model)
        sw_part.reference_point_along_curve(model, edge, 25.0, mode="percentage")
        self.assertEqual(model.FeatureManager.reference_args, (2, 1, 25.0, 1))
        sw_part.reference_point_along_curve(model, edge, .012, mode="distance")
        self.assertEqual(model.FeatureManager.reference_args, (2, 0, .012, 1))
        sw_part.reference_point_along_curve(
            model, edge, 0.0, mode="evenly_distributed", count=3,
        )
        self.assertEqual(model.FeatureManager.reference_args, (2, 2, 0.0, 3))
        sw_part.reference_point_face_vertex_projection(model, face, model.vertices[0])
        self.assertEqual(model.FeatureManager.reference_args, (5, 0, 0.0, 1))
        sw_part.reference_point_intersection(model, edge, face)
        self.assertEqual(model.FeatureManager.reference_args, (6, 0, 0.0, 1))
        sw_part.reference_point_from_sketch_point(model, model.vertices[0])
        self.assertEqual(model.FeatureManager.reference_args, (7, 0, 0.0, 1))


if __name__ == "__main__":
    unittest.main()
