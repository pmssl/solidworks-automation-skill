"""Offline contracts for multi-configuration rebuild and geometry auditing."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_document_data


class Configuration:
    def __init__(self, model, name):
        self.model = model
        self.Name = name

    @property
    def NeedsRebuild(self):
        return self.model.needs_rebuild[self.Name]


class Manager:
    def __init__(self, model):
        self.model = model

    @property
    def ActiveConfiguration(self):
        return self.model.configurations[self.model.active]


class Feature:
    def __init__(self, model, index, name, feature_type):
        self.model = model
        self.index = index
        self.Name = name
        self.feature_type = feature_type

    def GetTypeName2(self):
        return self.feature_type

    def GetErrorCode(self):
        return self.model.feature_errors.get((self.model.active, self.Name), 0)

    def GetNextFeature(self):
        next_index = self.index + 1
        return self.model.features[next_index] if next_index < len(self.model.features) else None


class Body:
    def __init__(self, volume_mm3, box_mm):
        self.volume_mm3 = volume_mm3
        self.box_mm = box_mm

    def GetMassProperties(self, density):
        return (0.0, 0.0, 0.0, self.volume_mm3 / 1e9)

    def GetBodyBox(self):
        return tuple(value / 1000.0 for value in self.box_mm)


class Model:
    def __init__(self):
        self.active = "Default"
        self.configurations = {
            name: Configuration(self, name) for name in ("Default", "Thin", "Thick")
        }
        self.ConfigurationManager = Manager(self)
        self.needs_rebuild = {name: True for name in self.configurations}
        self.force_rebuild_return = True
        self.leave_needs_rebuild = set()
        self.feature_errors = {}
        self.features = [
            Feature(self, 0, "Origin", "OriginProfileFeature"),
            Feature(self, 1, "Boss-Extrude1", "Boss"),
        ]
        self.bodies = {
            "Default": [Body(48000.0, (0, 0, 0, 80, 50, 12))],
            "Thin": [Body(24000.0, (0, 0, 0, 80, 50, 6))],
            "Thick": [Body(80000.0, (0, 0, 0, 80, 50, 20))],
        }

    def GetConfigurationNames(self):
        return tuple(self.configurations)

    def GetConfigurationByName(self, name):
        return self.configurations.get(name)

    def ShowConfiguration2(self, name):
        if name not in self.configurations:
            return False
        self.active = name
        return True

    def ForceRebuild3(self, top_only):
        if self.force_rebuild_return and self.active not in self.leave_needs_rebuild:
            self.needs_rebuild[self.active] = False
        return self.force_rebuild_return

    def FirstFeature(self):
        return self.features[0]

    def GetBodies2(self, body_type, visible_only):
        return tuple(self.bodies[self.active])


class ConfigurationAuditTests(unittest.TestCase):
    def test_audits_all_configurations_and_restores_original(self):
        model = Model()
        result = sw_document_data.audit_configuration_rebuilds(model)
        self.assertTrue(result["success"])
        self.assertEqual(result["active_after"], "Default")
        self.assertTrue(result["restored_active"])
        self.assertEqual(
            [row["volumes_mm3"] for row in result["configurations"]],
            [[48000.0], [24000.0], [80000.0]],
        )
        self.assertEqual(
            [row["combined_bounding_box_mm"][5] for row in result["configurations"]],
            [12.0, 6.0, 20.0],
        )
        self.assertTrue(all(not row["needs_rebuild_after"] for row in result["configurations"]))

    def test_selected_names_are_case_insensitive_and_duplicates_rejected(self):
        model = Model()
        result = sw_document_data.audit_configuration_rebuilds(
            model, ("thin", "THICK"),
        )
        self.assertEqual(result["configuration_names"], ["Thin", "Thick"])
        with self.assertRaisesRegex(ValueError, "重复"):
            sw_document_data.audit_configuration_rebuilds(model, ("Thin", "thin"))

    def test_detects_feature_error(self):
        model = Model()
        model.feature_errors[("Thin", "Boss-Extrude1")] = 7
        result = sw_document_data.audit_configuration_rebuilds(model, ("Thin",))
        self.assertFalse(result["success"])
        self.assertEqual(result["configurations"][0]["feature_errors"][0]["error_code"], 7)

    def test_solid_body_requirement_is_explicit(self):
        model = Model()
        model.bodies["Thin"] = []
        blocked = sw_document_data.audit_configuration_rebuilds(model, ("Thin",))
        self.assertFalse(blocked["success"])
        allowed = sw_document_data.audit_configuration_rebuilds(
            model, ("Thin",), require_solid_body=False,
        )
        self.assertTrue(allowed["success"])

    def test_detects_rebuild_failure_and_stale_configuration(self):
        model = Model()
        model.force_rebuild_return = False
        failed = sw_document_data.audit_configuration_rebuilds(model, ("Default",))
        self.assertFalse(failed["success"])
        self.assertFalse(failed["configurations"][0]["rebuild_success"])

        model = Model()
        model.leave_needs_rebuild.add("Default")
        stale = sw_document_data.audit_configuration_rebuilds(model, ("Default",))
        self.assertFalse(stale["success"])
        self.assertTrue(stale["configurations"][0]["needs_rebuild_after"])


if __name__ == "__main__":
    unittest.main()
