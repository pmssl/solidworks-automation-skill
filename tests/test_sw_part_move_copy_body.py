"""Offline contracts for native Move/Copy Body."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class Body:
    def __init__(self, model): self.model = model
    def Select2(self, append, mark):
        if not append: self.model.selected = []
        self.model.selected.append((self, mark)); return mark == 1


class Manager:
    def __init__(self): self.args = None
    def InsertMoveCopyBody2(self, *args): self.args = args; return object()


class Model:
    def __init__(self): self.selected = []; self.FeatureManager = Manager()
    def ClearSelection2(self, _all): self.selected = []


class MoveCopyBodyTests(unittest.TestCase):
    def test_non_symmetric_transform_argument_order(self):
        model = Model(); body = Body(model)
        sw_part.move_copy_bodies(
            model, body, translation=(.007, -.004, .003),
            rotation_origin=(.001, .002, .003), rotation=(.1, .2, .3),
            copy=True, copies=2,
        )
        self.assertEqual(model.FeatureManager.args,
                         (.007, -.004, .003, 0.0, .001, .002, .003,
                          .1, .2, .3, True, 2))

    def test_invalid_move_copy_inputs_are_rejected(self):
        model = Model(); body = Body(model)
        with self.assertRaises(ValueError): sw_part.move_copy_bodies(model, ())
        with self.assertRaises(ValueError): sw_part.move_copy_bodies(model, body, copies=0)


if __name__ == "__main__":
    unittest.main()
