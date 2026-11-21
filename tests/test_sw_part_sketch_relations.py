"""Offline contracts for native sketch-relation management."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class Relation:
    def __init__(self, entities, relation_type=4):
        self.entities = list(entities)
        self.Suppressed = False
        self.relation_type = relation_type

    def GetRelationType(self):
        return self.relation_type

    def GetEntitiesCount(self):
        return len(self.entities)

    def ReplaceEntity(self, old, new):
        try:
            index = self.entities.index(old)
        except ValueError:
            return False
        self.entities[index] = new
        return True

    def GetEntities(self):
        return tuple(self.entities)


class RelationManager:
    def __init__(self):
        self.relations = []
        self.fail_type = None

    def GetRelations(self, filter_type):
        if filter_type != 0:
            return ()
        return tuple(self.relations)

    def AddRelation(self, entities, relation_type):
        if relation_type == self.fail_type:
            return None
        relation = Relation(tuple(getattr(entities, "value", entities)), relation_type)
        self.relations.append(relation)
        return relation

    def DeleteRelation(self, relation):
        try:
            self.relations.remove(relation)
        except ValueError:
            return False
        return True


class Entity:
    def __init__(self, model):
        self.model = model

    def Select2(self, append, mark):
        if not append:
            self.model.selected = []
        self.model.selected.append((self, mark))
        return True


class Model:
    def __init__(self):
        self.selected = []
        self.manager = RelationManager()
        self.SketchManager = type("SketchManager", (), {})()
        self.SketchManager.ActiveSketch = type(
            "Sketch", (), {"RelationManager": self.manager}
        )()

    def ClearSelection2(self, _clear_all):
        self.selected = []

    def SketchAddConstraints(self, _relation_type):
        self.manager.relations.append(Relation([item[0] for item in self.selected]))

    def SketchConstraintsDel(self, relation_index, _relation_type):
        del self.manager.relations[relation_index]


class DimensionValue:
    def __init__(self, value):
        self.SystemValue = value
        self.Name = "WidthDrive"
        self.tolerance_type = 2
        self.tolerance_values = (-0.0002, 0.0003)
    def GetToleranceType(self): return self.tolerance_type
    def GetToleranceValues(self): return self.tolerance_values
    def SetToleranceType(self, value): self.tolerance_type = value; return True
    def SetToleranceValues(self, minimum, maximum): self.tolerance_values = (minimum, maximum); return True


class Annotation:
    def __init__(self, attached, selectable=False):
        self.attached = tuple(attached)
        self.selectable = selectable

    def GetAttachedEntities3(self):
        return self.attached

    def Select3(self, _append, _data):
        return self.selectable


class DisplayDimension:
    def __init__(self, value, attached, name="D1@Sketch1", selectable=False):
        self.dimension = DimensionValue(value)
        self.annotation = Annotation(attached, selectable)
        self.name = name

    def GetDimension2(self, _index):
        return self.dimension

    def GetAnnotation(self):
        return self.annotation

    def GetNameForSelection(self):
        return self.name


class DimensionExtension:
    def __init__(self, model):
        self.model = model

    def SelectByID2(self, name, entity_type, *_args):
        if name == "D1@Sketch1" and entity_type == "DIMENSION":
            self.model.dimension_selected = True
            return True
        return False

    def DeleteSelection2(self, _options):
        if not self.model.dimension_selected:
            return False
        self.model.deleted = True
        return True


class DimensionModel(Model):
    def __init__(self):
        super().__init__()
        self.dimension_selected = False
        self.deleted = False
        self.Extension = DimensionExtension(self)

    def AddDimension2(self, _x, _y, _z):
        return DisplayDimension(0.025, [item[0] for item in self.selected], "D2@Sketch1")


class SketchRelationTests(unittest.TestCase):
    def test_add_enumerate_suppress_and_replace(self):
        model = Model()
        old = Entity(model)
        new = Entity(model)

        added = sw_part.add_sketch_relation_to_entities(model, (old,), "sgHORIZONTAL2D")
        self.assertEqual(len(added), 1)
        relation = added[0]
        self.assertEqual(
            sw_part.sketch_relation_summary(relation),
            {"type": 4, "entity_count": 1, "suppressed": False},
        )
        self.assertTrue(sw_part.set_sketch_relation_suppressed(relation, True))
        sw_part.replace_sketch_relation_entity(relation, old, new)
        self.assertEqual(relation.entities, [new])

    def test_direct_relation_manager_entry_returns_typed_relation(self):
        model = Model(); first = Entity(model); second = Entity(model)
        relation = sw_part.add_sketch_relation_direct(model, (first, second), 14)
        self.assertEqual(
            sw_part.sketch_relation_summary(relation),
            {"type": 14, "entity_count": 2, "suppressed": False},
        )
        self.assertEqual(relation.entities, [first, second])

    def test_direct_relation_manager_rejects_invalid_constraint_type(self):
        with self.assertRaises(ValueError):
            sw_part.add_sketch_relation_direct(Model(), (Entity(Model()),), 0)

    def test_direct_relation_batch_creates_all_relations(self):
        model = Model(); first = Entity(model); second = Entity(model)
        relations = sw_part.add_sketch_relations_direct_batch(
            model, (((first,), 4), ((second,), 4), ((first, second), 14)),
        )
        self.assertEqual([item.GetRelationType() for item in relations], [4, 4, 14])
        self.assertEqual(len(model.manager.relations), 3)

    def test_direct_relation_batch_rolls_back_partial_failure(self):
        model = Model(); first = Entity(model); second = Entity(model)
        model.manager.fail_type = 14
        with self.assertRaises(RuntimeError):
            sw_part.add_sketch_relations_direct_batch(
                model, (((first,), 4), ((first, second), 14)),
            )
        self.assertEqual(model.manager.relations, [])

    def test_relation_entity_batch_replaces_across_multiple_relations(self):
        model = Model(); old = Entity(model); new = Entity(model); other = Entity(model)
        horizontal = Relation([old], 4); equal = Relation([old, other], 14)
        result = sw_part.replace_sketch_relation_entities_batch(
            ((horizontal, old, new), (equal, old, new)),
        )
        self.assertEqual(result, (horizontal, equal))
        self.assertEqual(horizontal.entities, [new]); self.assertEqual(equal.entities, [new, other])

    def test_relation_entity_batch_rolls_back_when_later_relation_rejects(self):
        model = Model(); old = Entity(model); new = Entity(model); missing = Entity(model)
        first = Relation([old], 4); second = Relation([missing], 4)
        with self.assertRaises(RuntimeError):
            sw_part.replace_sketch_relation_entities_batch(
                ((first, old, new), (second, old, new)),
            )
        self.assertEqual(first.entities, [old]); self.assertEqual(second.entities, [missing])

    def test_delete_relation_uses_selected_entity_and_index(self):
        model = Model()
        entity = Entity(model)
        model.manager.relations.append(Relation([entity]))

        result = sw_part.delete_sketch_relation(model, entity, 0, "sgHORIZONTAL2D")

        self.assertEqual(result, {"deleted": 1, "remaining": 0})
        self.assertEqual(model.selected, [])

    def test_validation_rejects_invalid_filter_and_relation_name(self):
        model = Model()
        with self.assertRaises(ValueError):
            sw_part.sketch_relations(model, filter_type=8)
        with self.assertRaises(ValueError):
            sw_part.add_sketch_relation_to_entities(model, (Entity(model),), "horizontal")

    def test_rebind_dimension_recreates_and_preserves_value(self):
        model = DimensionModel()
        old_entity = Entity(model)
        new_entity = Entity(model)
        old = DisplayDimension(0.010, (old_entity,))

        result = sw_part.rebind_sketch_dimension(
            model, old, (new_entity,), 0.0125, 0.025
        )

        self.assertTrue(model.deleted)
        self.assertEqual(result["strategy"], "delete_recreate")
        self.assertAlmostEqual(result["value"], 0.010)
        self.assertEqual(result["attached_count"], 1)
        self.assertEqual(result["name"], "WidthDrive")
        self.assertEqual(result["tolerance"], {
            "type": 2, "values": (-0.0002, 0.0003),
        })


if __name__ == "__main__":
    unittest.main()
