"""Offline contract tests for the native HoleWizard5 simple-hole whitelist."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class SelectData:
    X = Y = Z = 0.0
    Mark = 0


class SelectionManager:
    def CreateSelectData(self): return SelectData()


class Face:
    def __init__(self): self.selection = None
    def Select4(self, append, data):
        self.selection = (append, data.X, data.Y, data.Z, data.Mark)
        return True


class Manager:
    def __init__(self): self.calls = []
    def HoleWizard5(self, *args): self.calls.append(args); return object()


class Model:
    def __init__(self):
        self.SelectionManager = SelectionManager()
        self.FeatureManager = Manager()
    def ClearSelection2(self, _all): pass


class HoleWizardTests(unittest.TestCase):
    def test_simple_through_hole_uses_explicit_point_and_27_arguments(self):
        model, face = Model(), Face()
        sw_part.hole_wizard_simple(
            model, face, (0.01, -0.02, 0.03), 0.006, through=True
        )
        self.assertEqual(face.selection, (False, 0.01, -0.02, 0.03, 0))
        args = model.FeatureManager.calls[0]
        self.assertEqual(len(args), 27)
        self.assertEqual(args[:7], (2, 1, 39, "", 1, 0.006, 0.006))
        self.assertEqual(args[-7:], ("", False, True, True, False, False, False))

    def test_blind_hole_requires_positive_depth(self):
        with self.assertRaises((TypeError, ValueError)):
            sw_part.hole_wizard_simple(Model(), Face(), (0, 0, 0), 0.006)
        with self.assertRaises(ValueError):
            sw_part.hole_wizard_simple(Model(), Face(), (0, 0, 0), -0.006, through=True)


if __name__ == "__main__":
    unittest.main()
