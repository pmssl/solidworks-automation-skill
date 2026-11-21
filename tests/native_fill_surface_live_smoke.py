"""Real SolidWorks regression for a native Fill Surface."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import (
    connect_solidworks,
    create_empty_dispatch_variant,
    get_com_member,
    new_document,
)


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    completed = False
    try:
        with sw_part.sketch(model, "Front Plane") as sketch_name:
            sw_part.sketch_circle(model, 0.0, 0.0, .020)
        boundary = get_com_member(model, "FeatureByName", str(sketch_name))
        if boundary is None:
            raise RuntimeError(f"fill boundary sketch not found: {sketch_name}")
        constraint = None
        constraint_name = None
        if "--constraint" in sys.argv:
            with sw_part.sketch_3d(model) as constraint_name:
                sw_part.sketch_spline_3d(model, (
                    (-.020, 0.0, 0.0),
                    (0.0, 0.0, .008),
                    (.020, 0.0, 0.0),
                ))
            constraint = get_com_member(model, "FeatureByName", str(constraint_name))
            if constraint is None:
                raise RuntimeError(f"fill constraint sketch not found: {constraint_name}")
        feature = sw_part.fill_surface(
            model, boundary, resolution=3,
            constraint_curves=(constraint,) if constraint is not None else (),
        )
        surface_bodies = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
        if len(surface_bodies) != 1:
            raise RuntimeError(f"fill surface body count mismatch: {len(surface_bodies)}")
        faces = tuple(get_com_member(surface_bodies[0], "GetFaces") or ())
        area_mm2 = sum(float(get_com_member(face, "GetArea")) for face in faces) * 1e6
        expected = math.pi * 20.0 ** 2
        body_box_mm = [
            float(value) * 1000.0
            for value in get_com_member(surface_bodies[0], "GetBodyBox")
        ]
        if constraint is None and abs(area_mm2 - expected) > 1e-4:
            raise RuntimeError(f"fill surface area mismatch: {area_mm2} vs {expected}")
        if constraint is not None and (
            area_mm2 <= expected + 1.0 or body_box_mm[5] < 7.5
        ):
            raise RuntimeError(
                f"constraint curve did not shape fill: area={area_mm2}, box={body_box_mm}"
            )
        data = get_com_member(feature, "GetDefinition")
        resolution = int(get_com_member(data, "ResolutionControl"))
        accessed = bool(get_com_member(
            data, "AccessSelections", model, create_empty_dispatch_variant(),
        ))
        if not accessed:
            raise RuntimeError("could not access Fill Surface selections")
        try:
            constraint_count = int(get_com_member(data, "GetConstraintCurvesCount"))
            boundary_count = int(get_com_member(data, "GetPatchBoundaryCount"))
        finally:
            get_com_member(data, "ReleaseSelectionAccess")
        error_code = int(get_com_member(feature, "GetErrorCode"))
        rebuilt = bool(model.ForceRebuild3(False))
        if (
            resolution != 3 or boundary_count != 1
            or constraint_count != (1 if constraint is not None else 0)
            or error_code != 0 or not rebuilt
        ):
            raise RuntimeError(f"fill surface resolution mismatch: {resolution}")
        print(json.dumps({
            "status": "ok",
            "feature": str(get_com_member(feature, "Name")),
            "boundary": str(sketch_name),
            "constraint": str(constraint_name) if constraint_name else None,
            "resolution": resolution,
            "boundary_count": boundary_count,
            "constraint_count": constraint_count,
            "surface_body_count": len(surface_bodies),
            "area_mm2": area_mm2,
            "body_box_mm": body_box_mm,
            "error_code": error_code,
            "rebuild": rebuilt,
            "live_document_title": title,
            "saved": False,
        }, ensure_ascii=False))
        completed = True
    finally:
        if not completed:
            try: sw.QuitDoc(title)
            except Exception: pass
        if not completed and original_title:
            try: sw.ActivateDoc2(original_title, False, 0)
            except Exception: pass


if __name__ == "__main__":
    main()
