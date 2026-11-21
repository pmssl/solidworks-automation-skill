"""Offline contracts for native Delete Face."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class Feature:
    def __init__(self, name, kind): self.Name, self.kind = name, kind
    def GetTypeName2(self): return self.kind
    def GetNextFeature(self): return None


class Face:
    def __init__(self): self.calls = []
    def Select2(self, append, mark): self.calls.append((append, mark)); return mark == 0


class Manager:
    def __init__(self, feature): self.feature = feature
    def GetLastFeatureAdded(self): return self.feature


class Extension:
    def __init__(self, model): self.model = model
    def InsertDeleteFace(self, option): self.model.option = option; return True


class Model:
    def __init__(self):
        self.before = Feature("Boss-Extrude1", "Boss")
        self.after = Feature("DeleteFace1", "DeleteFace")
        self.FeatureManager = Manager(self.after)
        self.heal = None
        self.option = None
    def ClearSelection2(self, _all): pass
    def FirstFeature(self): return self.before
    def InsertDeleteFace2(self, heal): self.heal = heal; return None


class DeleteFaceTests(unittest.TestCase):
    def test_delete_without_heal(self):
        model, face = Model(), Face()
        feature = sw_part.delete_faces(model, face)
        self.assertIs(feature, model.after)
        self.assertFalse(model.heal)
        self.assertEqual(face.calls, [(False, 0)])

    def test_empty_selection(self):
        with self.assertRaises(ValueError): sw_part.delete_faces(Model(), ())

    def test_delete_and_patch_requests_refill(self):
        model, face = Model(), Face()
        model.Extension = Extension(model)
        feature = sw_part.delete_faces(model, face, heal=True)
        self.assertIs(feature, model.after)
        self.assertEqual(model.option, 1)
        self.assertIsNone(model.heal)

    def test_delete_and_fill_uses_modern_option(self):
        model, face = Model(), Face(); model.Extension = Extension(model)
        sw_part.delete_faces(model, face, mode="fill")
        self.assertEqual(model.option, 2)

    def test_delete_and_tangent_fill_uses_modern_option(self):
        model, face = Model(), Face(); model.Extension = Extension(model)
        sw_part.delete_faces(model, face, mode="fill_tangent")
        self.assertEqual(model.option, 3)

    def test_rejects_conflicting_delete_modes(self):
        with self.assertRaises(ValueError):
            sw_part.delete_faces(Model(), Face(), heal=True, mode="fill")


if __name__ == "__main__":
    unittest.main()
