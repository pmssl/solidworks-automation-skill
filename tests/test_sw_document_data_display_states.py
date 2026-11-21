"""Offline contracts for native display-state lifecycle operations."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_document_data


class Configuration:
    def __init__(self, name="Default"):
        self.Name = name
        self.states = ["Display State-1"]
    def GetDisplayStates(self): return tuple(self.states)
    def GetDisplayStatesCount(self): return len(self.states)
    def CreateDisplayState(self, name): self.states.append(name); return True
    def ApplyDisplayState(self, name):
        if name not in self.states: return False
        self.states.remove(name); self.states.insert(0, name); return True
    def RenameDisplayState(self, old, new):
        self.states[self.states.index(old)] = new; return True
    def DeleteDisplayState(self, name): self.states.remove(name); return True


class Model:
    def __init__(self):
        self.configuration = Configuration()
        self.ConfigurationManager = type(
            "Manager", (), {"ActiveConfiguration": self.configuration},
        )()
    def GetConfigurationNames(self): return (self.configuration.Name,)
    def GetConfigurationByName(self, name):
        return self.configuration if name == self.configuration.Name else None


class DisplayStateTests(unittest.TestCase):
    def test_create_apply_rename_and_delete_lifecycle(self):
        model = Model(); original = sw_document_data.inspect_display_states(model)["active_display_state"]
        created = sw_document_data.create_display_state(model, "Review")
        self.assertTrue(created["success"]); self.assertEqual(created["states_after"][0], "Review")
        renamed = sw_document_data.rename_display_state(model, "Review", "Inspection")
        self.assertTrue(renamed["success"])
        sw_document_data.activate_display_state(model, original)
        deleted = sw_document_data.delete_display_state(model, "Inspection")
        self.assertTrue(deleted["success"]); self.assertEqual(deleted["after"]["display_states"], [original])

    def test_rejects_deleting_active_display_state(self):
        model = Model()
        with self.assertRaises(ValueError):
            sw_document_data.delete_display_state(model, "Display State-1")


if __name__ == "__main__":
    unittest.main()
