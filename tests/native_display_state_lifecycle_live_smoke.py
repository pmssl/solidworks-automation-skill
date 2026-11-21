"""Real SolidWorks regression for display-state lifecycle operations."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_document_data, sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def main():
    sw, original_doc = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original_doc, "GetTitle")) if original_doc else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    success = False
    try:
        with sw_part.sketch(model, "Front Plane") as sketch_name:
            sw_part.sketch_rectangle(model, 0.0, 0.0, 0.060, 0.040)
        feature = sw_part.extrude_boss(model, sketch_name, 0.010)
        if feature is None:
            raise RuntimeError("base feature creation failed")
        before = sw_document_data.inspect_display_states(model)
        original_state = before["active_display_state"]
        created = sw_document_data.create_display_state(model, "Review", activate=True)
        renamed = sw_document_data.rename_display_state(model, "Review", "Inspection")
        active_original = sw_document_data.activate_display_state(model, original_state)
        deleted = sw_document_data.delete_display_state(model, "Inspection")
        after = sw_document_data.inspect_display_states(model)
        if not all(item["success"] for item in (created, renamed, active_original, deleted)):
            raise RuntimeError("display-state lifecycle operation failed")
        if after["display_states"] != before["display_states"] or after["count"] != before["count"]:
            raise RuntimeError(f"display-state lifecycle did not restore baseline: {before}, {after}")
        if not bool(model.ForceRebuild3(False)):
            raise RuntimeError("display-state model rebuild failed")
        success = True
        print(json.dumps({
            "status": "ok", "document": title, "saved": False,
            "configuration": after["configuration"],
            "baseline_states": before["display_states"],
            "created_states": created["states_after"],
            "renamed_states": renamed["after"]["display_states"],
            "restored_states": after["display_states"],
            "active_display_state": after["active_display_state"],
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
