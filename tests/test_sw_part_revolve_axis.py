"""Offline contracts for native revolves around an independent reference axis."""

from pathlib import Path
import math
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class Feature:
    def __init__(self, name, model):
        self.Name, self.model = name, model

    def Select2(self, append, mark):
        if not append:
            self.model.selected = []
        self.model.selected.append((self.Name, mark))
        return True


class AxisSegment:
    def __init__(self, name, model, segment_type=0):
        self.Name, self.model, self.segment_type = name, model, segment_type

    def GetType(self):
        return self.segment_type

    def Select4(self, append, select_data):
        if not append:
            self.model.selected = []
        self.model.selected.append((self.Name, select_data.Mark))
        return True


class Vertex:
    def __init__(self, point):
        self.point = point

    def GetPoint(self):
        return self.point


class Edge(AxisSegment):
    def __init__(self, name, model):
        super().__init__(name, model)
        self.start, self.end = Vertex((0, 0, 0)), Vertex((0, 1, 0))

    def GetStartVertex(self):
        return self.start

    def GetEndVertex(self):
        return self.end

    def GetLength(self):
        return 1.0


class Body(AxisSegment):
    pass


class RejectBody(Body):
    def Select4(self, append, select_data):
        return False


class Extension:
    def __init__(self, model):
        self.model = model

    def SelectByID2(self, name, entity_type, _x, _y, _z, append, mark, _callout, _option):
        if not append:
            self.model.selected = []
        self.model.selected.append((name, entity_type, mark))
        return entity_type == "AXIS" and mark == 16


class SelectData:
    Mark = 0


class SelectionManager:
    def __init__(self, model):
        self.model = model

    def CreateSelectData(self):
        return SelectData()

    def GetSelectedObjectCount2(self, _mark):
        return len(self.model.selected)

    def GetSelectedObjectType3(self, index, _mark):
        selected = self.model.selected[index - 1]
        return 9 if selected[0] == "Profile" else 10

    def GetSelectedObjectMark(self, index):
        return int(self.model.selected[index - 1][-1])


class SketchManager:
    ActiveSketch = None


class Manager:
    def __init__(self, model):
        self.model, self.calls = model, []

    def FeatureRevolve2(self, *args):
        self.calls.append((args, tuple(self.model.selected)))
        return Feature("Revolve", self.model)


class Model:
    def __init__(self):
        self.selected = []
        self.profile = Feature("Profile", self)
        self.axis = Feature("AxisObject", self)
        self.axis_segment = AxisSegment("AxisSegment", self)
        self.edge = Edge("AxisEdge", self)
        self.Extension = Extension(self)
        self.SelectionManager = SelectionManager(self)
        self.SketchManager = SketchManager()
        self.FeatureManager = Manager(self)

    def FeatureByName(self, name):
        return self.profile if name == "Profile" else None

    def ClearSelection2(self, _all):
        self.selected = []


class IndependentAxisRevolveTests(unittest.TestCase):
    def test_named_reference_axis_uses_official_mark_16(self):
        model = Model()
        feature = sw_part.revolve_feature_about_axis(
            model, "Profile", "Axis1", math.pi * 1.5,
            cut=True, reverse_direction=True, merge=False,
        )
        self.assertEqual(feature.Name, "Revolve")
        args, selected = model.FeatureManager.calls[0]
        self.assertEqual(len(args), 20)
        self.assertEqual(selected, (("Profile", 0), ("Axis1", "AXIS", 16)))
        self.assertTrue(args[3])
        self.assertTrue(args[4])
        self.assertAlmostEqual(args[8], math.pi * 1.5)
        self.assertFalse(args[17])
        self.assertEqual(model.selected, [])

    def test_reference_axis_object_is_selected_with_mark_16(self):
        model = Model()
        sw_part.revolve_feature_about_axis(model, "Profile", model.axis, math.tau)
        _args, selected = model.FeatureManager.calls[0]
        self.assertEqual(selected, (("Profile", 0), ("AxisObject", 16)))

    def test_rejects_invalid_angles_and_missing_profile(self):
        model = Model()
        with self.assertRaises(ValueError):
            sw_part.revolve_feature_about_axis(model, "Profile", "Axis1", 0)
        with self.assertRaises(ValueError):
            sw_part.revolve_feature_about_axis(model, "Profile", "Axis1", math.tau + 0.01)
        with self.assertRaises(RuntimeError):
            sw_part.revolve_feature_about_axis(model, "Missing", "Axis1", math.pi)

    def test_external_sketch_segment_and_edge_use_mark_4(self):
        model = Model()
        with mock.patch.object(
            sw_part, "reference_axis_from_sketch_line", return_value=model.axis,
        ) as create_axis:
            sw_part.revolve_feature_about_sketch_segment(
                model, "Profile", model.axis_segment, math.pi,
            )
        create_axis.assert_called_once_with(model, model.axis_segment)
        _args, selected = model.FeatureManager.calls[-1]
        self.assertEqual(selected, (("Profile", 0), ("AxisObject", 16)))

        sw_part.revolve_feature_about_edge(model, "Profile", model.edge, math.pi)
        _args, selected = model.FeatureManager.calls[-1]
        self.assertEqual(selected, (("Profile", 0), ("AxisEdge", 4)))

    def test_external_axis_rejects_non_line_segment(self):
        model = Model()
        with self.assertRaises(ValueError):
            sw_part.reference_axis_from_sketch_line(
                model, AxisSegment("Spline", model, 3),
            )

    def test_two_direction_revolve_uses_independent_blind_angles(self):
        model = Model()
        feature = sw_part.revolve_feature_two_directions(
            model, "Profile", math.radians(120), math.radians(60),
            cut=True, reverse_direction=True, merge=False,
        )
        self.assertEqual(feature.Name, "Revolve")
        args, selected = model.FeatureManager.calls[-1]
        self.assertFalse(args[0])
        self.assertTrue(args[3])
        self.assertTrue(args[4])
        self.assertEqual((args[6], args[7]), (0, 0))
        self.assertAlmostEqual(args[8], math.radians(120))
        self.assertAlmostEqual(args[9], math.radians(60))
        self.assertFalse(args[17])
        self.assertEqual(selected, (("Profile", 0),))

    def test_two_direction_revolve_rejects_overlap(self):
        with self.assertRaises(ValueError):
            sw_part.revolve_feature_two_directions(
                Model(), "Profile", math.radians(240), math.radians(180),
            )

    def test_midplane_revolve_uses_total_angle_and_ignores_reverse(self):
        model = Model()
        feature = sw_part.revolve_feature_midplane(
            model, "Profile", math.radians(150), cut=True, merge=False,
        )
        self.assertEqual(feature.Name, "Revolve")
        args, selected = model.FeatureManager.calls[-1]
        self.assertTrue(args[0])
        self.assertTrue(args[1])
        self.assertFalse(args[2])
        self.assertTrue(args[3])
        self.assertFalse(args[4])
        self.assertEqual((args[6], args[7]), (6, 0))
        self.assertAlmostEqual(args[8], math.radians(150))
        self.assertEqual(args[9], 0.0)
        self.assertFalse(args[17])
        self.assertEqual(selected, (("Profile", 0),))

    def test_midplane_revolve_rejects_invalid_total_angle(self):
        with self.assertRaises(ValueError):
            sw_part.revolve_feature_midplane(Model(), "Profile", 0.0)
        with self.assertRaises(ValueError):
            sw_part.revolve_feature_midplane(
                Model(), "Profile", math.tau + 0.001,
            )

    def test_explicit_revolve_scope_selects_bodies_with_mark_1(self):
        model = Model()
        body1 = Body("Body1", model)
        body2 = Body("Body2", model)
        sw_part.revolve_feature_midplane(
            model, "Profile", math.pi,
            affected_bodies=(body1, body2),
        )
        args, selected = model.FeatureManager.calls[-1]
        self.assertTrue(args[18])
        self.assertFalse(args[19])
        self.assertEqual(
            selected,
            (("Profile", 0), ("Body1", 1), ("Body2", 1)),
        )

    def test_revolve_scope_rejects_empty_or_unselectable_bodies(self):
        model = Model()
        with self.assertRaises(ValueError):
            sw_part.revolve_feature_midplane(
                model, "Profile", math.pi, affected_bodies=(),
            )
        with self.assertRaises(RuntimeError):
            sw_part.revolve_feature_midplane(
                model, "Profile", math.pi,
                affected_bodies=(RejectBody("BadBody", model),),
            )
        self.assertEqual(model.selected, [])

    def test_midplane_thin_revolve_uses_total_thickness(self):
        model = Model()
        sw_part.revolve_thin_feature(
            model, "Profile", math.tau, 0.002, thin_type=2,
        )
        args, selected = model.FeatureManager.calls[-1]
        self.assertTrue(args[0])
        self.assertTrue(args[2])
        self.assertEqual(args[14], 2)
        self.assertEqual(args[15], 0.002)
        self.assertEqual(args[16], 0.0)
        self.assertEqual(selected, (("Profile", 0),))

    def test_two_wall_thicknesses_and_two_revolve_directions(self):
        model = Model()
        sw_part.revolve_thin_feature(
            model, "Profile", math.radians(100), 0.002,
            thin_type=3, thickness2=0.003,
            direction2_angle_rad=math.radians(80),
        )
        args, _selected = model.FeatureManager.calls[-1]
        self.assertFalse(args[0])
        self.assertAlmostEqual(args[8], math.radians(100))
        self.assertAlmostEqual(args[9], math.radians(80))
        self.assertEqual((args[14], args[15], args[16]), (3, 0.002, 0.003))

    def test_thin_revolve_rejects_invalid_wall_parameters(self):
        with self.assertRaises(ValueError):
            sw_part.revolve_thin_feature(Model(), "Profile", math.pi, 0.0)
        with self.assertRaises(ValueError):
            sw_part.revolve_thin_feature(
                Model(), "Profile", math.pi, 0.002, thin_type=3,
            )

    def test_reference_terminated_revolve_uses_mark_32_and_end_condition(self):
        model = Model()
        target = Feature("TargetPlane", model)
        sw_part.revolve_feature_to_reference(
            model, "Profile", target, "up_to_surface",
            reverse_direction=True, merge=False,
        )
        args, selected = model.FeatureManager.calls[-1]
        self.assertEqual(selected, (("Profile", 0), ("TargetPlane", 32)))
        self.assertTrue(args[0])
        self.assertTrue(args[4])
        self.assertEqual(args[6], 4)
        self.assertEqual(args[12], 0.0)
        self.assertFalse(args[17])

    def test_offset_revolve_uses_distance_and_reverse_flag(self):
        model = Model()
        target = Feature("TargetPlane", model)
        sw_part.revolve_feature_to_reference(
            model, "Profile", target, 5,
            offset_distance=0.003, offset_reverse=True,
        )
        args, _selected = model.FeatureManager.calls[-1]
        self.assertEqual(args[6], 5)
        self.assertTrue(args[10])
        self.assertEqual(args[12], 0.003)

    def test_reference_terminated_revolve_validates_offset_semantics(self):
        target = Feature("TargetPlane", Model())
        with self.assertRaises(ValueError):
            sw_part.revolve_feature_to_reference(
                Model(), "Profile", target, "offset_from_surface",
            )
        with self.assertRaises(ValueError):
            sw_part.revolve_feature_to_reference(
                Model(), "Profile", target, "up_to_vertex", offset_distance=0.001,
            )

    def test_two_direction_revolve_selects_shared_reference_once(self):
        model = Model()
        target = Feature("TargetPlane", model)
        sw_part.revolve_feature_two_directions_to_same_reference(
            model, "Profile", target, "up_to_surface", cut=True, merge=False,
        )
        args, selected = model.FeatureManager.calls[-1]
        self.assertEqual(selected, (("Profile", 0), ("TargetPlane", 32)))
        self.assertFalse(args[0])
        self.assertTrue(args[3])
        self.assertTrue(args[5])
        self.assertEqual((args[6], args[7]), (4, 4))
        self.assertEqual((args[8], args[9]), (0.0, 0.0))
        self.assertFalse(args[17])
        self.assertEqual(model.selected, [])

    def test_two_direction_offset_revolve_keeps_independent_offsets(self):
        model = Model()
        target = Feature("TargetPlane", model)
        sw_part.revolve_feature_two_directions_to_same_reference(
            model, "Profile", target, 5,
            offset_distance1=0.002, offset_distance2=0.003,
            offset_reverse1=True, offset_reverse2=False,
        )
        args, _selected = model.FeatureManager.calls[-1]
        self.assertEqual((args[6], args[7]), (5, 5))
        self.assertEqual((args[10], args[11]), (True, False))
        self.assertEqual((args[12], args[13]), (0.002, 0.003))

    def test_shared_reference_allows_different_direction_conditions(self):
        model = Model()
        target = Feature("TargetPlane", model)
        sw_part.revolve_feature_two_directions_to_same_reference(
            model, "Profile", target, "up_to_surface",
            direction2_end_condition="offset_from_surface",
            offset_distance2=0.004, offset_reverse2=True,
        )
        args, selected = model.FeatureManager.calls[-1]
        self.assertEqual(selected, (("Profile", 0), ("TargetPlane", 32)))
        self.assertEqual((args[6], args[7]), (4, 5))
        self.assertEqual((args[10], args[11]), (False, True))
        self.assertEqual((args[12], args[13]), (0.0, 0.004))
        self.assertTrue(args[5])

    def test_two_direction_reference_revolve_validates_offsets(self):
        model = Model()
        target = Feature("TargetPlane", model)
        with self.assertRaises(ValueError):
            sw_part.revolve_feature_two_directions_to_same_reference(
                model, "Profile", target, "offset_from_surface",
                offset_distance1=0.001,
            )
        with self.assertRaises(ValueError):
            sw_part.revolve_feature_two_directions_to_same_reference(
                model, "Profile", target, "up_to_surface",
                offset_distance1=0.001, offset_distance2=0.001,
            )

    def test_two_distinct_references_use_marks_32_and_64(self):
        model = Model()
        target1 = Feature("TargetPlane1", model)
        target2 = Feature("TargetPlane2", model)
        sw_part.revolve_feature_two_references(
            model, "Profile", target1, target2,
            "up_to_surface", "offset_from_surface",
            offset_distance2=0.006, offset_reverse2=True,
            cut=True, merge=False,
        )
        args, selected = model.FeatureManager.calls[-1]
        self.assertEqual(
            selected,
            (("Profile", 0), ("TargetPlane1", 32), ("TargetPlane2", 64)),
        )
        self.assertFalse(args[0])
        self.assertTrue(args[3])
        self.assertFalse(args[5])
        self.assertEqual((args[6], args[7]), (4, 5))
        self.assertEqual((args[10], args[11]), (False, True))
        self.assertEqual((args[12], args[13]), (0.0, 0.006))
        self.assertFalse(args[17])
        self.assertEqual(model.selected, [])

    def test_two_reference_revolve_rejects_invalid_offset_semantics(self):
        model = Model()
        target1 = Feature("TargetPlane1", model)
        target2 = Feature("TargetPlane2", model)
        with self.assertRaises(ValueError):
            sw_part.revolve_feature_two_references(
                model, "Profile", target1, target2,
                "up_to_surface", "offset_from_surface",
            )
        with self.assertRaises(ValueError):
            sw_part.revolve_feature_two_references(
                model, "Profile", target1, target2,
                "up_to_surface", "up_to_vertex",
                offset_distance1=0.001,
            )

    def test_blind_direction1_and_reference_direction2_use_mark_64(self):
        model = Model()
        target = Feature("TargetPlane", model)
        sw_part.revolve_feature_blind_and_reference(
            model, "Profile", math.radians(45), target, "up_to_surface",
            blind_in_direction1=True, cut=True,
        )
        args, selected = model.FeatureManager.calls[-1]
        self.assertEqual(selected, (("Profile", 0), ("TargetPlane", 64)))
        self.assertFalse(args[0])
        self.assertTrue(args[3])
        self.assertFalse(args[5])
        self.assertEqual((args[6], args[7]), (0, 4))
        self.assertAlmostEqual(args[8], math.radians(45))
        self.assertEqual(args[9], 0.0)

    def test_reference_direction1_and_blind_direction2_use_mark_32(self):
        model = Model()
        target = Feature("TargetPlane", model)
        sw_part.revolve_feature_blind_and_reference(
            model, "Profile", math.radians(30), target,
            "offset_from_surface", blind_in_direction1=False,
            offset_distance=0.002, offset_reverse=True,
        )
        args, selected = model.FeatureManager.calls[-1]
        self.assertEqual(selected, (("Profile", 0), ("TargetPlane", 32)))
        self.assertEqual((args[6], args[7]), (5, 0))
        self.assertEqual((args[8], args[9]), (0.0, math.radians(30)))
        self.assertEqual((args[10], args[11]), (True, False))
        self.assertEqual((args[12], args[13]), (0.002, 0.0))

    def test_mixed_revolve_validates_blind_angle_and_offset(self):
        model = Model()
        target = Feature("TargetPlane", model)
        with self.assertRaises(ValueError):
            sw_part.revolve_feature_blind_and_reference(
                model, "Profile", 0.0, target, "up_to_surface",
            )
        with self.assertRaises(ValueError):
            sw_part.revolve_feature_blind_and_reference(
                model, "Profile", math.pi, target, "offset_from_surface",
            )
        with self.assertRaises(ValueError):
            sw_part.revolve_feature_blind_and_reference(
                model, "Profile", math.pi, target, "up_to_surface",
                offset_distance=0.001,
            )


if __name__ == "__main__":
    unittest.main()
