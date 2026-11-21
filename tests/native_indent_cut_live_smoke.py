"""Real SolidWorks regression for native Indent cut mode."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def _body_rows(model):
    rows = []
    for body in tuple(get_com_member(model, "GetBodies2", 0, False) or ()):
        volume = float(get_com_member(body, "GetMassProperties", 1.0)[3]) * 1e9
        rows.append((volume, body))
    return sorted(rows, key=lambda row: row[0], reverse=True)


def _tool_face(body, area):
    for face in tuple(get_com_member(body, "GetFaces") or ()):
        try:
            geometry = sw_part.planar_face_geometry(face)
        except (TypeError, ValueError, RuntimeError):
            continue
        if math.isclose(geometry["area"], area, abs_tol=1e-9):
            return face
    raise RuntimeError("no planar tool-body end face found")


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    completed = False
    try:
        with sw_part.sketch(model, "Front Plane") as target_sketch:
            sw_part.sketch_rectangle(model, 0.0, 0.0, .060, .040)
        target_feature = sw_part.extrude_boss(model, target_sketch, .010)
        with sw_part.sketch(model, "Front Plane") as tool_sketch:
            sw_part.sketch_circle(model, 0.0, 0.0, .008)
        tool_feature = sw_part.extrude_boss(model, tool_sketch, .015, merge=False)

        before = _body_rows(model)
        if len(before) != 2:
            raise RuntimeError(f"expected two source bodies, found {len(before)}")
        before_total = sum(row[0] for row in before)
        indent = sw_part.indent_feature(
            model, before[0][1], (_tool_face(before[1][1], math.pi * .008 * .008),),
            # InsertIndent is a legacy COM signature and still requires a
            # positive placeholder even though UI cut mode disables thickness.
            thickness=.001, clearance=.0005,
            exclude_selected_regions=True, cut=True, cut_direction=False,
        )
        evidence = sw_part.indent_feature_evidence(indent, model)
        after = _body_rows(model)
        after_total = sum(row[0] for row in after)

        if not evidence["is_cut"]:
            raise RuntimeError(f"Indent cut-mode FeatureData mismatch: {evidence}")
        if not math.isclose(evidence["clearance"] * 1000.0, .5, abs_tol=1e-9):
            raise RuntimeError(f"Indent cut clearance mismatch: {evidence}")
        if not after_total < before_total:
            raise RuntimeError(f"Indent cut did not remove material: {before_total} -> {after_total}")
        if not bool(get_com_member(model, "ForceRebuild3", False)):
            raise RuntimeError("Indent cut rebuild failed")
        if any(int(get_com_member(feature, "GetErrorCode") or 0) != 0 for feature in (
            target_feature, tool_feature, indent,
        )):
            raise RuntimeError("Indent cut feature tree contains an error")

        completed = True
        print(json.dumps({
            "status": "ok", "document": title, "saved": False,
            "feature_data": evidence,
            "before": {"body_count": len(before), "volumes_mm3": [row[0] for row in before], "total_mm3": before_total},
            "after": {"body_count": len(after), "volumes_mm3": [row[0] for row in after], "total_mm3": after_total},
        }, ensure_ascii=False))
    finally:
        if completed:
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
