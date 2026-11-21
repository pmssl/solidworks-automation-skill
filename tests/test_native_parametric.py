"""Pure-Python contract tests; real COM smoke test is documented separately."""

import math
import os
import unittest

from scripts.sw_native_parametric import NativeParametric


class Point:
    def __init__(self, x, y):
        self.X, self.Y = x, y


class Segment:
    def __init__(self, a, b):
        self.a, self.b = Point(*a), Point(*b)
        self.ConstructionGeometry = False

    def GetStartPoint2(self):
        return self.a

    def GetEndPoint2(self):
        return self.b

    def Select4(self, append, callout):
        assert append is False
        assert callout is not None
        return True

    def GetType(self):
        return 0


class ArcSegment(Segment):
    def __init__(self, center, radius, start=None, end=None):
        start = start or (center[0] + radius, center[1])
        end = end or start
        super().__init__(start, end)
        self.center = Point(*center)
        self.radius = radius

    def GetType(self):
        return 1

    def GetCenterPoint2(self):
        return self.center

    def GetRadius(self):
        return self.radius


class SplineSegment(Segment):
    def GetType(self):
        return 3


class Sketch:
    def __init__(self):
        self.segments = []
        self.dim_count = 0

    def GetSketchSegments(self):
        return self.segments

    def GetConstrainedStatus(self):
        return 3 if self.dim_count == 2 else 2


class Feature:
    def __init__(self, name, typ, sketch=None):
        self.Name, self.typ, self.sketch = name, typ, sketch
        self.next = None

    def GetNextFeature(self):
        return self.next

    def GetFirstSubFeature(self):
        return None

    def GetTypeName2(self):
        return self.typ

    def GetSpecificFeature2(self):
        return self.sketch

    def GetErrorCode2(self):
        return 0

    def GetErrorCode(self):
        return 0

    def GetDefinition(self):
        return getattr(self, "definition", None)

    def Select2(self, *_):
        return True


class SketchManager:
    def __init__(self, model):
        self.model = model
        self.ActiveSketch = None
        self.AddToDB = False

    def CreateCenterRectangle(self, x1, y1, z1, x2, y2, z2):
        seg = [Segment((-x2, -y2), (x2, -y2)),
               Segment((x2, -y2), (x2, y2)),
               Segment((x2, y2), (-x2, y2)),
               Segment((-x2, y2), (-x2, -y2))]
        self.ActiveSketch.segments.extend(seg)
        return seg

    def CreateLine(self, x1, y1, z1, x2, y2, z2):
        segment = Segment((x1, y1), (x2, y2))
        self.ActiveSketch.segments.append(segment)
        return segment

    def CreateCornerRectangle(self, x1, y1, z1, x2, y2, z2):
        segments = [Segment((x1, y1), (x2, y1)),
                    Segment((x2, y1), (x2, y2)),
                    Segment((x2, y2), (x1, y2)),
                    Segment((x1, y2), (x1, y1))]
        self.ActiveSketch.segments.extend(segments)
        return segments

    def CreateCircleByRadius(self, cx, cy, cz, radius):
        segment = ArcSegment((cx, cy), radius)
        self.ActiveSketch.segments.append(segment)
        return segment

    def CreateArc(self, cx, cy, cz, sx, sy, sz, ex, ey, ez, direction):
        segment = ArcSegment((cx, cy), math.hypot(sx - cx, sy - cy),
                             (sx, sy), (ex, ey))
        self.ActiveSketch.segments.append(segment)
        return segment

    def CreatePolygon(self, cx, cy, cz, px, py, pz, sides, inscribed):
        radius = math.hypot(px - cx, py - cy)
        points = [(cx + radius * math.cos(2 * math.pi * i / sides),
                   cy + radius * math.sin(2 * math.pi * i / sides))
                  for i in range(sides)]
        segments = [Segment(points[i], points[(i + 1) % sides]) for i in range(sides)]
        self.ActiveSketch.segments.extend(segments)
        return segments


class SwApp:
    def __init__(self):
        self.input_dim_on_create = False

    def GetUserPreferenceToggle(self, preference):
        assert preference == 10
        return self.input_dim_on_create

    def SetUserPreferenceToggle(self, preference, value):
        assert preference == 10
        self.input_dim_on_create = bool(value)


class Dimension:
    DrivenState = 2
    FullName = "D1@Sketch1"

    def __init__(self, sketch):
        self.sketch = sketch
        self._value = 0

    @property
    def SystemValue(self):
        return self._value

    @SystemValue.setter
    def SystemValue(self, value):
        self._value = value
        self.sketch.dim_count += 1


class DisplayDimension:
    def __init__(self, sketch):
        self.sketch = sketch

    def GetDimension2(self, _):
        return Dimension(self.sketch)


class Model:
    def __init__(self, title="Part1"):
        self.title, self.path = title, ""
        self.features = [Feature("Front Plane", "RefPlane")]
        self.SketchManager = SketchManager(self)
        self.bodies = []

    def GetTitle(self):
        return self.title

    def GetPathName(self):
        return self.path

    def GetType(self):
        return 1

    def FirstFeature(self):
        for left, right in zip(self.features, self.features[1:]):
            left.next = right
        self.features[-1].next = None
        return self.features[0]

    def ClearSelection2(self, _):
        pass

    def AddDimension2(self, *_):
        return DisplayDimension(self.SketchManager.ActiveSketch)

    def ForceRebuild3(self, _):
        return True

    def GetBodies2(self, *_):
        return self.bodies


class PropertyModel(Model):
    """Match pywin32 builds that expose no-arg COM getters as properties."""

    @property
    def GetTitle(self):
        return self.title

    @property
    def GetPathName(self):
        return self.path

    @property
    def GetType(self):
        return 1


class PseudoPropertyInt(int):
    def __call__(self):
        raise RuntimeError("(-2147352573, '找不到成员。', None, None)")


class PseudoPropertyModel(Model):
    """Match pywin32 pseudo-properties that misleadingly advertise __call__."""

    @property
    def GetType(self):
        return PseudoPropertyInt(1)


class PartOps:
    @staticmethod
    def start_sketch(model, plane):
        assert plane == "Front Plane"
        sketch = Sketch()
        index = 1 + sum(feature.typ == "ProfileFeature" for feature in model.features)
        model.features.append(Feature(f"Sketch{index}", "ProfileFeature", sketch))
        model.SketchManager.ActiveSketch = sketch

    @staticmethod
    def start_sketch_on_largest_planar_face(model):
        PartOps.start_sketch(model, "Front Plane")

    @staticmethod
    def end_sketch(model):
        model.SketchManager.ActiveSketch = None

    @staticmethod
    def extrude_boss(model, sketch_name, depth, direction=True, draft_angle=0.0,
                     draft_outward=True):
        assert sketch_name == "Sketch1" and abs(depth - 0.02) < 1e-9
        f = Feature("Boss-Extrude1", "Boss")
        model.features.append(f)
        model.bodies.append(object())
        return f

    @staticmethod
    def sketch_slot(model, x1, y1, x2, y2, radius):
        segments = [Segment((x1, y1 + radius), (x2, y2 + radius)),
                    Segment((x2, y2 - radius), (x1, y1 - radius)),
                    ArcSegment((x1, y1), radius),
                    ArcSegment((x2, y2), radius)]
        model.SketchManager.ActiveSketch.segments.extend(segments)
        return segments

    @staticmethod
    def sketch_spline(model, points):
        segment = SplineSegment(points[0], points[-1])
        model.SketchManager.ActiveSketch.segments.append(segment)
        return segment

    @staticmethod
    def revolve_feature(model, sketch_name, angle, cut=False,
                        reverse_direction=False, merge=True):
        assert sketch_name == "Sketch1"
        feature = Feature("Revolve1", "Revolution")
        feature.definition = RevolveDefinition(angle, cut, reverse_direction)
        model.features.append(feature)
        if not cut:
            model.bodies.append(object())
        return feature

    @staticmethod
    def sweep_feature(model, profile_sketch_name, path_sketch_name, cut=False,
                      merge=True):
        assert profile_sketch_name == "Sketch1"
        assert path_sketch_name == "Sketch2"
        feature = Feature("Sweep1", "Sweep")
        feature.definition = SweepDefinition(cut, merge)
        model.features.append(feature)
        if not cut:
            model.bodies.append(object())
        return feature

    @staticmethod
    def offset_plane(model, base_plane_name, distance, reverse_direction=False):
        assert base_plane_name == "Front Plane"
        feature = Feature("Plane1", "RefPlane")
        feature.definition = PlaneDefinition(distance, reverse_direction)
        model.features.append(feature)
        return feature

    @staticmethod
    def loft_feature(model, section_sketch_names, cut=False, merge=True):
        assert section_sketch_names == ["Sketch1", "Sketch2"]
        feature = Feature("Loft1", "Blend")
        feature.definition = LoftDefinition(len(section_sketch_names), cut, merge)
        model.features.append(feature)
        if not cut:
            model.bodies.append(object())
        return feature


class RevolveDefinition:
    def __init__(self, angle, cut, reverse_direction):
        self.angle = angle
        self.cut = cut
        self.ReverseDirection = reverse_direction

    def GetRevolutionAngle(self, forward):
        assert forward is True
        return self.angle

    def IsBossFeature(self):
        return not self.cut


class SweepDefinition:
    TwistControlType = 0

    def __init__(self, cut, merge):
        self.cut = cut
        self.Merge = merge

    def IsBossFeature(self):
        return not self.cut

    def GetProfileType(self):
        return 0

    def GetPathType(self):
        return 0


class PlaneDefinition:
    def __init__(self, distance, reverse_direction):
        self.Distance = distance
        self.ReverseDirection = reverse_direction


class LoftDefinition:
    Close = False
    MaintainTangency = False

    def __init__(self, count, cut, merge):
        self.count = count
        self.cut = cut
        self.Merge = merge

    def GetProfileCount(self):
        return self.count

    def IsBossFeature(self):
        return not self.cut


class NativeTests(unittest.TestCase):
    def setUp(self):
        self._old_pref = os.environ.get("SW_NATIVE_DIM_DIALOG_DISABLED")
        os.environ["SW_NATIVE_DIM_DIALOG_DISABLED"] = "1"
        self.model = Model("Part1")
        self.sw = SwApp()
        self.engine = NativeParametric(lambda: (self.sw, self.model), lambda: PartOps)

    def tearDown(self):
        if self._old_pref is None:
            os.environ.pop("SW_NATIVE_DIM_DIALOG_DISABLED", None)
        else:
            os.environ["SW_NATIVE_DIM_DIALOG_DISABLED"] = self._old_pref

    def test_full_stepwise_workflow(self):
        begun = self.engine.begin("Part1", "Front Plane")
        token = begun["session_id"]
        self.assertEqual(begun["sketch"], "Sketch1")
        self.engine.rectangle(token, 100, 60)
        self.assertFalse(self.engine.status(token)["fully_defined"])
        self.engine.dimension(token, "horizontal", 100)
        self.engine.dimension(token, "vertical", 60)
        self.assertTrue(self.engine.status(token)["fully_defined"])
        self.engine.finish(token)
        created = self.engine.extrude(token, 20)
        self.assertEqual(created["feature"], "Boss-Extrude1")
        state = self.engine.model_state(token)
        self.assertEqual(state["solid_body_count"], 1)
        self.assertIn("Sketch1", [f["name"] for f in state["features"]])

    def test_document_switch_is_blocked(self):
        token = self.engine.begin("Part1", "Front Plane")["session_id"]
        self.model.title = "unrelated_model.SLDPRT"
        with self.assertRaisesRegex(RuntimeError, "Active document changed"):
            self.engine.rectangle(token, 100, 60)

    def test_under_defined_cannot_finish_or_extrude(self):
        token = self.engine.begin("Part1", "Front Plane")["session_id"]
        self.engine.rectangle(token, 100, 60)
        with self.assertRaisesRegex(RuntimeError, "not fully defined"):
            self.engine.finish(token)
        self.engine.finish(token, require_fully_defined=False)
        with self.assertRaisesRegex(RuntimeError, "not verifiably fully defined"):
            self.engine.extrude(token, 20)

    def test_wrong_session_or_title_is_blocked(self):
        with self.assertRaisesRegex(RuntimeError, "not"):
            self.engine.begin("OtherPart", "Front Plane")
        self.engine.begin("Part1", "Front Plane")
        with self.assertRaisesRegex(RuntimeError, "No matching"):
            self.engine.dimension("invalid-token-123456", "horizontal", 100)

    def test_property_style_no_arg_com_getters(self):
        self.model = PropertyModel("PropertyPart")
        self.engine = NativeParametric(lambda: (self.sw, self.model), lambda: PartOps)
        begun = self.engine.begin("PropertyPart", "Front Plane")
        self.assertEqual(begun["sketch"], "Sketch1")

    def test_callable_pseudo_property_member_not_found_fallback(self):
        self.model = PseudoPropertyModel("PseudoPropertyPart")
        self.engine = NativeParametric(lambda: (self.sw, self.model), lambda: PartOps)
        begun = self.engine.begin("PseudoPropertyPart", "Front Plane")
        self.assertEqual(begun["sketch"], "Sketch1")

    def test_begin_on_largest_planar_face_route(self):
        begun = self.engine.begin("Part1", "largest_planar_face")
        self.assertEqual(begun["sketch"], "Sketch1")

    def test_concentric_rectangle_pair(self):
        token = self.engine.begin("Part1", "Front Plane")["session_id"]
        result = self.engine.rectangle_pair(token, 39, 39, 27, 25)
        self.assertEqual(result["outer_mm"], [39, 39])
        self.assertEqual(result["inner_mm"], [27, 25])
        self.assertEqual(len(result["driving_dimensions"]), 4)
        self.assertEqual(len(self.model.SketchManager.ActiveSketch.segments), 8)

    def test_native_sketch_primitives_and_geometry(self):
        token = self.engine.begin("Part1", "Front Plane")["session_id"]
        self.engine.line(token, -10, 0, 10, 0)
        self.engine.corner_rectangle(token, -20, -10, 20, 10)
        self.engine.circle(token, 0, 0, 5)
        self.engine.arc(token, 0, 0, 10, 0, 0, 10)
        self.engine.polygon(token, 0, 0, 8, 6)
        self.engine.straight_slot(token, -15, 20, 15, 20, 6)
        self.engine.spline(token, [(-10, -20), (0, -25), (10, -20)])
        geometry = self.engine.geometry(token)
        self.assertEqual(geometry["segment_count"], 18)
        self.assertEqual(geometry["segments"][0]["type"], "line")
        self.assertEqual(geometry["segments"][5]["radius_mm"], 5.0)

    def test_native_revolve_requires_and_reads_construction_axis(self):
        token = self.engine.begin("Part1", "Front Plane")["session_id"]
        self.engine.corner_rectangle(token, 10, -5, 20, 5)
        axis = self.engine.line(token, 0, -25, 0, 25, construction=True)
        self.assertTrue(axis["created_segments"][0]["construction"])
        self.model.SketchManager.ActiveSketch.dim_count = 2
        self.engine.finish(token)
        result = self.engine.revolve(token, 270, reverse_direction=True)
        self.assertEqual(result["feature"], "Revolve1")
        self.assertAlmostEqual(result["angle_deg"], 270)
        self.assertTrue(result["reverse_direction"])
        self.assertFalse(result["cut"])
        self.assertEqual(result["solid_body_count"], 1)

    def test_native_sweep_uses_previous_profile_and_current_path(self):
        profile_token = self.engine.begin("Part1", "Front Plane")["session_id"]
        self.engine.circle(profile_token, 0, 0, 3)
        self.model.SketchManager.ActiveSketch.dim_count = 2
        self.engine.finish(profile_token)
        path_token = self.engine.begin("Part1", "Front Plane")["session_id"]
        self.engine.line(path_token, 0, 0, 40, 0)
        self.model.SketchManager.ActiveSketch.dim_count = 2
        self.engine.finish(path_token)
        result = self.engine.sweep(path_token, "Sketch1")
        self.assertEqual(result["feature"], "Sweep1")
        self.assertEqual(result["profile_sketch"], "Sketch1")
        self.assertEqual(result["path_sketch"], "Sketch2")
        self.assertFalse(result["cut"])
        self.assertEqual(result["solid_body_count"], 1)

    def test_offset_plane_and_native_loft(self):
        plane = self.engine.offset_plane("Part1", "Front Plane", 37, True)
        self.assertEqual(plane["feature"], "Plane1")
        self.assertAlmostEqual(plane["offset_mm"], 37)
        self.assertTrue(plane["reverse_direction"])
        first = self.engine.begin("Part1", "Front Plane")
        self.engine.circle(first["session_id"], 0, 0, 5)
        self.model.SketchManager.ActiveSketch.dim_count = 2
        self.engine.finish(first["session_id"])
        second = self.engine.begin("Part1", "Front Plane")
        self.engine.circle(second["session_id"], 0, 0, 3)
        self.model.SketchManager.ActiveSketch.dim_count = 2
        self.engine.finish(second["session_id"])
        result = self.engine.loft(
            second["session_id"], [first["sketch"], second["sketch"]]
        )
        self.assertEqual(result["feature"], "Loft1")
        self.assertEqual(result["profile_count"], 2)
        self.assertFalse(result["cut"])
        self.assertEqual(result["solid_body_count"], 1)


if __name__ == "__main__":
    unittest.main()
