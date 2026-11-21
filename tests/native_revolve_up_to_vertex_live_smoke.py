"""Real SolidWorks regression for a revolve terminated by a solid vertex."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    try:
        target_angle = math.radians(60.0)
        target_x = 0.030 * math.cos(target_angle)
        # Top Plane sketch Y maps to negative model Z in this template.
        target_z = 0.030 * math.sin(target_angle)
        with sw_part.sketch(model, "Top Plane") as target_sketch:
            sw_part.sketch_corner_rectangle(
                model, target_x, target_z, target_x + 0.001, target_z + 0.001,
            )
        target_body_feature = sw_part.extrude_boss_midplane(
            model, target_sketch, 0.001, merge=False,
        )
        if target_body_feature is None or not bool(model.ForceRebuild3(False)):
            raise RuntimeError("up-to-vertex target body failed")

        candidates = []
        for vertex in sw_part.solid_vertices(model):
            point = sw_part.vertex_geometry(vertex)["point"]
            radius = math.hypot(point[0], point[2])
            angle = math.atan2(-point[2], point[0])
            if angle < 0.0:
                angle += math.tau
            if radius > 0.025:
                candidates.append((abs(angle - target_angle), abs(point[1]), point, vertex))
        candidates.sort(key=lambda row: (row[0], row[1], row[2]))
        if not candidates or candidates[0][0] > math.radians(0.1):
            raise RuntimeError(f"up-to-vertex target resolution failed: {candidates}")
        _delta, _abs_y, target_point, target_vertex = candidates[0]
        actual_angle = math.atan2(-target_point[2], target_point[0])
        if actual_angle < 0.0:
            actual_angle += math.tau

        with sw_part.sketch(model, "Front Plane") as profile_name:
            axis = sw_part.sketch_line(model, 0.0, -0.030, 0.0, 0.030)
            sw_part.set_sketch_construction(axis, True)
            sw_part.sketch_rectangle(model, 0.015, 0.0, 0.010, 0.010)

        feature = sw_part.revolve_feature_to_reference(
            model, profile_name, target_vertex, "up_to_vertex", merge=False,
        )
        error = int(get_com_member(feature, "GetErrorCode"))
        rebuilt = bool(model.ForceRebuild3(False))
        if error != 0 or not rebuilt:
            raise RuntimeError(f"up-to-vertex revolve failed: error={error}")
        bodies = tuple(model.GetBodies2(0, False) or ())
        if len(bodies) != 2:
            raise RuntimeError(f"up-to-vertex body count mismatch: {len(bodies)}")
        volumes = sorted(float(list(body.GetMassProperties(1.0))[3]) * 1e9 for body in bodies)
        full_volume = math.pi * (20.0 ** 2 - 10.0 ** 2) * 10.0
        expected_revolve = full_volume * actual_angle / math.tau
        if abs(volumes[0] - 1.0) > 0.01 or abs(volumes[1] - expected_revolve) > 0.05:
            raise RuntimeError(
                f"up-to-vertex volumes mismatch: {volumes}, expected={expected_revolve}"
            )

        definition = get_com_member(feature, "GetDefinition")
        accessed = bool(get_com_member(
            definition, "AccessSelections", model, sw_part._empty_callout(),
        ))
        if not accessed:
            raise RuntimeError("up-to-vertex selections were not accessible")
        try:
            axis_type = int(get_com_member(definition, "GetAxisType"))
        finally:
            get_com_member(definition, "ReleaseSelectionAccess")

        print(json.dumps({
            "status": "ok",
            "feature": str(get_com_member(feature, "Name")),
            "profile": str(profile_name),
            "target_vertex_mm": [value * 1000.0 for value in target_point],
            "target_angle_deg": math.degrees(actual_angle),
            "axis_type": axis_type,
            "solid_body_count": len(bodies),
            "body_volumes_mm3": volumes,
            "analytic_revolve_delta_mm3": volumes[1] - expected_revolve,
            "rebuild": rebuilt,
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
