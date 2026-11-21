"""Offline contracts for native configuration-parameter matrix reads."""

from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_document_data


class Configuration:
    def __init__(self, names, values, reported_count=None):
        self.names = tuple(names)
        self.values = tuple(values)
        self.reported_count = len(self.names) if reported_count is None else reported_count

    def GetParameterCount(self):
        return self.reported_count

    def GetParameters(self, params, values):
        params.value = self.names
        values.value = self.values


class Model:
    def __init__(self, configuration):
        self.configuration = configuration

    def GetConfigurationNames(self):
        return ("Default", "Thin")

    def GetConfigurationByName(self, name):
        return self.configuration if name == "Thin" else None


class ConfigurationParameterTests(unittest.TestCase):
    def test_reads_and_classifies_native_parameter_matrix(self):
        model = Model(Configuration(
            ("$说明", "$STATE@Cut1", "D1@Boss1"),
            ("Thin", "S", "6.000000"),
        ))
        with mock.patch.object(
            sw_document_data, "inspect_design_table", return_value={"exists": False},
        ):
            result = sw_document_data.read_configuration_parameters(model, "thin")
        self.assertEqual(result["configuration"], "Thin")
        self.assertEqual(result["reported_count"], 3)
        self.assertEqual(result["categories"]["dimensions"], {"D1@Boss1": "6.000000"})
        self.assertEqual(result["categories"]["feature_states"], {"$STATE@Cut1": "S"})
        self.assertEqual(result["categories"]["metadata"], {"$说明": "Thin"})
        self.assertTrue(result["read_only"])
        self.assertTrue(result["review_required"])

    def test_rejects_reported_count_mismatch(self):
        model = Model(Configuration(("D1@Boss1",), ("6.0",), reported_count=2))
        with self.assertRaisesRegex(RuntimeError, "数量回读不一致"):
            sw_document_data.read_configuration_parameters(model, "Thin")

    def test_rejects_name_value_mismatch(self):
        model = Model(Configuration(("D1@Boss1",), ()))
        with self.assertRaisesRegex(RuntimeError, "参数名和值数量不一致"):
            sw_document_data.read_configuration_parameters(model, "Thin")

    def test_rejects_case_insensitive_duplicate_names(self):
        model = Model(Configuration(("D1@Boss1", "d1@boss1"), ("6", "7")))
        with self.assertRaisesRegex(RuntimeError, "重复项"):
            sw_document_data.read_configuration_parameters(model, "Thin")

    def test_rejects_unknown_configuration_before_com_read(self):
        model = Model(Configuration((), ()))
        with self.assertRaises(LookupError):
            sw_document_data.read_configuration_parameters(model, "Missing")


if __name__ == "__main__":
    unittest.main()
