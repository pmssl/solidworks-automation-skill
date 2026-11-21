"""Offline contracts for native configuration rename/delete lifecycle."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_document_data


class Configuration:
    def __init__(self, model, name, parent=None):
        self.model = model
        self._name = name
        self.parent = parent

    @property
    def Name(self):
        return self._name

    @Name.setter
    def Name(self, value):
        old = self._name
        self._name = value
        self.model.configurations[value] = self.model.configurations.pop(old)
        for config in self.model.configurations.values():
            if config.parent == old:
                config.parent = value
        if self.model.active == old:
            self.model.active = value

    @property
    def IsDerived(self):
        return self.parent is not None

    def GetParent(self):
        return self.model.configurations[self.parent] if self.parent else None

    def GetChildren(self):
        return tuple(
            config for config in self.model.configurations.values()
            if config.parent == self.Name
        )


class Manager:
    def __init__(self, model):
        self.model = model

    @property
    def ActiveConfiguration(self):
        return self.model.configurations[self.model.active]


class Model:
    EditRebuild3 = True

    def __init__(self, rows, active):
        self.configurations = {}
        self.active = active
        self.deleted = []
        for name, parent in rows:
            self.configurations[name] = Configuration(self, name, parent)
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

    def DeleteConfiguration2(self, name):
        if name == self.active or name not in self.configurations:
            return False
        if any(config.parent == name for config in self.configurations.values()):
            return False
        del self.configurations[name]
        self.deleted.append(name)
        return True


class ConfigurationLifecycleTests(unittest.TestCase):
    def test_rename_parent_preserves_active_state_and_child_hierarchy(self):
        model = Model((("Default", None), ("Parent", None), ("Child", "Parent")), "Parent")
        result = sw_document_data.rename_configuration(model, "parent", "Renamed")
        self.assertTrue(result["success"])
        self.assertEqual(result["active_after"], "Renamed")
        self.assertEqual(result["hierarchy_after"]["configurations"]["Child"]["parent"], "Renamed")
        self.assertNotIn("Parent", model.configurations)

    def test_rename_rejects_case_insensitive_collision(self):
        model = Model((("Default", None), ("Thin", None)), "Default")
        with self.assertRaises(FileExistsError):
            sw_document_data.rename_configuration(model, "Default", "thin")

    def test_delete_active_subtree_switches_and_deletes_postorder(self):
        model = Model(
            (("Default", None), ("Parent", None), ("Child", "Parent"), ("Grand", "Child")),
            "Grand",
        )
        result = sw_document_data.delete_configuration(
            model, "Parent", include_descendants=True, fallback_configuration="Default",
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["delete_order"], ["Grand", "Child", "Parent"])
        self.assertEqual(model.deleted, ["Grand", "Child", "Parent"])
        self.assertEqual(result["active_after"], "Default")
        self.assertEqual(result["configurations_after"], ["Default"])

    def test_delete_parent_requires_explicit_subtree_mode(self):
        model = Model((("Default", None), ("Parent", None), ("Child", "Parent")), "Default")
        with self.assertRaisesRegex(ValueError, "include_descendants=True"):
            sw_document_data.delete_configuration(model, "Parent")
        self.assertEqual(model.deleted, [])

    def test_delete_rejects_only_configuration(self):
        model = Model((("Default", None),), "Default")
        with self.assertRaisesRegex(ValueError, "唯一配置"):
            sw_document_data.delete_configuration(model, "Default")


if __name__ == "__main__":
    unittest.main()
