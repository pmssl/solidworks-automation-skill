"""Offline contracts for native Split features."""

from pathlib import Path
from unittest.mock import patch
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class Feature:
    Name = "Split1"
    def GetTypeName2(self): return "Split"


class Tool:
    def Select2(self, _append, mark): return mark == 0


class Body: pass


class Manager:
    def __init__(self): self.preview = (Body(), Body()); self.args = None; self.feature = Feature()
    def PreSplitBody2(self): return self.preview
    def PostSplitBody2(self, *args): self.args = args; return self.feature


class Model:
    def __init__(self): self.FeatureManager = Manager()
    def ClearSelection2(self, _all): pass
    def FirstFeature(self): return None


class SplitTests(unittest.TestCase):
    def test_split_contract(self):
        model = Model()
        with patch.dict("os.environ", {"SW_RUN_INTERACTIVE_SPLIT_DIAGNOSTIC": "1"}):
            result = sw_part._split_bodies_experimental(
                model, Tool(), allow_modal=True,
            )
        self.assertIs(result["feature"], model.FeatureManager.feature)
        self.assertEqual(len(result["preview_bodies"]), 2)
        self.assertEqual(len(model.FeatureManager.args), 5)

    def test_requires_tool(self):
        with patch.dict("os.environ", {"SW_RUN_INTERACTIVE_SPLIT_DIAGNOSTIC": "1"}):
            with self.assertRaises(ValueError):
                sw_part._split_bodies_experimental(Model(), (), allow_modal=True)

    def test_experimental_entry_requires_explicit_modal_opt_in(self):
        model = Model()
        with self.assertRaisesRegex(RuntimeError, "allow_modal=True"):
            sw_part._split_bodies_experimental(model, Tool())
        self.assertIsNone(model.FeatureManager.args)

    def test_experimental_entry_requires_environment_opt_in(self):
        model = Model()
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(
                RuntimeError, "SW_RUN_INTERACTIVE_SPLIT_DIAGNOSTIC=1",
            ):
                sw_part._split_bodies_experimental(
                    model, Tool(), allow_modal=True,
                )
        self.assertIsNone(model.FeatureManager.args)

    def test_public_entry_is_blocked(self):
        with self.assertRaisesRegex(RuntimeError, "interactive Save As"):
            sw_part.split_bodies(Model(), Tool(), save_paths=("a.SLDPRT", "b.SLDPRT"))


if __name__ == "__main__":
    unittest.main()
