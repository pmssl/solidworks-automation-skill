"""Offline contracts for native FeatureManager folders."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class FolderSpecific:
    def __init__(self, model):
        self.model = model

    def GetFeatureCount(self):
        return len(self.model.folder_contents)


class Feature:
    def __init__(self, name, model):
        self.Name = name
        self.model = model

    def Select2(self, append, mark):
        if not append:
            self.model.selected = []
        self.model.selected.append((self, mark))
        return True

    def GetSpecificFeature2(self):
        return FolderSpecific(self.model)


class FeatureManager:
    def __init__(self, model):
        self.model = model
        self.folder_type = None

    def InsertFeatureTreeFolder2(self, folder_type):
        self.folder_type = folder_type
        self.model.folder_contents = [item[0] for item in self.model.selected]
        return Feature("Folder1", self.model)


class Model:
    def __init__(self):
        self.selected = []
        self.folder_contents = []
        self.FeatureManager = FeatureManager(self)
        self.features = {
            "Boss": Feature("Boss", self),
            "Cut": Feature("Cut", self),
        }

    def FeatureByName(self, name):
        return self.features.get(name)

    def ClearSelection2(self, _clear_all):
        self.selected = []


class FeatureFolderTests(unittest.TestCase):
    def test_creates_containing_folder_and_renames_it(self):
        model = Model()

        folder = sw_part.create_feature_folder(model, ("Boss", "Cut"), name="Machining")

        self.assertEqual(model.FeatureManager.folder_type, 2)
        self.assertEqual([item.Name for item in model.folder_contents], ["Boss", "Cut"])
        self.assertEqual(folder.Name, "Machining")
        self.assertEqual(model.selected, [])

    def test_requires_features_and_nonempty_name(self):
        model = Model()
        with self.assertRaises(ValueError):
            sw_part.create_feature_folder(model, ())
        with self.assertRaises(ValueError):
            sw_part.create_feature_folder(model, "Boss", name=" ")

    def test_creates_nested_containing_folder(self):
        model = Model()
        inner = sw_part.create_feature_folder(model, ("Boss", "Cut"), name="Inner")
        later = Feature("LaterCut", model)
        model.features["LaterCut"] = later

        outer = sw_part.create_feature_folder(
            model, (inner, later), name="Outer",
        )

        self.assertEqual(outer.Name, "Outer")
        self.assertEqual([item.Name for item in model.folder_contents], ["Inner", "LaterCut"])


if __name__ == "__main__":
    unittest.main()
