"""Offline regression tests for semantic planar-face selection and shell."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class Surface:
    IsPlane = True
    PlaneParams = (0, 1, 0, -0.02, 0.01, -0.015)


class Face:
    def __init__(self, model, center_y):
        self.model = model
        self.center_y = center_y

    def GetSurface(self): return Surface()
    @property
    def Normal(self): return (0, 1, 0)
    def GetArea(self): return 0.0012
    def GetBox(self): return (-0.02, self.center_y, -0.015, 0.02, self.center_y, 0.015)
    def Select2(self, append, mark):
        if not append: self.model.selected = []
        self.model.selected.append(self)
        return mark == 0


class Body:
    def __init__(self, faces): self.faces = faces
    def GetFaces(self): return self.faces


class Manager:
    def __init__(self, model): self.model = model; self.calls = []; self.last = None
    def GetLastFeatureAdded(self): return self.last


class Model:
    def __init__(self):
        self.selected = []
        self.faces = [Face(self, -0.01), Face(self, 0.01)]
        self.body = Body(self.faces)
        self.FeatureManager = Manager(self)
    def GetBodies2(self, _kind, _visible): return [self.body]
    def ClearSelection2(self, _all): self.selected = []
    def InsertFeatureShell(self, thickness, outward):
        self.FeatureManager.calls.append((thickness, outward, tuple(self.selected)))
        self.FeatureManager.last = object()
        return True


class ShellTests(unittest.TestCase):
    def test_semantic_face_resolution_and_explicit_shell_selection(self):
        model = Model()
        faces = sw_part.find_planar_faces(
            model, area=0.0012, center=(0, 0.01, 0), normal=(0, -1, 0)
        )
        self.assertEqual(faces, (model.faces[1],))
        sw_part.shell(model, 0.002, faces, outward=True)
        self.assertEqual(model.FeatureManager.calls[0], (0.002, True, (model.faces[1],)))
        self.assertEqual(model.selected, [])

    def test_shell_rejects_invalid_thickness_and_empty_face_list(self):
        with self.assertRaises(ValueError): sw_part.shell(Model(), 0)
        with self.assertRaises(ValueError): sw_part.shell(Model(), 0.002, [])


if __name__ == "__main__":
    unittest.main()
