"""Offline contracts for native rollback-bar control."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class Feature:
    Name = "Cut1"


class Manager:
    def __init__(self): self.calls = []
    def EditRollback(self, location, name): self.calls.append((location, name)); return True


class Model:
    def __init__(self): self.FeatureManager = Manager(); self.feature = Feature()
    def FeatureByName(self, name): return self.feature if name == "Cut1" else None


class RollbackTests(unittest.TestCase):
    def test_before_after_and_end_locations(self):
        model = Model()
        sw_part.rollback_to_feature(model, model.feature, before=True)
        sw_part.rollback_to_feature(model, "Cut1", before=False)
        sw_part.rollback_to_end(model)
        self.assertEqual(model.FeatureManager.calls,
                         [(3, "Cut1"), (4, "Cut1"), (1, "")])

    def test_missing_feature_is_rejected(self):
        with self.assertRaises(ValueError): sw_part.rollback_to_feature(Model(), "Missing")


if __name__ == "__main__":
    unittest.main()
