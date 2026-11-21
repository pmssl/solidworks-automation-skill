"""Strict offline contracts for native Boundary features."""

from pathlib import Path
import os
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class Entity:
    def __init__(self, name, model):
        self.Name = name
        self.model = model

    def Select2(self, append, mark):
        if not append:
            self.model.selected = []
        self.model.selected.append((self.Name, mark))
        return True

    def Select4(self, append, select_data):
        if not append:
            self.model.selected = []
        self.model.selected.append((self.Name, select_data.Mark))
        return True


class SelectData:
    Mark = 0


class SelectionManager:
    def __init__(self, model):
        self.model = model

    def CreateSelectData(self):
        return SelectData()

    def GetSelectedObjectCount2(self, _mark):
        return len(self.model.selected)

    def GetSelectedObjectType3(self, _index, _mark):
        return 1

    def GetSelectedObjectMark(self, index):
        return self.model.selected[index - 1][1]


class Manager:
    def __init__(self, model):
        self.model = model
        self.curve_data = []
        self.direction_data = []
        self.insert_calls = []
        self.raw_insert_calls = []
        self.legacy_insert_calls = []

    def SetNetBlendCurveData(self, *args):
        self.curve_data.append(tuple(getattr(value, "value", value) for value in args))

    def SetNetBlendDirectionData(self, *args):
        self.direction_data.append(tuple(getattr(value, "value", value) for value in args))

    def InsertNetBlend2(self, *args):
        self.raw_insert_calls.append(args)
        values = tuple(getattr(value, "value", value) for value in args)
        self.insert_calls.append((values, tuple(self.model.selected)))
        return Entity("Boundary1", self.model)

    def InsertNetBlend(self, *args):
        self.legacy_insert_calls.append((args, tuple(self.model.selected)))
        return Entity("LegacyBoundary1", self.model)


class App:
    def __init__(self):
        self.commands = []

    def RunCommand(self, command, label):
        self.commands.append((command, label))
        return True


class Model:
    def __init__(self):
        self.selected = []
        self.features = {
            name: Entity(name, self)
            for name in ("D1A", "D1B", "D2A", "D2B")
        }
        self.FeatureManager = Manager(self)
        self.SelectionManager = SelectionManager(self)
        self.app = App()

    def FeatureByName(self, name):
        return self.features.get(name)

    def ClearSelection2(self, _all):
        self.selected = []

    def GetSwApp(self):
        return self.app


class CleanupFaultModel(Model):
    def __init__(self):
        super().__init__()
        self.clear_calls = 0

    def ClearSelection2(self, _all):
        self.clear_calls += 1
        if self.clear_calls > 1:
            raise RuntimeError("invalid COM proxy during cleanup")
        super().ClearSelection2(_all)


class ExternalSketchSelectionManager(SelectionManager):
    def GetSelectedObjectType3(self, _index, _mark):
        return 24


class BoundaryFeatureTests(unittest.TestCase):
    def setUp(self):
        self.previous_gate = os.environ.get("SW_RUN_INTERACTIVE_BOUNDARY_DIAGNOSTIC")
        os.environ["SW_RUN_INTERACTIVE_BOUNDARY_DIAGNOSTIC"] = "1"

    def tearDown(self):
        if self.previous_gate is None:
            os.environ.pop("SW_RUN_INTERACTIVE_BOUNDARY_DIAGNOSTIC", None)
        else:
            os.environ["SW_RUN_INTERACTIVE_BOUNDARY_DIAGNOSTIC"] = self.previous_gate

    def test_boundary_boss_uses_indexed_direction_marks_and_full_signature(self):
        model = Model()
        feature = sw_part.boundary_boss(
            model, ("D1A", "D1B"), ("D2A", "D2B"),
            direction1_data=(
                {"tangency_type": 1, "tangent_length": 1.25},
                {"tangency_type": 2, "draft_angle": 0.1},
            ),
            direction_influence=(32, 16), trim_curves=(0, 1),
            allow_experimental=True,
        )

        self.assertEqual(feature.Name, "Boundary1")
        self.assertEqual(
            model.FeatureManager.curve_data,
            [(0, 0, 1, 0.0, 1.25, True),
             (0, 1, 2, 0.1, 1.0, True),
             (1, 0, 0, 0.0, 1.0, True),
             (1, 1, 0, 0.0, 1.0, True)],
        )
        self.assertEqual(
            model.FeatureManager.direction_data,
            [(0, 32, 0, False, False), (1, 16, 1, False, False)],
        )
        args, selected = model.FeatureManager.insert_calls[0]
        self.assertEqual(len(args), 21)
        self.assertEqual(args[:5], (1, 2, 2, False, 0.0001))
        self.assertTrue(args[5])
        self.assertTrue(args[20])
        self.assertEqual(
            selected,
            (("D1A", 8193), ("D1B", 16385),
             ("D2A", 8194), ("D2B", 16386)),
        )
        self.assertEqual(model.selected, [])
        self.assertEqual([], model.FeatureManager.legacy_insert_calls)
        raw = model.FeatureManager.raw_insert_calls[0]
        for index in (0, 1, 2, 13):
            self.assertIs(type(raw[index]), int)

    def test_boundary_surface_uses_surface_marks(self):
        model = Model()
        sw_part.boundary_surface(
            model, ("D1A", "D1B"), ("D2A",), allow_experimental=True,
        )

        args, selected = model.FeatureManager.insert_calls[0]
        self.assertEqual(args[0], 2)
        self.assertFalse(args[5])
        self.assertFalse(args[20])
        self.assertEqual(
            selected,
            (("D1A", 1), ("D1B", 1), ("D2A", 2)),
        )

    def test_validates_curve_counts_settings_and_thickness(self):
        with self.assertRaises(ValueError):
            sw_part.boundary_boss(Model(), ("D1A",))
        with self.assertRaises(ValueError):
            sw_part.boundary_boss(
                Model(), ("D1A", "D1B"), direction1_data=({},),
            )
        with self.assertRaises(ValueError):
            sw_part.boundary_boss(
                Model(), ("D1A", "D1B"), thin=True, thickness1=0.0,
            )

    def test_dangerous_com_call_requires_both_internal_gates(self):
        model = Model()
        os.environ.pop("SW_RUN_INTERACTIVE_BOUNDARY_DIAGNOSTIC", None)
        with self.assertRaisesRegex(RuntimeError, "can terminate SolidWorks"):
            sw_part.boundary_boss(
                model, ("D1A", "D1B"), allow_experimental=True,
            )
        self.assertEqual([], model.FeatureManager.insert_calls)

        os.environ["SW_RUN_INTERACTIVE_BOUNDARY_DIAGNOSTIC"] = "1"
        with self.assertRaisesRegex(RuntimeError, "can terminate SolidWorks"):
            sw_part.boundary_boss(model, ("D1A", "D1B"))
        self.assertEqual([], model.FeatureManager.insert_calls)

    def test_cleanup_fault_does_not_mask_null_feature_result(self):
        model = CleanupFaultModel()
        model.FeatureManager.InsertNetBlend2 = lambda *args: None
        with self.assertRaisesRegex(RuntimeError, "did not create the boundary"):
            sw_part.boundary_boss(
                model, ("D1A", "D1B"), allow_experimental=True,
            )

    def test_external_sketch_proxy_is_rejected_before_boundary_com_call(self):
        model = Model()
        model.SelectionManager = ExternalSketchSelectionManager(model)
        with self.assertRaisesRegex(RuntimeError, "unsafe Boundary selection"):
            sw_part.boundary_surface(
                model, ("D1A",), ("D2A",), allow_experimental=True,
            )
        self.assertEqual([], model.FeatureManager.insert_calls)
        self.assertEqual([], model.FeatureManager.curve_data)

    def test_legacy_boundary_route_is_explicit_and_does_not_call_insert2(self):
        model = Model()
        feature = sw_part.boundary_surface(
            model, ("D1A",), ("D2A",),
            allow_experimental=True, use_legacy=True,
        )
        self.assertEqual("LegacyBoundary1", feature.Name)
        self.assertEqual([], model.FeatureManager.insert_calls)
        self.assertEqual(1, len(model.FeatureManager.legacy_insert_calls))

    def test_boundary_surface_command_uses_native_pm_ok_and_internal_gate(self):
        model = Model()
        before = Entity("Boss1", model)
        after = Entity("BoundarySurface1", model)
        with mock.patch.object(sw_part, "_last_model_feature", side_effect=(before, after)), \
             mock.patch.object(sw_part.time, "sleep"):
            feature = sw_part.boundary_surface_command(
                model, (model.features["D1A"],), (model.features["D2A"],),
                allow_experimental=True,
            )
        self.assertEqual("BoundarySurface1", feature.Name)
        self.assertEqual(
            [(618, "Boundary Surface"), (-2, "Accept Boundary Surface")],
            model.app.commands,
        )

        blocked = Model()
        with self.assertRaisesRegex(RuntimeError, "allow_experimental"):
            sw_part.boundary_surface_command(
                blocked, (blocked.features["D1A"],), (blocked.features["D2A"],),
            )
        self.assertEqual([], blocked.app.commands)


if __name__ == "__main__":
    unittest.main()
