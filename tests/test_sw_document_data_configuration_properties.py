"""Offline contracts for native configuration property editing."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_document_data


class Configuration:
    def __init__(self, name, parent=None):
        self.Name = name
        self.parent = parent
        self.Comment = ""
        self.Description = ""
        self.AlternateName = ""
        self.BOMPartNoSource = 1
        self.UseAlternateNameInBOM = False
        self.UseDescriptionInBOM = False
        self.SuppressNewFeatures = False

    @property
    def IsDerived(self):
        return self.parent is not None

    def GetParent(self):
        return self.model.configurations[self.parent] if self.parent else None


class Manager:
    def __init__(self, model):
        self.model = model

    @property
    def ActiveConfiguration(self):
        return self.model.configurations[self.model.active]


class Model:
    EditRebuild3 = True

    def __init__(self, active="Default"):
        self.active = active
        self.configurations = {
            "Default": Configuration("Default"),
            "Thin": Configuration("Thin", parent="Default"),
        }
        for configuration in self.configurations.values():
            configuration.model = self
        self.ConfigurationManager = Manager(self)

    def GetConfigurationNames(self):
        return tuple(self.configurations)

    def GetConfigurationByName(self, name):
        return self.configurations.get(name)

    def ShowConfiguration2(self, name):
        if name not in self.configurations:
            return False
        self.active = name
        return True


class ConfigurationPropertyTests(unittest.TestCase):
    def test_reads_native_properties_and_parent(self):
        model = Model()
        result = sw_document_data.inspect_configuration_properties(model, "thin")
        self.assertEqual(result["configuration"], "Thin")
        self.assertTrue(result["derived"])
        self.assertEqual(result["parent"], "Default")
        self.assertEqual(result["bom_part_number_source"], "document_name")

    def test_updates_properties_with_bom_source_readback(self):
        model = Model()
        result = sw_document_data.update_configuration_properties(
            model,
            "Thin",
            comment="reviewed",
            description="Lightweight",
            alternate_name="PN-006",
            use_alternate_name_in_bom=True,
            use_description_in_bom=True,
            suppress_new_features=True,
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["after"]["alternate_name"], "PN-006")
        self.assertTrue(result["after"]["use_alternate_name_in_bom"])
        self.assertTrue(result["after"]["suppress_new_features"])
        self.assertEqual(result["active_after"], "Default")

    def test_temporarily_switches_when_editing_active_suppress_default(self):
        model = Model(active="Thin")
        result = sw_document_data.update_configuration_properties(
            model, "Thin", suppress_new_features=True,
        )
        self.assertTrue(result["success"])
        self.assertTrue(result["switched_for_inactive_property"])
        self.assertEqual(result["temporary_configuration"], "Default")
        self.assertEqual(model.active, "Thin")

    def test_requires_a_property_change(self):
        model = Model()
        with self.assertRaisesRegex(ValueError, "至少提供"):
            sw_document_data.update_configuration_properties(model, "Thin")


if __name__ == "__main__":
    unittest.main()
