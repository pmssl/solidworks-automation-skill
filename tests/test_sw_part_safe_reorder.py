"""Offline contracts for dependency-aware FeatureManager reordering."""

from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class Feature:
    def __init__(self, name, feature_type="Boss"): self.Name = name; self.feature_type = feature_type
    def GetTypeName2(self): return self.feature_type


class Model:
    def __init__(self, *features): self.features = {feature.Name: feature for feature in features}
    def FeatureByName(self, name): return self.features.get(name)


class SafeReorderTests(unittest.TestCase):
    def test_dependency_path_finds_transitive_child(self):
        base, cut, fillet = Feature("Base"), Feature("Cut", "Cut"), Feature("Fillet", "Fillet")
        model = Model(base, cut, fillet)
        graph = {
            "edges": [
                {"parent": {"name": "Base", "type": "Boss"}, "child": {"name": "Cut", "type": "Cut"}},
                {"parent": {"name": "Cut", "type": "Cut"}, "child": {"name": "Fillet", "type": "Fillet"}},
            ]
        }
        with mock.patch.object(sw_part, "feature_dependency_graph", return_value=graph):
            path = sw_part.feature_dependency_path(model, base, fillet)
        self.assertEqual([item[0] for item in path], ["Base", "Cut", "Fillet"])

    def test_safe_reorder_blocks_parent_after_descendant_before_com_call(self):
        base, fillet = Feature("Base"), Feature("Fillet", "Fillet")
        model = Model(base, fillet)
        with mock.patch.object(
            sw_part, "feature_dependency_path",
            return_value=(("Base", "Boss"), ("Fillet", "Fillet")),
        ), mock.patch.object(sw_part, "reorder_feature_after") as reorder:
            with self.assertRaises(ValueError):
                sw_part.reorder_feature_after_safe(model, base, fillet)
        reorder.assert_not_called()

    def test_safe_reorder_delegates_when_no_dependency_path_exists(self):
        first, second = Feature("First"), Feature("Second")
        model = Model(first, second)
        with mock.patch.object(sw_part, "feature_dependency_path", return_value=()), \
             mock.patch.object(sw_part, "reorder_feature_after", return_value=("Second", "First")) as reorder:
            result = sw_part.reorder_feature_after_safe(model, first, second)
        self.assertEqual(result, ("Second", "First")); reorder.assert_called_once_with(model, first, second)


if __name__ == "__main__":
    unittest.main()
