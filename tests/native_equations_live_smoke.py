"""Real SolidWorks regression for global variables and dimension equations."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_equations, sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    try:
        with sw_part.sketch(model, "Front Plane") as sketch_name:
            sw_part.sketch_rectangle(model, 0, 0, .040, .030)
        feature = sw_part.extrude_boss_midplane(model, sketch_name, .010)
        if feature is None:
            raise RuntimeError("equation regression base failed")
        depth = get_com_member(feature, "Parameter", "D1")
        if depth is None:
            raise RuntimeError("extrusion depth dimension D1 was not found")
        full_name = str(get_com_member(depth, "FullName")).rsplit("@", 1)[0]

        global_row = sw_equations.add_global_variable(model, "DepthGV", "18mm")
        dimension_row = sw_equations.add_dimension_equation(
            model, full_name, '"DepthGV"'
        )
        evaluation = sw_equations.evaluate_equations(model)
        actual_depth = float(get_com_member(depth, "SystemValue"))
        bounds = [float(value) * 1000.0 for value in get_com_member(model, "GetPartBox", True)]
        extents = [abs(bounds[index + 3] - bounds[index]) for index in range(3)]
        if abs(actual_depth - .018) > 1e-8:
            raise RuntimeError(f"dimension equation depth mismatch: {actual_depth}")
        if abs(max(extents) - 40.0) > 1e-5 or not any(abs(value - 18.0) < 1e-5 for value in extents):
            raise RuntimeError(f"equation-driven geometry mismatch: {extents}")
        rows = sw_equations.equation_rows(model)
        disabled_count = int(get_com_member(sw_equations.equation_manager(model), "GetDisabledEquationCount"))
        if len(rows) != 2 or not rows[0]["global_variable"] or rows[1]["global_variable"]:
            raise RuntimeError(f"equation classification mismatch: {rows}")
        if [row["value_status"] for row in rows] != [0, 1]:
            raise RuntimeError(f"equation value status mismatch: {rows}")
        if disabled_count != 0:
            raise RuntimeError(f"an equation was disabled: count={disabled_count}, rows={rows}")
        print(json.dumps({
            "status": "ok",
            "global_variable": global_row,
            "dimension_equation": dimension_row,
            "depth_dimension": full_name,
            "actual_depth_mm": actual_depth * 1000.0,
            "extents_mm": extents,
            "evaluation": evaluation,
        }, ensure_ascii=False))
    finally:
        try:
            sw.QuitDoc(title)
        except Exception:
            pass
        if original_title:
            try:
                sw.ActivateDoc2(original_title, False, 0)
            except Exception:
                pass


if __name__ == "__main__":
    main()
