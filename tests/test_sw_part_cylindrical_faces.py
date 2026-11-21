"""Offline contracts for cylindrical-face semantics."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class Surface:
    IsCylinder = True
    CylinderParams = (.05, 0.0, -.015, 0.0, 0.0, 2.0, .01)


class ConeSurface:
    IsCone = True
    ConeParams2 = (.085, 0.0, .06, 0.0, 0.0, -2.0, 0.0, .19739555985, 1.0, 0.0, 0.0)


class CircleCurve:
    IsCircle = True
    CircleParams = (.05, 0.0, .015, 0.0, 0.0, 2.0, .01)


class CircleEdge:
    def __init__(self): self.calls = []
    def GetCurve(self): return CircleCurve()
    def Select2(self, append, mark): self.calls.append((append, mark)); return True


class Face:
    def __init__(self, surface=None): self.calls = []; self.surface = surface or Surface()
    def GetSurface(self): return self.surface
    def GetArea(self): return .001
    def Select2(self, append, mark): self.calls.append((append, mark)); return True


class Body:
    def __init__(self, face): self.face = face
    def GetFaces(self): return (self.face,)


class Feature:
    Name = "Axis1"
    def GetTypeName2(self): return "RefAxis"


class Manager:
    def __init__(self): self.last = None
    def GetLastFeatureAdded(self): return self.last
    def InsertReferencePoint(self, *args):
        self.reference_args = args; self.last = Feature(); return (self.last,)


class Model:
    def __init__(self): self.face = Face(); self.FeatureManager = Manager(); self.features = []
    def GetBodies2(self, _kind, _visible): return (Body(self.face),)
    def ClearSelection2(self, _all): pass
    def FirstFeature(self): return self.features[0] if self.features else None
    def InsertAxis2(self, _auto_size):
        self.FeatureManager.last = Feature(); self.features.append(self.FeatureManager.last); return True


class CylindricalFaceTests(unittest.TestCase):
    def test_geometry_normalizes_axis_and_finds_radius(self):
        model = Model(); geometry = sw_part.cylindrical_face_geometry(model.face)
        self.assertEqual(geometry["axis"], (0.0, 0.0, 1.0))
        self.assertEqual(sw_part.find_cylindrical_faces(model, radius=.01, axis=(0, 0, -1)),
                         (model.face,))

    def test_cylindrical_face_creates_single_reference_axis(self):
        model = Model(); feature = sw_part.reference_axis_from_cylindrical_face(model, model.face)
        self.assertEqual(feature.Name, "Axis1")
        self.assertEqual(model.face.calls, [(False, 0)])

    def test_conical_face_geometry_and_axis(self):
        model = Model(); face = Face(ConeSurface()); model.face = face
        geometry = sw_part.conical_face_geometry(face)
        self.assertEqual(geometry["axis"], (0.0, 0.0, -1.0))
        self.assertEqual(sw_part.find_conical_faces(model, axis=(0, 0, 1)), (face,))
        feature = sw_part.reference_axis_from_conical_face(model, face)
        self.assertEqual(feature.Name, "Axis1")

    def test_circular_edge_geometry_and_center_point(self):
        model = Model(); edge = CircleEdge()
        geometry = sw_part.circular_edge_geometry(edge)
        self.assertEqual(geometry["center"], (.05, 0.0, .015))
        point = sw_part.reference_point_edge_center(model, edge)
        self.assertEqual(point.Name, "Axis1")
        self.assertEqual(model.FeatureManager.reference_args, (3, 0, 0.0, 1))


if __name__ == "__main__":
    unittest.main()
