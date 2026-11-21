"""Real SolidWorks regression for a native multi-body Indent feature."""

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
        box = tuple(float(value) * 1000.0 for value in get_com_member(body, "GetBodyBox"))
        rows.append((volume, box, body))
    rows.sort(key=lambda row: row[0], reverse=True)
    return rows


def _tool_face(body, expected_area):
    matches = []
    for face in tuple(get_com_member(body, "GetFaces") or ()):
        try:
            geometry = sw_part.planar_face_geometry(face)
        except (TypeError, ValueError, RuntimeError):
            continue
        if math.isclose(geometry["area"], expected_area, abs_tol=1e-9):
            matches.append((geometry["center"], face))
    if not matches:
        raise RuntimeError("no planar tool-body region face matched the cylinder end")
    matches.sort(key=lambda item: item[0])
    return matches[-1][1]


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    completed = False
    try:
        with sw_part.sketch(model, "Front Plane") as target_sketch:
            sw_part.sketch_rectangle(model, 0.0, 0.0, .060, .040)
        target_feature = sw_part.extrude_boss(
            model, target_sketch, .010, merge=True,
        )
        with sw_part.sketch(model, "Front Plane") as tool_sketch:
            sw_part.sketch_circle(model, 0.0, 0.0, .008)
        tool_feature = sw_part.extrude_boss(
            model, tool_sketch, .015, merge=False,
        )

        before = _body_rows(model)
        if len(before) != 2:
            raise RuntimeError(f"expected two overlapping source bodies, found {len(before)}")
        target_body, tool_body = before[0][2], before[1][2]
        tool_face = _tool_face(tool_body, math.pi * .008 * .008)
        before_total = sum(row[0] for row in before)

        indent = sw_part.indent_feature(
            model, target_body, (tool_face,),
            thickness=.002, clearance=.001,
            exclude_selected_regions=True,
            clearance_direction=True,
            cut=False,
        )
        evidence = sw_part.indent_feature_evidence(indent, model)
        after = _body_rows(model)
        after_total = sum(row[0] for row in after)

        if not math.isclose(evidence["thickness"] * 1000.0, 2.0, abs_tol=1e-9):
            raise RuntimeError(f"Indent thickness mismatch: {evidence}")
        if not math.isclose(evidence["clearance"] * 1000.0, 1.0, abs_tol=1e-9):
            raise RuntimeError(f"Indent clearance mismatch: {evidence}")
        if evidence["is_cut"] or evidence["body_count"] < 1 or evidence["tool_region_count"] < 1:
            raise RuntimeError(f"Indent FeatureData mismatch: {evidence}")
        if math.isclose(after_total, before_total, abs_tol=1e-5):
            raise RuntimeError(
                f"Indent did not change solid geometry: before={before_total}, after={after_total}"
            )
        if not bool(get_com_member(model, "ForceRebuild3", False)):
            raise RuntimeError("Indent rebuild failed")
        if any(int(get_com_member(feature, "GetErrorCode") or 0) != 0 for feature in (
            target_feature, tool_feature, indent,
        )):
            raise RuntimeError("Indent feature tree contains an error")

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
