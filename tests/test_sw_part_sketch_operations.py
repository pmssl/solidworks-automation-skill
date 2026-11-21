"""Offline contracts for native sketch transform/edit operations."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class Entity:
    def __init__(self, model): self.model = model
    def GetName(self): return "Line1"
    def Select2(self, append, mark):
        if not append: self.model.selected = []
        self.model.selected.append(self)
        return mark == 0
    def Select4(self, append, select_data):
        if not append: self.model.selected = []
        self.model.selected.append(self)
        return select_data.Mark == 0


class SelectData:
    X = Y = Z = 0.0
    Mark = 0


class SelectionManager:
    def CreateSelectData(self): return SelectData()


class Extension:
    def __init__(self, model): self.model = model
    def SelectByID2(self, _name, _kind, _x, _y, _z, append, mark, _callout, _option):
        if not append: self.model.selected = []
        self.model.selected.append("named")
        return mark == 0


class Sketch:
    def __init__(self): self.segments = []
    def GetSketchSegments(self): return self.segments


class Manager:
    def __init__(self, model): self.model = model; self.ActiveSketch = Sketch(); self.calls = []
    def _add(self, kind, args, amount=1):
        self.calls.append((kind, args)); self.ActiveSketch.segments.extend(object() for _ in range(amount)); return True
    def SketchUseEdge3(self, *args): return self._add("convert", args)
    def SketchOffset2(self, *args): return self._add("offset", args)
    def SketchTrim(self, *args): self.calls.append(("trim", args)); return True
    def SketchExtend(self, *args): self.calls.append(("extend", args)); return True
    def CreateLinearSketchStepAndRepeat(self, *args): return self._add("linear", args, 2)
    def CreateCircularSketchStepAndRepeat(self, *args): return self._add("circular", args, 3)


class CircleManager(Manager):
    def CreateCircleByRadius(self, *args):
        self.ActiveSketch.segments.append("created-circle")
        return None


class MarkEntity(Entity):
    def Select2(self, append, mark):
        if not append: self.model.selected = []
        self.model.selected.append((self, mark))
        return mark in (1, 2)


class Model:
    def __init__(self):
        self.selected = []
        self.SketchManager = Manager(self)
        self.SelectionManager = SelectionManager()
        self.Extension = Extension(self)
    def ClearSelection2(self, _all): self.selected = []
    def SketchMirror(self):
        self.SketchManager.ActiveSketch.segments.append("mirrored")


class SketchOperationTests(unittest.TestCase):
    def test_convert_offset_and_edit_operations(self):
        model, entity = Model(), None
        entity = Entity(model)
        self.assertEqual(len(sw_part.sketch_convert_entities(model, entity, chain=True)), 1)
        self.assertEqual(len(sw_part.sketch_offset_entities(model, entity, .003, chain=True)), 1)
        sw_part.sketch_trim(model, 1, ((entity, (.01, .02, 0)),))
        sw_part.sketch_extend(model, entity, pick_point=(-.01, .04, 0))
        self.assertEqual([item[0] for item in model.SketchManager.calls],
                         ["convert", "offset", "trim", "extend"])

    def test_linear_and_circular_pattern_argument_counts(self):
        model, entity = Model(), None
        entity = Entity(model)
        sw_part.linear_sketch_pattern(model, entity, 3, .01, count_y=2, spacing_y=.02)
        linear_args = model.SketchManager.calls[0][1]
        self.assertEqual(len(linear_args), 12)
        self.assertEqual(linear_args[:4], (3, 2, .01, .02))
        sw_part.circular_sketch_pattern(model, entity, .025, 3.0, 5)
        circular_args = model.SketchManager.calls[1][1]
        self.assertEqual(len(circular_args), 9)
        self.assertEqual(circular_args[:4], (.025, 3.0, 5, .6))

    def test_invalid_operation_parameters_are_rejected(self):
        model, entity = Model(), None
        entity = Entity(model)
        with self.assertRaises(ValueError): sw_part.sketch_offset_entities(model, entity, 0)
        with self.assertRaises(ValueError): sw_part.linear_sketch_pattern(model, entity, 1, .01)
        with self.assertRaises(ValueError): sw_part.circular_sketch_pattern(model, entity, .02, 3.0, 1)

    def test_circle_recovers_created_segment_when_com_returns_none(self):
        model = Model()
        model.SketchManager = CircleManager(model)
        self.assertEqual(sw_part.sketch_circle(model, 0, 0, .002), "created-circle")

    def test_sketch_mirror_uses_native_selection_marks(self):
        model = Model()
        seed, axis = MarkEntity(model), MarkEntity(model)
        self.assertEqual(sw_part.sketch_mirror_entities(model, seed, axis), ("mirrored",))


if __name__ == "__main__":
    unittest.main()
