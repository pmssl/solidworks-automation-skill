"""Offline contracts for native ruled surfaces."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_part


class Data:
    Type = 2
    Distance = .01
    Angle = 0.0
    UseVector = False
    TrimAndKnit = False
    Connect = False

    def __init__(self):
        self.references = ()
        self.accessed = 0
        self.released = 0

    def AccessSelections(self, model, component):
        self.accessed += 1
        return True

    def ReleaseSelectionAccess(self):
        self.released += 1

    def SetDirectionReference(self, first, second):
        self.references = (first,) if second is None else (first, second)

    def GetDirectionReference(self):
        return (len(self.references), None, 0, None, 0)


class Feature:
    Name = "Ruled Surface1"

    def __init__(self):
        self.data = Data()
        self.modified = 0

    def GetTypeName2(self): return "RuledSurface"
    def GetDefinition(self): return self.data
    def GetErrorCode(self): return 0
    def ModifyDefinition(self, data, model, component):
        self.modified += 1
        return True


class Edge:
    def __init__(self): self.marks = []
    def Select2(self, append, mark): self.marks.append((append, mark)); return mark in (4, 6)


class Manager:
    def __init__(self): self.args = None; self.feature = Feature()
    def InsertRuledSurfaceFromEdge2(self, *args): self.args = args; return self.feature


class Model:
    def __init__(self): self.FeatureManager = Manager()
    def ClearSelection2(self, _all): pass
    def FirstFeature(self): return None


class RuledSurfaceTests(unittest.TestCase):
    def test_normal_surface_contract(self):
        model, edge = Model(), Edge()
        feature = sw_part.ruled_surface_from_edges(model, edge, .01, alternate_face=True)
        self.assertIs(feature, model.FeatureManager.feature)
        self.assertEqual(edge.marks, [(False, 6)])
        self.assertEqual(model.FeatureManager.args, (1, .01, False, False, False, 0.0,
                                                       False, 0.0, 0.0, 0.0, False))

    def test_invalid_inputs(self):
        model = Model()
        with self.assertRaises(ValueError): sw_part.ruled_surface_from_edges(model, (), .01)
        with self.assertRaises(ValueError): sw_part.ruled_surface_from_edges(model, Edge(), 0)
        with self.assertRaises(ValueError): sw_part.ruled_surface_from_edges(model, Edge(), .01, surface_type=9)
        with self.assertRaises(ValueError): sw_part.ruled_surface_from_edges(model, Edge(), .01, surface_type=2)
        with self.assertRaises(ValueError): sw_part.ruled_surface_from_edges(
            model, Edge(), .01, surface_type=4, direction_vector=(0, 0, 0),
        )

    def test_vector_mode_contract(self):
        model, edge = Model(), Edge()
        sw_part.ruled_surface_from_edges(
            model, edge, .01, surface_type=4, direction_vector=(0, 0, 2),
        )
        self.assertEqual(
            model.FeatureManager.args,
            (4, .01, False, False, False, 0.0, True, 0.0, 0.0, 1.0, False),
        )

    def test_tapered_reference_mode_uses_feature_data(self):
        model, edge, reference = Model(), Edge(), object()
        feature = sw_part.ruled_surface_from_edges(
            model, edge, .01, surface_type=2,
            angle_rad=.25, direction_references=(reference,),
        )
        self.assertEqual(
            model.FeatureManager.args,
            (1, .01, False, False, False, .25, False, 0.0, 0.0, 0.0, False),
        )
        self.assertEqual(feature.data.references, (reference,))
        self.assertEqual(feature.data.Type, 3)
        self.assertEqual(feature.data.Distance, .01)
        self.assertEqual(feature.data.Angle, .25)
        self.assertFalse(feature.data.UseVector)
        self.assertEqual(feature.modified, 1)
        self.assertEqual(feature.data.released, 1)

    def test_reads_ruled_surface_evidence(self):
        feature, model = Feature(), Model()
        feature.data.Type = 4
        feature.data.Distance = .012
        feature.data.Angle = .3
        feature.data.references = (object(),)
        evidence = sw_part.ruled_surface_evidence(feature, model)
        self.assertEqual(evidence["type"], 4)
        self.assertEqual(evidence["distance"], .012)
        self.assertEqual(evidence["angle"], .3)
        self.assertEqual(evidence["direction_reference_count"], 1)
        self.assertEqual(evidence["error_code"], 0)
        self.assertEqual(feature.data.released, 1)


if __name__ == "__main__":
    unittest.main()
