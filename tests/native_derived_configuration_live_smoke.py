"""Real SolidWorks regression for a two-level derived configuration tree."""

from __future__ import annotations

import json
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
            sw_part.sketch_rectangle(model, 0.0, 0.0, 0.070, 0.040)
        feature = sw_part.extrude_boss(model, sketch_name, 0.012)
        if feature is None:
            raise RuntimeError("base feature creation failed")
        default_name = sw_document_data.inspect_configurations(model)["active_configuration"]
        child = sw_document_data.create_derived_configuration(
            model, "派生一级", default_name, comment="native hierarchy regression",
        )
        grandchild = sw_document_data.create_derived_configuration(
            model, "派生二级", "派生一级", comment="native hierarchy regression",
        )
        hierarchy = sw_document_data.configuration_hierarchy(model)
        nodes = hierarchy["configurations"]
        if not child["success"] or not grandchild["success"]:
            raise RuntimeError(f"derived configuration creation failed: {child}, {grandchild}")
        if nodes["派生一级"]["parent"] != default_name or nodes["派生二级"]["parent"] != "派生一级":
            raise RuntimeError(f"derived hierarchy mismatch: {hierarchy}")
        if "派生一级" not in nodes[default_name]["children"] or "派生二级" not in nodes["派生一级"]["children"]:
            raise RuntimeError(f"derived child lists mismatch: {hierarchy}")
        if hierarchy["active_configuration"] != default_name or not bool(model.ForceRebuild3(False)):
            raise RuntimeError(f"derived hierarchy did not restore/rebuild: {hierarchy}")
        success = True
        print(json.dumps({
            "status": "ok", "document": title, "saved": False,
            "active_configuration": hierarchy["active_configuration"],
            "hierarchy": nodes,
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
