"""Offline contracts for native Intersect features."""

from pathlib import Path
import sys
import unittest
import pythoncom
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class Feature:
    Name = "Intersect1"
    def GetTypeName2(self): return "Intersect"


class Body:
    def __init__(self, volume): self.volume = volume
    def Select(self, _append, mark): return mark == 0
    def GetMassProperties(self, _density): return (0, 0, 0, self.volume)


class Manager:
    def __init__(self, model):
        self.model = model
        self.regions = [Body(.018), Body(.006), Body(.002)]
        self.excluded = None
        self.excluded_vt = None
        self.clear_calls_at_post = None
        self.pre2_calls = []
        self.feature = Feature()
    def PreIntersect2(self, cap, region_type):
        self.pre2_calls.append((cap, region_type))
        return self.regions
    def PreIntersect(self, _cap):
        raise AssertionError("obsolete PreIntersect must not be called")
    def PostIntersect(self, excluded, _merge, _consume):
        self.excluded = tuple(bool(v) for v in excluded.value)
        self.excluded_vt = excluded.varianttype
        self.clear_calls_at_post = self.model.clear_calls
        return self.feature


class Model:
    def __init__(self):
        self.clear_calls = 0
        self.FeatureManager = Manager(self)
    def ClearSelection2(self, _all): self.clear_calls += 1
    def FirstFeature(self): return None


class IntersectTests(unittest.TestCase):
    def test_target_volume_selects_unique_region(self):
        model = Model(); bodies = (Body(.024), Body(.008))
        with mock.patch.object(
            sw_part,
            "_typed_sldworks_feature_manager",
            wraps=sw_part._typed_sldworks_feature_manager,
        ) as typed_manager:
            result = sw_part.intersect_bodies(model, bodies, target_volume=.006)
        typed_manager.assert_called_once_with(model.FeatureManager)
        self.assertEqual(result["included_indices"], (1,))
        self.assertEqual(model.FeatureManager.excluded, (True, False, True))
        self.assertEqual(
            model.FeatureManager.excluded_vt,
            pythoncom.VT_ARRAY | pythoncom.VT_BOOL,
        )
        self.assertGreaterEqual(model.FeatureManager.clear_calls_at_post, 2)
        self.assertEqual(model.FeatureManager.pre2_calls, [(False, 0)])

    def test_requires_two_bodies(self):
        with self.assertRaises(ValueError): sw_part.intersect_bodies(Model(), (Body(1),))

    def test_rejects_unknown_region_type_before_selection(self):
        with self.assertRaises(ValueError):
            sw_part.intersect_bodies(Model(), (Body(1), Body(2)), region_type=3)


if __name__ == "__main__":
    unittest.main()
