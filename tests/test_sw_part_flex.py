"""Offline contracts for native Flex features."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class SelectionManager:
    def __init__(self):
        self.select_data = None

    def CreateSelectData(self):
        self.select_data = SelectData()
        return self.select_data

    def GetSelectedObjectCount2(self, mark):
        return 1

    def GetSelectedObjectType3(self, index, mark):
        return 76


class SelectData:
    Mark = None


class Body:
    def __init__(self):
        self.calls = []

    def Select2(self, append, select_data):
        self.calls.append((append, select_data))
        return True

    def GetMassProperties(self, density):
        return (0.0, 0.0, 0.0, 0.00001)

    def GetBodyBox(self):
        return (-.01, -.01, -.05, .01, .01, .05)


class Feature:
    Name = "Flex1"

    def __init__(self):
        self.display_dimension = DisplayDimension()

    def GetTypeName2(self):
        return "Flex"

    def GetErrorCode(self):
        return 0

    def GetFirstDisplayDimension(self):
        return self.display_dimension

    def GetNextDisplayDimension(self, current):
        return None


class DisplayDimension:
    def GetDimension2(self, configuration):
        return Dimension()


class Dimension:
    Name = "D0"
    SystemValue = 0.2


class Manager:
    def __init__(self):
        self.args = None
        self.feature = Feature()

    def InsertFlexFeature(self, *args):
        self.args = args
        return self.feature


class Model:
    def __init__(self):
        self.SelectionManager = SelectionManager()
        self.FeatureManager = Manager()
        self.body = Body()
        self.clears = 0

    def ClearSelection2(self, all_items):
        self.clears += 1

    def GetBodies2(self, body_type, visible_only):
        return (self.body,)


class FlexTests(unittest.TestCase):
    def test_bending_argument_order_and_axis_normalization(self):
        model = Model()
        feature = sw_part.flex_feature(
            model, model.body, "bending", 0.5,
            rotation_axis=(0.0, 0.0, 4.0),
            tangent_axis=(2.0, 0.0, 0.0),
            radius_axis=(0.0, 3.0, 0.0),
            pivot=(0.01, 0.02, 0.03),
            left_trim=0.04, right_trim=0.06, hard_edges=True,
        )
        self.assertIs(feature, model.FeatureManager.feature)
        self.assertEqual(
            model.FeatureManager.args,
            (0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0,
             0.5, 0.01, 0.02, 0.03, 0, 0.04, 0.06, True),
        )
        self.assertEqual(len(model.body.calls), 1)
        self.assertFalse(model.body.calls[0][0])
        self.assertIs(model.body.calls[0][1], model.SelectionManager.select_data)
        self.assertEqual(model.SelectionManager.select_data.Mark, 1)
        self.assertEqual(model.clears, 2)

    def test_all_documented_modes(self):
        for mode, expected in sw_part.FLEX_TYPES.items():
            with self.subTest(mode=mode):
                model = Model()
                sw_part.flex_feature(model, model.body, mode, 0.1)
                self.assertEqual(model.FeatureManager.args[13], expected)

    def test_validates_mode_axes_and_trim_range(self):
        model = Model()
        with self.assertRaises(ValueError):
            sw_part.flex_feature(model, model.body, "unknown", 0.1)
        with self.assertRaises(ValueError):
            sw_part.flex_feature(model, model.body, "bending", 0.1, tangent_axis=(0, 0, 0))
        with self.assertRaises(ValueError):
            sw_part.flex_feature(model, model.body, "bending", 0.1, rotation_axis=(0, 0, 0))
        with self.assertRaises(ValueError):
            sw_part.flex_feature(
                model, model.body, "bending", 0.1,
                tangent_axis=(1, 0, 0), radius_axis=(1, 0, 0),
            )
        with self.assertRaises(ValueError):
            sw_part.flex_feature(model, model.body, "bending", 0.1, left_trim=-1, right_trim=1)
        with self.assertRaises(ValueError):
            sw_part.flex_feature(model, model.body, "bending", 0.1, left_trim=0, right_trim=0)
        sw_part.flex_feature(model, model.body, "bending", 0.1, left_trim=1, right_trim=1)

    def test_reads_feature_and_resulting_body_evidence(self):
        model = Model()
        evidence = sw_part.flex_feature_evidence(Feature(), model)
        self.assertEqual(evidence["feature"], "Flex1")
        self.assertEqual(evidence["type"], "Flex")
        self.assertEqual(evidence["error_code"], 0)
        self.assertEqual(
            evidence["dimensions"], ({"name": "D0", "system_value": 0.2},),
        )
        self.assertEqual(evidence["body_count"], 1)
        self.assertEqual(evidence["bodies"][0]["volume"], 0.00001)


if __name__ == "__main__":
    unittest.main()
