"""Offline contracts for native configuration-family batch updates."""

from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_document_data


class Model:
    EditRebuild3 = True


class ConfigurationFamilyTests(unittest.TestCase):
    def test_validates_complete_family_before_mutation(self):
        with mock.patch.object(sw_document_data, "create_configuration") as create:
            with self.assertRaises(ValueError):
                sw_document_data.apply_configuration_family(
                    Model(),
                    ({"name": "Thin", "dimensions_mm": {"D1@Boss": 5}},
                     {"name": "thin"}),
                )
        create.assert_not_called()

    def test_applies_explicit_configuration_scopes_and_restores_active(self):
        model = Model()
        with mock.patch.object(
            sw_document_data, "_active_configuration_name", side_effect=["Default", "Default"],
        ), mock.patch.object(
            sw_document_data, "_configuration_names", return_value=["Default", "Thin"],
        ), mock.patch.object(
            sw_document_data, "create_configuration", return_value={"success": True},
        ) as create, mock.patch.object(
            sw_document_data, "update_dimension_mm", return_value={"success": True},
        ) as update, mock.patch.object(
            sw_document_data, "set_custom_properties", return_value={"success": True},
        ) as properties, mock.patch.object(
            sw_document_data, "set_feature_suppression", return_value={"success": True},
        ) as suppression, mock.patch.object(
            sw_document_data, "activate_configuration", return_value={"success": True},
        ) as activate:
            result = sw_document_data.apply_configuration_family(model, ({
                "name": "Thin",
                "dimensions_mm": {"D1@Boss": 6.0},
                "properties": {"Class": "Thin"},
                "feature_suppression": {"Cut1": "suppress"},
            },))
        self.assertTrue(result["success"])
        create.assert_called_once_with(
            model, "Thin", if_exists="reuse", activate=False, rebuild=False, save=False,
        )
        update.assert_called_once_with(
            model, "D1@Boss", 6.0, configuration_mode="specific",
            configuration_names=("Thin",), rebuild=False, save=False,
        )
        properties.assert_called_once_with(
            model, {"Class": "Thin"}, configuration_name="Thin", save=False,
        )
        suppression.assert_called_once()
        activate.assert_called_once_with(model, "Default", rebuild=True, save=False)


if __name__ == "__main__":
    unittest.main()
