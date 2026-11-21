"""Real SolidWorks regression for a revolve directly about a solid edge."""

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
        with sw_part.sketch(model, "Front Plane") as base_sketch:
            sw_part.sketch_rectangle(model, 0.0, 0.0, 0.008, 0.060)
        base = sw_part.extrude_boss_midplane(model, base_sketch, 0.004)
        if base is None or not bool(model.ForceRebuild3(False)):
            raise RuntimeError("edge-axis base body failed")

        faces = sw_part.find_planar_faces(
            model, area=0.008 * 0.060, center=(0.0, 0.0, 0.002),
            normal=(0.0, 0.0, 1.0), tolerance=1e-7,
        )
        if len(faces) != 1:
            face_rows = [sw_part.planar_face_geometry(face) for face in sw_part.solid_faces(model)]
            body_box = [float(value) * 1000.0 for value in model.GetBodies2(0, False)[0].GetBodyBox()]
            raise RuntimeError(
                f"edge-axis sketch face mismatch: {len(faces)}; "
                f"body_box_mm={body_box}; faces={face_rows}"
            )
        axis_edges = sw_part.find_solid_edges(
            model, length=0.060, direction=(0.0, 1.0, 0.0),
            midpoint=(-0.004, 0.0, 0.002), tolerance=1e-7,
        )
        if len(axis_edges) != 1:
            raise RuntimeError(f"edge-axis semantic edge mismatch: {len(axis_edges)}")
        axis_edge = axis_edges[0]
        axis_geometry = sw_part.edge_geometry(axis_edge)

        model.ClearSelection2(True)
        if not sw_part._select_com_object(faces[0], append=False, mark=0):
            raise RuntimeError("failed to select edge-axis sketch face")
        model.SketchManager.InsertSketch(True)
        sw_part.sketch_rectangle(model, 0.011, 0.0, 0.010, 0.010)
        profile = sw_part.end_sketch(model)
        if profile is None:
            raise RuntimeError("edge-axis profile sketch did not finish")

        feature = sw_part.revolve_feature_about_edge(
            model, profile.name, axis_edge, math.tau, merge=False,
        )
        error = int(get_com_member(feature, "GetErrorCode"))
        rebuilt = bool(model.ForceRebuild3(False))
        if error != 0 or not rebuilt:
            raise RuntimeError(f"edge-axis revolve failed: error={error}")

        bodies = tuple(model.GetBodies2(0, False) or ())
        if len(bodies) != 2:
            raise RuntimeError(f"edge-axis body count mismatch: {len(bodies)}")
        body_rows = []
        for body in bodies:
            volume = float(list(body.GetMassProperties(1.0))[3]) * 1e9
            box = [float(value) * 1000.0 for value in body.GetBodyBox()]
            spans = sorted(abs(box[index + 3] - box[index]) for index in range(3))
            body_rows.append({"volume_mm3": volume, "spans_mm": spans})
        body_rows.sort(key=lambda row: row["volume_mm3"])
        expected = (1920.0, math.pi * (20.0 ** 2 - 10.0 ** 2) * 10.0)
        if any(abs(row["volume_mm3"] - wanted) > 0.05
               for row, wanted in zip(body_rows, expected)):
            raise RuntimeError(f"edge-axis body volumes mismatch: {body_rows}")
        expected_spans = ((4.0, 8.0, 60.0), (10.0, 40.0, 40.0))
        for row, wanted in zip(body_rows, expected_spans):
            if any(abs(actual - target) > 0.1
                   for actual, target in zip(row["spans_mm"], wanted)):
                raise RuntimeError(f"edge-axis body bounds mismatch: {body_rows}")

        definition = get_com_member(feature, "GetDefinition")
        accessed = bool(get_com_member(
            definition, "AccessSelections", model, sw_part._empty_callout(),
        ))
        if not accessed:
            raise RuntimeError("edge-axis definition selections were not accessible")
        try:
            axis_type = int(get_com_member(definition, "GetAxisType"))
            axis_object = get_com_member(definition, "Axis")
        finally:
            get_com_member(definition, "ReleaseSelectionAccess")
        if axis_type != 1 or axis_object is None:
            raise RuntimeError(f"expected swSelEDGES (1), got {axis_type}")

        print(json.dumps({
            "status": "ok",
            "feature": str(get_com_member(feature, "Name")),
            "profile": profile.name,
            "axis_type": axis_type,
            "axis_geometry": axis_geometry,
            "solid_body_count": len(bodies),
            "bodies": body_rows,
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
