"""Offline contracts for native multi-reference planes."""

from pathlib import Path
import math
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class Entity:
    def __init__(self): self.calls = []
    def Select2(self, append, mark):
        self.calls.append((append, mark))
        return True


class CylinderSurface:
    IsCylinder = True
    IsCone = False


class CylinderFace(Entity):
    def GetSurface(self): return CylinderSurface()


class Manager:
    def __init__(self): self.args = None; self.plane = object()
    def InsertRefPlane(self, *args): self.args = args; return self.plane


class Model:
    def __init__(self): self.FeatureManager = Manager(); self.clear_calls = 0
    def ClearSelection2(self, _all): self.clear_calls += 1


class Transform:
    ArrayData = (0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 2.0, 0.0, 0.0,
                 0.020, 0.015, 0.010, 1.0, 0.0, 0.0, 0.0)


class RefPlane:
    Transform = Transform()


class ReferencePlaneTests(unittest.TestCase):
    def test_three_vertex_plane_uses_coincident_constraints_and_marks(self):
        model = Model(); vertices = (Entity(), Entity(), Entity())
        result = sw_part.reference_plane_through_three_vertices(model, *vertices)
        self.assertIs(result, model.FeatureManager.plane)
        self.assertEqual(model.FeatureManager.args, (4, 0.0, 4, 0.0, 4, 0.0))
        self.assertEqual([item.calls for item in vertices], [[(False, 0)], [(True, 1)], [(True, 2)]])
        self.assertEqual(model.clear_calls, 2)

    def test_one_reference_is_padded_to_six_arguments(self):
        model = Model(); entity = Entity()
        sw_part.constraint_reference_plane(model, ((entity, 8 | 256, .012),))
        self.assertEqual(model.FeatureManager.args, (264, .012, 0, 0.0, 0, 0.0))

    def test_rejects_invalid_reference_count_before_selection(self):
        model = Model()
        with self.assertRaises(ValueError): sw_part.constraint_reference_plane(model, ())
        self.assertEqual(model.clear_calls, 0)

    def test_angle_plane_uses_angle_and_coincident_hinge(self):
        model = Model(); face = Entity(); edge = Entity()
        sw_part.reference_plane_at_angle(
            model, face, edge, math.radians(37.0), flip=True,
        )
        self.assertEqual(
            model.FeatureManager.args,
            (16 | 256, math.radians(37.0), 4, 0.0, 0, 0.0),
        )
        self.assertEqual(face.calls, [(False, 0)])
        self.assertEqual(edge.calls, [(True, 1)])

    def test_angle_plane_rejects_zero_angle(self):
        with self.assertRaises(ValueError):
            sw_part.reference_plane_at_angle(Model(), Entity(), Entity(), 0.0)

    def test_midplane_uses_two_midplane_constraints(self):
        model = Model(); first = Entity(); second = Entity()
        sw_part.reference_midplane(model, first, second)
        self.assertEqual(
            model.FeatureManager.args,
            (128, 0.0, 128, 0.0, 0, 0.0),
        )
        self.assertEqual(first.calls, [(False, 0)])
        self.assertEqual(second.calls, [(True, 1)])

    def test_tangent_parallel_plane_uses_curved_face_and_plane(self):
        model = Model(); face = CylinderFace(); plane = Entity()
        sw_part.reference_plane_tangent_parallel(model, face, plane, flip=True)
        self.assertEqual(
            model.FeatureManager.args,
            (32 | 256, 0.0, 1, 0.0, 0, 0.0),
        )
        self.assertEqual(face.calls, [(False, 0)])
        self.assertEqual(plane.calls, [(True, 1)])

    def test_tangent_projected_point_plane_uses_surface_then_project_constraint(self):
        model = Model(); face = CylinderFace(); point = Entity()
        sw_part.reference_plane_tangent_at_projected_point(
            model, face, point, projection="nearest", flip=True,
        )
        self.assertEqual(
            model.FeatureManager.args,
            (32 | 256, 0.0, 64 | 1024, 0.0, 0, 0.0),
        )
        self.assertEqual(face.calls, [(False, 0)])
        self.assertEqual(point.calls, [(True, 1)])

    def test_tangent_projected_point_supports_sketch_normal_option(self):
        model = Model(); face = CylinderFace(); point = Entity()
        sw_part.reference_plane_tangent_at_projected_point(
            model, face, point, projection="sketch_normal",
        )
        self.assertEqual(
            model.FeatureManager.args,
            (32, 0.0, 64 | 2048, 0.0, 0, 0.0),
        )

    def test_curve_normal_plane_uses_perpendicular_curve_and_coincident_point(self):
        model = Model(); curve = Entity(); point = Entity()
        sw_part.reference_plane_normal_to_curve(model, curve, point, flip=True)
        self.assertEqual(
            model.FeatureManager.args,
            (2 | 256, 0.0, 4, 0.0, 0, 0.0),
        )
        self.assertEqual(curve.calls, [(False, 0)])
        self.assertEqual(point.calls, [(True, 1)])

    def test_parallel_through_point_plane_uses_two_constraints(self):
        model = Model(); plane = Entity(); point = Entity()
        sw_part.reference_plane_parallel_through_point(model, plane, point, flip=True)
        self.assertEqual(
            model.FeatureManager.args,
            (1 | 256, 0.0, 4, 0.0, 0, 0.0),
        )
        self.assertEqual(plane.calls, [(False, 0)])
        self.assertEqual(point.calls, [(True, 1)])

    def test_reference_plane_geometry_uses_transform_origin_and_normal(self):
        geometry = sw_part.reference_plane_geometry(RefPlane())
        self.assertEqual(geometry["origin"], (0.020, 0.015, 0.010))
        self.assertEqual(geometry["normal"], (1.0, 0.0, 0.0))

    def test_curve_location_plane_keeps_native_point_as_second_reference(self):
        model = Model(); curve = Entity(); point_feature = Entity(); plane_feature = object()
        with mock.patch.object(
            sw_part, "reference_point_along_curve", return_value=(point_feature,),
        ) as create_point, mock.patch.object(
            sw_part, "reference_plane_normal_to_curve", return_value=plane_feature,
        ) as create_plane:
            result = sw_part.reference_plane_normal_at_curve_location(
                model, curve, 37.5, mode="percentage", flip=True,
            )
        self.assertEqual(result, (point_feature, plane_feature))
        create_point.assert_called_once_with(
            model, curve, 37.5, mode="percentage", count=1,
        )
        create_plane.assert_called_once_with(
            model, curve, point_feature, flip=True,
        )


if __name__ == "__main__":
    unittest.main()
