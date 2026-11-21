"""Offline contracts for native Dome features."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class Face:
    def __init__(self):
        self.calls = []

    def Select4(self, append, select_data):
        self.calls.append((append, select_data.Mark))
        return True


class SelectData:
    Mark = 0


class SelectionManager:
    def __init__(self):
        self.selected_types = []

    def CreateSelectData(self):
        return SelectData()

    def GetSelectedObjectCount2(self, mark):
        return 1

    def GetSelectedObjectType3(self, index, mark):
        return 2


class Data:
    Height = 0.012
    ReverseDir = False
    Elliptical = True
    ConstraintPointOrSketch = None
    Direction = None

    def __init__(self):
        self.accessed = 0
        self.released = 0

    def AccessSelections(self, model, component):
        self.accessed += 1
        return True

    def ReleaseSelectionAccess(self):
        self.released += 1

    def GetFaceCount(self):
        return 2


class Feature:
    def __init__(self, name, type_name, data=None):
        self.Name = name
        self._type_name = type_name
        self._data = data
        self.modified = None

    def GetTypeName2(self):
        return self._type_name

    def GetDefinition(self):
        return self._data

    def GetErrorCode(self):
        return 0

    def GetNextFeature(self):
        return None

    def ModifyDefinition(self, data, model, component):
        self.modified = (data, model, component)
        return True


class Manager:
    def __init__(self):
        self.last = None

    def GetLastFeatureAdded(self):
        return self.last


class Model:
    def __init__(self):
        self.FeatureManager = Manager()
        self.SelectionManager = SelectionManager()
        self.base = Feature("Boss-Extrude1", "Extrusion")
        self.args = None
        self.clears = 0

    def ClearSelection2(self, all_items):
        self.clears += 1

    def FirstFeature(self):
        return self.base

    def InsertDome(self, *args):
        self.args = args
        self.FeatureManager.last = Feature("Dome1", "Dome", Data())


class DomeTests(unittest.TestCase):
    def test_creates_native_dome_on_multiple_faces(self):
        model, first, second = Model(), Face(), Face()
        feature = sw_part.dome_feature(
            model, (first, second), 0.012,
            reverse_direction=True, elliptical=True,
        )
        self.assertIs(feature, model.FeatureManager.last)
        self.assertEqual(model.args, (0.012, True, True))
        self.assertEqual(first.calls, [(False, 1)])
        self.assertEqual(second.calls, [(True, 1)])
        self.assertEqual(model.clears, 2)

    def test_validates_faces_and_height(self):
        with self.assertRaises(ValueError):
            sw_part.dome_feature(Model(), (), 0.01)
        with self.assertRaises(ValueError):
            sw_part.dome_feature(Model(), (Face(),), 0.0)

    def test_rejects_missing_new_feature(self):
        model = Model()
        model.InsertDome = lambda *args: None
        with self.assertRaises(RuntimeError):
            sw_part.dome_feature(model, (Face(),), 0.01)

    def test_reads_native_feature_data(self):
        evidence = sw_part.dome_feature_evidence(
            Feature("Dome1", "Dome", Data()),
        )
        self.assertEqual(evidence["height"], 0.012)
        self.assertFalse(evidence["reverse_direction"])
        self.assertTrue(evidence["elliptical"])
        self.assertEqual(evidence["face_count"], 2)
        self.assertFalse(evidence["has_constraint"])
        self.assertFalse(evidence["has_direction"])
        self.assertEqual(evidence["error_code"], 0)

    def test_updates_native_feature_data_and_releases_access(self):
        data = Data()
        feature = Feature("Dome1", "Dome", data)
        model, constraint, direction = Model(), object(), object()
        result = sw_part.update_dome_feature(
            feature, model, height=0.02, reverse_direction=True,
            elliptical=False, constraint=constraint, direction=direction,
        )
        self.assertIs(result, feature)
        self.assertEqual(data.Height, 0.02)
        self.assertTrue(data.ReverseDir)
        self.assertFalse(data.Elliptical)
        self.assertIs(data.ConstraintPointOrSketch, constraint)
        self.assertIs(data.Direction, direction)
        self.assertEqual(data.accessed, 1)
        self.assertEqual(data.released, 1)
        self.assertIs(feature.modified[0], data)


if __name__ == "__main__":
    unittest.main()
