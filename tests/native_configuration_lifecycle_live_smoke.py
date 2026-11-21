"""Live native configuration rename and dependency-safe deletion regression."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_document_data, sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def body_evidence(model):
    bodies = tuple(model.GetBodies2(0, True) or ())
    if len(bodies) != 1:
        raise RuntimeError(f"expected one solid body, got {len(bodies)}")
    box = tuple(round(float(value) * 1000.0, 6) for value in bodies[0].GetBodyBox())
    return {"solid_body_count": len(bodies), "body_box_mm": box}


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
        if feature is None or int(get_com_member(feature, "GetErrorCode")) != 0:
            raise RuntimeError("base feature creation failed")
        baseline = body_evidence(model)
        default_name = sw_document_data.inspect_configurations(model)["active_configuration"]
        parent = sw_document_data.create_configuration(
            model, "父配置", activate=False, rebuild=True, save=False,
        )
        child = sw_document_data.create_derived_configuration(
            model, "子配置", "父配置", rebuild=True, restore_active=True,
        )
        grand = sw_document_data.create_derived_configuration(
            model, "孙配置", "子配置", rebuild=True, restore_active=True,
        )
        if not all(item["success"] for item in (parent, child, grand)):
            raise RuntimeError(f"configuration creation failed: {parent}, {child}, {grand}")

        renamed = sw_document_data.rename_configuration(
            model, "父配置", "生产族", rebuild=True,
        )
        if not renamed["success"]:
            raise RuntimeError(f"configuration rename failed: {renamed}")
        renamed_nodes = renamed["hierarchy_after"]["configurations"]
        if renamed_nodes["子配置"]["parent"] != "生产族":
            raise RuntimeError(f"child parent was not updated: {renamed_nodes}")

        active = sw_document_data.activate_configuration(
            model, "孙配置", rebuild=True, save=False,
        )
        if not active["success"]:
            raise RuntimeError(f"grandchild activation failed: {active}")
        deleted = sw_document_data.delete_configuration(
            model,
            "生产族",
            include_descendants=True,
            fallback_configuration=default_name,
            rebuild=True,
        )
        if not deleted["success"]:
            raise RuntimeError(f"configuration subtree deletion failed: {deleted}")
        if deleted["delete_order"] != ["孙配置", "子配置", "生产族"]:
            raise RuntimeError(f"unexpected deletion order: {deleted['delete_order']}")
        if deleted["configurations_after"] != [default_name]:
            raise RuntimeError(f"unexpected remaining configurations: {deleted}")
        final = body_evidence(model)
        if final != baseline:
            raise RuntimeError(f"geometry changed across lifecycle: {baseline} -> {final}")
        if int(get_com_member(feature, "GetErrorCode")) != 0:
            raise RuntimeError("base feature has a rebuild error after lifecycle")
        success = True
        print(json.dumps({
            "status": "ok",
            "document": title,
            "saved": False,
            "renamed": ["父配置", "生产族"],
            "renamed_child_parent": renamed_nodes["子配置"]["parent"],
            "delete_order": deleted["delete_order"],
            "fallback_configuration": deleted["fallback_configuration"],
            "configurations_after": deleted["configurations_after"],
            "active_configuration": deleted["active_after"],
            "geometry_before": baseline,
            "geometry_after": final,
            "feature_error_code": int(get_com_member(feature, "GetErrorCode")),
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
