"""Offline contracts for native equations and global variables."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_equations


class Manager:
    def __init__(self): self.rows = []; self.last_status = -1
    def GetCount(self): return len(self.rows)
    def Add2(self, index, equation, solve):
        row = {"equation": equation, "value": .018 if "DepthGV" in equation else 0.0,
               "global": equation.startswith('"DepthGV"'), "disabled": False}
        self.rows.append(row); return len(self.rows) - 1
    def Equation(self, index): return self.rows[index]["equation"]
    def Value(self, index): self.last_status = index; return self.rows[index]["value"]
    def GlobalVariable(self, index): return self.rows[index]["global"]
    def Disabled(self, index): return self.rows[index]["disabled"]
    def GetConfigurationOption(self, index): return 1
    def GetDisabledEquationCount(self): return 0
    def EvaluateAll(self): return 0
    @property
    def Status(self): return self.last_status


class Model:
    def __init__(self): self.manager = Manager()
    def GetEquationMgr(self): return self.manager
    def ForceRebuild3(self, _top_only): return True


class EquationTests(unittest.TestCase):
    def test_global_and_dimension_equations_round_trip(self):
        model = Model()
        global_row = sw_equations.add_global_variable(model, "DepthGV", "18mm")
        dimension_row = sw_equations.add_dimension_equation(
            model, "D1@Boss-Extrude1", '"DepthGV"'
        )
        self.assertTrue(global_row["global_variable"])
        self.assertFalse(dimension_row["global_variable"])
        self.assertAlmostEqual(sw_equations.global_variable_value(model, "DepthGV"), .018)
        evaluated = sw_equations.evaluate_equations(model)
        self.assertTrue(evaluated["evaluate_return_is_documented_ambiguous"] is False)

    def test_invalid_equations_are_rejected(self):
        model = Model()
        with self.assertRaises(ValueError): sw_equations.add_equation(model, "no assignment")
        with self.assertRaises(ValueError): sw_equations.add_global_variable(model, 'bad"name', "1mm")
        with self.assertRaises(ValueError): sw_equations.add_dimension_equation(model, "", "1mm")


if __name__ == "__main__":
    unittest.main()
