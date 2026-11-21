"""Real SolidWorks regression for multi-configuration rebuild and geometry audit."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_document_data, sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    success = False
    try:
        with sw_part.sketch(model, "Front Plane") as sketch_name:
            sw_part.sketch_rectangle(model, 0.0, 0.0, 0.080, 0.050)
        feature = sw_part.extrude_boss(model, sketch_name, 0.012)
        if feature is None or int(get_com_member(feature, "GetErrorCode")) != 0:
            raise RuntimeError("base extrusion failed")
        feature_name = str(get_com_member(feature, "Name"))
        dimension_name = f"D1@{feature_name}"
        default_name = sw_document_data.inspect_configurations(model)["active_configuration"]
        depths = {default_name: 12.0, "薄型": 6.0, "加强型": 20.0}
        family = sw_document_data.apply_configuration_family(model, tuple(
            {"name": name, "dimensions_mm": {dimension_name: depth}}
            for name, depth in depths.items()
        ))
        if not family["success"]:
            raise RuntimeError(f"configuration family failed: {family}")

        audit = sw_document_data.audit_configuration_rebuilds(model)
        if not audit["success"]:
            raise RuntimeError(f"configuration audit failed: {audit}")
        rows = {row["configuration"]: row for row in audit["configurations"]}
        for name, depth in depths.items():
            row = rows[name]
            expected_volume = 80.0 * 50.0 * depth
            if row["solid_body_count"] != 1:
                raise RuntimeError(f"body count mismatch for {name}: {row}")
            if not math.isclose(row["volumes_mm3"][0], expected_volume, abs_tol=1e-3):
                raise RuntimeError(f"volume mismatch for {name}: {row}")
            box = row["combined_bounding_box_mm"]
            if not math.isclose(box[5] - box[2], depth, abs_tol=1e-6):
                raise RuntimeError(f"depth mismatch for {name}: {box}")
            if row["feature_errors"] or row["needs_rebuild_after"]:
                raise RuntimeError(f"rebuild evidence mismatch for {name}: {row}")
        if audit["active_after"] != default_name or not audit["restored_active"]:
            raise RuntimeError(f"active configuration not restored: {audit}")

        success = True
        print(json.dumps({
            "status": "ok",
            "document": title,
            "saved": False,
            "dimension": dimension_name,
            "audit": audit,
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
