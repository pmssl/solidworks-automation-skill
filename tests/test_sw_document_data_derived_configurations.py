"""Offline contracts for native derived configurations."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_document_data


class Configuration:
    def __init__(self, name, parent=None): self.Name = name; self.parent = parent; self.children = []
    def IsDerived(self): return self.parent is not None
    def GetParent(self): return self.parent
    def GetChildren(self): return tuple(self.children)


class Manager:
    def __init__(self, model): self.model = model; self.ActiveConfiguration = model.configurations["Default"]
    def AddConfiguration2(self, name, _comment, _alternate, _options, parent_name, _description, _rebuild):
        parent = self.model.configurations[parent_name]
        child = Configuration(name, parent); parent.children.append(child)
        self.model.configurations[name] = child
        return child


class Model:
    EditRebuild3 = True
    def __init__(self):
        self.configurations = {"Default": Configuration("Default")}
        self.ConfigurationManager = Manager(self)
    def GetConfigurationNames(self): return tuple(self.configurations)
    def GetConfigurationByName(self, name): return self.configurations.get(name)
    def ShowConfiguration2(self, name): self.ConfigurationManager.ActiveConfiguration = self.configurations[name]; return True


class DerivedConfigurationTests(unittest.TestCase):
    def test_create_and_read_two_level_hierarchy(self):
        model = Model()
        first = sw_document_data.create_derived_configuration(model, "Child", "Default")
        second = sw_document_data.create_derived_configuration(model, "Grandchild", "Child")
        hierarchy = sw_document_data.configuration_hierarchy(model)["configurations"]
        self.assertTrue(first["success"]); self.assertTrue(second["success"])
        self.assertEqual(hierarchy["Child"], {
            "derived": True, "parent": "Default", "children": ["Grandchild"],
        })
        self.assertEqual(hierarchy["Grandchild"]["parent"], "Child")

    def test_rejects_missing_parent_before_creation(self):
        with self.assertRaises(LookupError):
            sw_document_data.create_derived_configuration(Model(), "Child", "Missing")


if __name__ == "__main__":
    unittest.main()
