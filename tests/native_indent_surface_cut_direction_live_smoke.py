"""Real SolidWorks regression for surface-tool Indent cut direction."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def _solid_geometry(model):
    bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
    if len(bodies) != 1:
        raise RuntimeError(f"expected one solid body, found {len(bodies)}")
    body = bodies[0]
    box = tuple(float(value) * 1000.0 for value in get_com_member(body, "GetBodyBox"))
    volume = float(get_com_member(body, "GetMassProperties", 1.0)[3]) * 1e9
    return body, {"box_mm": box, "volume_mm3": volume}


def _run_case(sw, cut_direction):
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    completed = False
    try:
        with sw_part.sketch(model, "Front Plane") as target_sketch:
            sw_part.sketch_rectangle(model, 0.0, 0.0, .060, .040)
        target_feature = sw_part.extrude_boss_midplane(model, target_sketch, .010)
        target_body, before = _solid_geometry(model)

        # Offset from the symmetric midplane so the two cut directions retain
        # measurably different 35 mm and 25 mm half-spaces.
        tool_plane = sw_part.offset_plane(model, "Right Plane", .005)
        tool_plane_name = str(get_com_member(tool_plane, "Name"))
        with sw_part.sketch(model, tool_plane_name) as tool_sketch:
            sw_part.sketch_rectangle(model, 0.0, 0.0, .030, .050)
        surface_feature = sw_part.planar_surface_from_sketch(model, tool_sketch)
        surface_bodies = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
        if len(surface_bodies) != 1:
            raise RuntimeError(f"expected one surface tool, found {len(surface_bodies)}")
        surface_box = tuple(
            float(value) * 1000.0
            for value in get_com_member(surface_bodies[0], "GetBodyBox")
        )
        surface_area = sum(
            float(get_com_member(face, "GetArea"))
            for face in tuple(get_com_member(surface_bodies[0], "GetFaces") or ())
        ) * 1e6
        expected_surface_box = (5.0, -25.0, -15.0, 5.0, 25.0, 15.0)
        if any(not math.isclose(value, expected, abs_tol=1e-6)
               for value, expected in zip(surface_box, expected_surface_box)):
            raise RuntimeError(f"surface tool box mismatch: {surface_box}")
        if not math.isclose(surface_area, 1500.0, abs_tol=1e-6):
            raise RuntimeError(f"surface tool area mismatch: {surface_area}")
        tool_faces = tuple(get_com_member(surface_bodies[0], "GetFaces") or ())
        if len(tool_faces) != 1:
            raise RuntimeError(f"expected one surface tool face, found {len(tool_faces)}")
        indent = sw_part.indent_feature(
            model, target_body, tool_faces,
            thickness=.001, clearance=0.0,
            exclude_selected_regions=True, clearance_direction=True,
            cut=True, cut_direction=cut_direction,
        )
        evidence = sw_part.indent_feature_evidence(indent, model)
        _, after = _solid_geometry(model)
        remaining_surfaces = tuple(get_com_member(model, "GetBodies2", 1, False) or ())

        if not evidence["is_cut"] or evidence["cut_direction"] is not cut_direction:
            raise RuntimeError(f"surface Indent FeatureData mismatch: {evidence}")
        if evidence["tool_region_count"] != 1 or evidence["error_code"] != 0:
            raise RuntimeError(f"surface Indent scope mismatch: {evidence}")
        if not 0.0 < after["volume_mm3"] < before["volume_mm3"]:
            raise RuntimeError(f"surface Indent did not remove material: {before} -> {after}")
        if len(remaining_surfaces) != 1:
            raise RuntimeError("surface Indent did not preserve the surface tool body")
        if not bool(get_com_member(model, "ForceRebuild3", False)):
            raise RuntimeError("surface Indent rebuild failed")
        if any(int(get_com_member(feature, "GetErrorCode") or 0) != 0 for feature in (
            target_feature, tool_plane, surface_feature, indent,
        )):
            raise RuntimeError("surface Indent feature tree contains an error")

        completed = True
        return title, {
            "document": title, "saved": False,
            "cut_direction": cut_direction, "feature_data": evidence,
            "before": before, "after": after,
            "center_x_mm": (after["box_mm"][0] + after["box_mm"][3]) / 2.0,
        }
    finally:
        if not completed:
            sw.QuitDoc(title)


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    kept_title = str(get_com_member(original, "GetTitle")) if original else None
    rows = []
    try:
        for direction in (False, True):
            title, row = _run_case(sw, direction)
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
            if kept_title and kept_title != title:
                sw.QuitDoc(kept_title)
            kept_title = title
            sw.ActivateDoc2(title, False, 0)

        left, right = rows
        if math.isclose(
            left["after"]["volume_mm3"], right["after"]["volume_mm3"],
            rel_tol=1e-6, abs_tol=1e-3,
        ) or not math.isclose(
            left["after"]["volume_mm3"] + right["after"]["volume_mm3"],
            left["before"]["volume_mm3"], rel_tol=1e-6, abs_tol=1e-3,
        ):
            raise RuntimeError(f"opposite surface cuts did not partition the target: {rows}")
        if not left["center_x_mm"] * right["center_x_mm"] < 0.0:
            raise RuntimeError(f"cut_direction did not keep opposite half-spaces: {rows}")
        print(json.dumps({"status": "ok", "results": rows}, ensure_ascii=False))
    except Exception:
        if kept_title:
            try:
                sw.ActivateDoc2(kept_title, False, 0)
            except Exception:
                pass
        raise


if __name__ == "__main__":
    main()
