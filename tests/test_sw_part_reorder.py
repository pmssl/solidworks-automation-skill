"""Offline contracts for native FeatureManager reordering."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class Feature:
    def __init__(self, name): self.Name = name; self.next = None
    def GetNextFeature(self): return self.next


class Extension:
    def __init__(self, model): self.model = model; self.args = None
    def ReorderFeature(self, move, target, location):
        self.args = (move, target, location)
        moving = self.model.features.pop(self.model.features.index(self.model.by_name[move]))
        index = self.model.features.index(self.model.by_name[target]) + 1
        self.model.features.insert(index, moving)
        self.model.link()
        return True


class Model:
    def __init__(self):
        self.features = [Feature("Origin"), Feature("Boss1"), Feature("Boss2")]
        self.by_name = {feature.Name: feature for feature in self.features}
        self.Extension = Extension(self); self.link()
    def link(self):
        for index, feature in enumerate(self.features):
            feature.next = self.features[index + 1] if index + 1 < len(self.features) else None
    def FirstFeature(self): return self.features[0]
    def FeatureByName(self, name): return self.by_name.get(name)


class ReorderTests(unittest.TestCase):
    def test_move_after_and_verify_tree(self):
        model = Model()
        order = sw_part.reorder_feature_after(model, "Boss1", "Boss2")
        self.assertLess(order.index("Boss2"), order.index("Boss1"))
        self.assertEqual(model.Extension.args, ("Boss1", "Boss2", 3))

    def test_rejects_invalid_names(self):
        with self.assertRaises(ValueError): sw_part.reorder_feature_after(Model(), "Boss1", "Boss1")
        with self.assertRaises(ValueError): sw_part.reorder_feature_after(Model(), "Missing", "Boss2")


if __name__ == "__main__":
    unittest.main()
