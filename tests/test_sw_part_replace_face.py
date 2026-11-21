"""Offline contract for native Replace Face."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class Selectable:
    def __init__(self): self.calls = []
    def Select2(self, append, mark): self.calls.append((append, mark)); return True


class Feature:
    Name = "Replace Face1"
    def GetTypeName2(self): return "ReplaceFace"


class Manager:
    def __init__(self): self.last = Feature()
    def GetLastFeatureAdded(self): return self.last


class Model:
    def __init__(self): self.FeatureManager = Manager(); self.called = 0
    def ClearSelection2(self, _all): pass
    def FirstFeature(self): return None
    def InsertFeatureReplaceFace(self): self.called += 1


class ReplaceFaceTests(unittest.TestCase):
    def test_replace_face_uses_marks_one_and_two(self):
        model = Model(); target = Selectable(); surface = Selectable()
        feature = sw_part.replace_faces(model, target, surface)
        self.assertIs(feature, model.FeatureManager.last)
        self.assertEqual(target.calls, [(False, 1)])
        self.assertEqual(surface.calls, [(True, 2)])
        self.assertEqual(model.called, 1)

    def test_replace_face_requires_targets(self):
        with self.assertRaises(ValueError): sw_part.replace_faces(Model(), (), Selectable())


if __name__ == "__main__":
    unittest.main()
