"""Offline contracts for native Feature parent/child graph inspection."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class Feature:
    def __init__(self, name, kind):
        self.Name = name
        self.kind = kind
        self.parents = []
        self.children = []

    def GetTypeName2(self): return self.kind
    def GetParents(self): return tuple(self.parents)
    def GetChildren(self): return tuple(self.children)


class Model:
    def __init__(self):
        self.base = Feature("Boss1", "Boss")
        self.cut = Feature("Cut1", "Cut")
        self.fillet = Feature("Fillet1", "Fillet")
        self.base.children = [self.cut]
        self.cut.parents = [self.base]
        self.cut.children = [self.fillet]
        self.fillet.parents = [self.cut]
        self.features = {item.Name: item for item in (self.base, self.cut, self.fillet)}

    def FeatureByName(self, name): return self.features.get(name)


class FeatureDependencyTests(unittest.TestCase):
    def test_recursive_graph_deduplicates_native_features(self):
        graph = sw_part.feature_dependency_graph(Model(), "Fillet1")
        self.assertEqual(graph["root"], {"name": "Fillet1", "type": "Fillet"})
        self.assertEqual([node["name"] for node in graph["nodes"]], [
            "Boss1", "Cut1", "Fillet1",
        ])
        self.assertEqual([
            (edge["parent"]["name"], edge["child"]["name"])
            for edge in graph["edges"]
        ], [("Boss1", "Cut1"), ("Cut1", "Fillet1")])

    def test_direct_graph_includes_only_one_hop(self):
        graph = sw_part.feature_dependency_graph(Model(), "Cut1", recursive=False)
        self.assertEqual({node["name"] for node in graph["nodes"]}, {
            "Boss1", "Cut1", "Fillet1",
        })

    def test_missing_root_is_rejected(self):
        with self.assertRaises(ValueError):
            sw_part.feature_dependency_graph(Model(), "Missing")


if __name__ == "__main__":
    unittest.main()
