"""Offline contracts for configuration-scoped feature suppression."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_document_data


class Feature:
    def __init__(self, model):
        self.model = model
        self.calls = []

    def SetSuppression2(self, action, scope, names):
        self.calls.append((action, scope, names))
        targets = (
            tuple(names.value) if scope == 3 else
            tuple(self.model.names) if scope == 2 else
            (self.model.active,)
        )
        for name in targets:
            self.model.states[name] = action == 0
        return True

    def IsSuppressed(self):
        return self.model.states[self.model.active]


class Configuration:
    def __init__(self, name): self.Name = name


class ConfigurationManager:
    def __init__(self, model): self.model = model
    @property
    def ActiveConfiguration(self): return Configuration(self.model.active)


class Model:
    def __init__(self):
        self.names = ["Default", "NoHole", "Hole"]
        self.active = "Default"
        self.states = {name: False for name in self.names}
        self.feature = Feature(self)
        self.ConfigurationManager = ConfigurationManager(self)

    def GetConfigurationNames(self): return tuple(self.names)
    def FeatureByName(self, name): return self.feature if name == "Cut1" else None
    def ShowConfiguration2(self, name): self.active = name; return True
    def EditRebuild3(self): return True


class FeatureSuppressionTests(unittest.TestCase):
    def test_specific_configuration_suppression_and_restore(self):
        model = Model()
        result = sw_document_data.set_feature_suppression(
            model, "Cut1", "suppress",
            configuration_mode="specific", configuration_names=("nohole",),
        )
        self.assertTrue(result["success"])
        self.assertEqual(model.states, {"Default": False, "NoHole": True, "Hole": False})
        self.assertEqual(model.active, "Default")
        action, scope, names = model.feature.calls[0]
        self.assertEqual((action, scope), (0, 3))
        self.assertEqual(tuple(names.value), ("NoHole",))

    def test_all_configuration_unsuppression(self):
        model = Model()
        model.states = {name: True for name in model.names}
        result = sw_document_data.set_feature_suppression(
            model, "Cut1", "unsuppress", configuration_mode="all",
        )
        self.assertTrue(result["success"])
        self.assertFalse(any(model.states.values()))

    def test_invalid_scope_names_and_feature_are_rejected(self):
        model = Model()
        with self.assertRaises(ValueError):
            sw_document_data.set_feature_suppression(
                model, "Cut1", "suppress", configuration_mode="specific",
            )
        with self.assertRaises(ValueError):
            sw_document_data.set_feature_suppression(
                model, "Cut1", "suppress", configuration_names=("NoHole",),
            )
        with self.assertRaises(LookupError):
            sw_document_data.set_feature_suppression(model, "Missing", "suppress")


if __name__ == "__main__":
    unittest.main()
