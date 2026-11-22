"""Prevent pure geometry live regressions from opening save dialogs."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


TESTS_DIR = Path(__file__).resolve().parent
PERSISTENCE_REGRESSIONS = {
    "native_extrude_end_conditions_live_smoke.py",
    "native_persistent_edge_vertex_topology_live_smoke.py",
    "native_persistent_reference_live_smoke.py",
}


class NativeLiveNoPersistenceTests(unittest.TestCase):
    def test_geometry_live_smokes_do_not_call_save_or_ui_apis(self):
        violations = []
        for path in sorted(TESTS_DIR.glob("native_*_live_smoke.py")):
            if path.name in PERSISTENCE_REGRESSIONS:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                function = node.func
                name = function.id if isinstance(function, ast.Name) else None
                attribute = function.attr if isinstance(function, ast.Attribute) else None
                if name == "save_document" or attribute in {
                    "save", "SaveAs", "SaveAs2", "SaveAs3", "Save3",
                    # CloseDoc is documented as discarding dirty documents,
                    # but QuitDoc expresses that contract unambiguously and
                    # cannot be confused with a save-capable lifecycle path.
                    "CloseDoc",
                    # UI command IDs can open modal PropertyManagers or file
                    # dialogs and do not belong in unattended geometry smokes.
                    "RunCommand",
                }:
                    violations.append(f"{path.name}:{node.lineno}")
        self.assertEqual([], violations)


if __name__ == "__main__":
    unittest.main()
