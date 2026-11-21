"""Offline contracts for non-interactive design-table inspection."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import sw_document_data


class Table:
    def GetTitle(self): return "Family Table"
    def IsActive(self): return False
    def GetTotalRowCount(self): return 4
    def GetTotalColumnCount(self): return 3
    def GetVisibleRowCount(self): return 4
    def GetVisibleColumnCount(self): return 3
    def GetStartRowNumber(self): return 1
    def GetStartColumnNumber(self): return 1


class Model:
    def __init__(self, table=None):
        self.table = table
        self.Extension = type("Extension", (), {"HasDesignTable": table is not None})()
    def GetDesignTable(self): return self.table


class PhantomTable(Table):
    def GetTotalRowCount(self): return -2
    def GetTotalColumnCount(self): return -2
    def GetVisibleRowCount(self): return -2
    def GetVisibleColumnCount(self): return -2
    def GetStartRowNumber(self): return -2
    def GetStartColumnNumber(self): return -2


class DesignTableInspectionTests(unittest.TestCase):
    def test_reports_absent_table_without_ui_calls(self):
        self.assertEqual(sw_document_data.inspect_design_table(Model()), {
            "exists": False, "title": "", "active": False,
            "total_rows": 0, "total_columns": 0,
            "visible_rows": 0, "visible_columns": 0,
            "start_row": None, "start_column": None,
        })

    def test_reads_existing_table_metadata(self):
        result = sw_document_data.inspect_design_table(Model(Table()))
        self.assertTrue(result["exists"]); self.assertEqual(result["title"], "Family Table")
        self.assertEqual((result["total_rows"], result["total_columns"]), (4, 3))
        self.assertEqual((result["start_row"], result["start_column"]), (1, 1))

    def test_negative_extent_dispatch_is_treated_as_absent(self):
        model = Model(PhantomTable())
        model.Extension.HasDesignTable = True
        self.assertFalse(sw_document_data.inspect_design_table(model)["exists"])


if __name__ == "__main__":
    unittest.main()
