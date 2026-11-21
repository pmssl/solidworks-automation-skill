"""Live readback of IConfiguration parameters with resolved geometry evidence."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_document_data, sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def body_box_mm(model):
    bodies = tuple(model.GetBodies2(0, True) or ())
    if len(bodies) != 1:
        raise RuntimeError(f"expected one solid body, got {len(bodies)}")
    return tuple(float(value) * 1000.0 for value in bodies[0].GetBodyBox())


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    success = False
    try:
        with sw_part.sketch(model, "Front Plane") as sketch_name:
            sw_part.sketch_rectangle(model, 0.0, 0.0, 0.050, 0.030)
        feature = sw_part.extrude_boss(model, sketch_name, 0.010)
        if feature is None:
            raise RuntimeError("base feature creation failed")
        feature_name = str(get_com_member(feature, "Name"))
        dimension_name = f"D1@{feature_name}"
        created = sw_document_data.create_configuration(
            model, "参数组", activate=False, rebuild=True, save=False,
        )
        if not created["success"]:
            raise RuntimeError(f"configuration creation failed: {created}")
        seeded = sw_document_data.update_dimension_mm(
            model, dimension_name, 6.0, configuration_mode="specific",
            configuration_names=("参数组",), rebuild=True, save=False,
        )
        if not seeded["success"]:
            raise RuntimeError(f"dimension seeding failed: {seeded}")
        matrix = sw_document_data.read_configuration_parameters(model, "参数组")
        dimension_key = next(
            (key for key in matrix["categories"]["dimensions"]
             if key.casefold() == dimension_name.casefold()),
            None,
        )
        if dimension_key is None:
            raise RuntimeError(f"matrix is missing {dimension_name}: {matrix}")
        activation = sw_document_data.activate_configuration(
            model, "参数组", rebuild=True, save=False,
        )
        dimension = get_com_member(model, "Parameter", dimension_name)
        dimension_mm = float(dimension.GetSystemValue2("参数组")) * 1000.0
        box = body_box_mm(model)
        depth_mm = box[5] - box[2]
        if not activation["success"] or abs(dimension_mm - 6.0) > 1e-6:
            raise RuntimeError(f"resolved dimension mismatch: {dimension_mm}")
        if abs(float(matrix["parameters"][dimension_key]) - 6.0) > 1e-6:
            raise RuntimeError(f"matrix dimension mismatch: {matrix}")
        if abs(depth_mm - 6.0) > 1e-4:
            raise RuntimeError(f"B-Rep depth mismatch: {depth_mm} mm")
        success = True
        print(json.dumps({
            "status": "ok", "document": title, "saved": False,
            "configuration": "参数组", "parameter_count": matrix["reported_count"],
            "dimension": dimension_key, "matrix_value": matrix["parameters"][dimension_key],
            "dimension_mm": dimension_mm, "body_depth_mm": depth_mm,
            "has_design_table": matrix["has_design_table"],
            "review_required": matrix["review_required"],
            "active_configuration": sw_document_data.inspect_configurations(model)["active_configuration"],
        }, ensure_ascii=False))
    finally:
        if success:
            if original_title and original_title != title:
                try:
                    sw.QuitDoc(original_title)
                except Exception:
                    pass
            try:
                sw.ActivateDoc2(title, False, 0)
            except Exception:
                pass
        else:
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
