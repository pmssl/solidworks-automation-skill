"""Offline contracts for native Indent features."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class SelectData:
    Mark = 0


class SelectionManager:
    def CreateSelectData(self):
        return SelectData()

    def GetSelectedObjectCount2(self, mark):
        return 2

    def GetSelectedObjectType3(self, index, mark):
        return (70, 2)[index - 1]


class Selectable:
    def __init__(self, name=""):
        self.Name = name
        self.calls = []

    def Select4(self, append, select_data):
        self.calls.append((append, select_data.Mark))
        return True


class BodySelectable:
    def __init__(self, name=""):
        self.Name = name
        self.calls = []

    def Select2(self, append, select_data):
        self.calls.append((append, select_data.Mark))
        return True


class Data:
    Thickness = 0.002
    Clearance = 0.001
    SelectionState = 1
    ClearanceDirection = True
    IsCut = False
    CutDirection = False

    def __init__(self):
        self.TargetBody = Selectable("Target")
        self.ToolBodyRegion = (Selectable("Tool Face"),)
        self.accessed = 0
        self.released = 0

    def AccessSelections(self, model, component):
        self.accessed += 1
        return True

    def ReleaseSelectionAccess(self):
        self.released += 1

    def GetBodiesCount(self):
        return 1


class Feature:
    Name = "Indent1"

    def __init__(self):
        self.data = Data()

    def GetDefinition(self):
        return self.data

    def GetErrorCode(self):
        return 0


class Manager:
    def __init__(self):
        self.args = None
        self.feature = Feature()

    def InsertIndent(self, *args):
        self.args = args
        return self.feature


class Model:
    def __init__(self):
        self.SelectionManager = SelectionManager()
        self.FeatureManager = Manager()
        self.clears = 0

    def ClearSelection2(self, all_items):
        self.clears += 1


class IndentTests(unittest.TestCase):
    def test_creates_indent_with_official_selection_marks(self):
        model = Model()
        target, tool = BodySelectable("Target"), Selectable("Tool")
        feature = sw_part.indent_feature(
            model, target, (tool,), thickness=0.002, clearance=0.001,
            exclude_selected_regions=True, clearance_direction=False,
        )
        self.assertIs(feature, model.FeatureManager.feature)
        self.assertEqual(model.FeatureManager.args, (0.002, 0.001, True, False, False, False))
        self.assertEqual(target.calls, [(False, 1)])
        self.assertEqual(tool.calls, [(True, 4)])
        self.assertEqual(model.clears, 2)

    def test_creates_cut_mode_with_required_placeholder_thickness(self):
        model = Model()
        sw_part.indent_feature(
            model, BodySelectable(), (Selectable(),), cut=True,
            thickness=0.001, clearance=0.0005, cut_direction=True,
        )
        self.assertEqual(model.FeatureManager.args, (0.001, 0.0005, True, True, True, True))

    def test_validates_required_geometry_and_values(self):
        with self.assertRaises(ValueError):
            sw_part.indent_feature(Model(), None, (Selectable(),), thickness=0.001)
        with self.assertRaises(ValueError):
            sw_part.indent_feature(Model(), BodySelectable(), (), thickness=0.001)
        with self.assertRaises(ValueError):
            sw_part.indent_feature(Model(), BodySelectable(), (Selectable(),), thickness=0.0)
        with self.assertRaises(ValueError):
            sw_part.indent_feature(Model(), BodySelectable(), (Selectable(),), thickness=0.001, clearance=-1)

    def test_reads_native_feature_data_with_selection_access(self):
        model, feature = Model(), Feature()
        evidence = sw_part.indent_feature_evidence(feature, model)
        self.assertEqual(evidence["thickness"], 0.002)
        self.assertEqual(evidence["clearance"], 0.001)
        self.assertEqual(evidence["selection_state"], 1)
        self.assertTrue(evidence["clearance_direction"])
        self.assertFalse(evidence["is_cut"])
        self.assertEqual(evidence["body_count"], 1)
        self.assertEqual(evidence["target_body"], "Target")
        self.assertEqual(evidence["tool_region_count"], 1)
        self.assertEqual(feature.data.accessed, 1)
        self.assertEqual(feature.data.released, 1)


if __name__ == "__main__":
    unittest.main()
