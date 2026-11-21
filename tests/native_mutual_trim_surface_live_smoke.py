"""Real SolidWorks regression for mutual Surface Trim."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def _area_mm2(body) -> float:
    return sum(
        float(get_com_member(face, "GetArea"))
        for face in tuple(get_com_member(body, "GetFaces") or ())
    ) * 1e6


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    completed = False
    try:
        with sw_part.sketch(model, "Front Plane") as first_sketch:
            sw_part.sketch_line(model, -.030, 0.0, .030, 0.0)
        first = sw_part.extrude_surface(model, first_sketch, .040)
        with sw_part.sketch(model, "Front Plane") as second_sketch:
            sw_part.sketch_line(model, 0.0, -.020, 0.0, .020)
        second = sw_part.extrude_surface(model, second_sketch, .040)

        created_bodies = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
        if len(created_bodies) != 2:
            raise RuntimeError(f"surface creation body mismatch: {len(created_bodies)}")
        second_body = min(created_bodies, key=_area_mm2)
        sw_part.move_copy_bodies(
            model, second_body, translation=(0.0, 0.0, .005), copy=False,
        )

        before = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
        before_areas = sorted(_area_mm2(body) for body in before)
        before_boxes = [
            tuple(float(value) for value in get_com_member(body, "GetBodyBox"))
            for body in before
        ]
        if len(before) != 2 or any(
            abs(actual - expected) > 1e-4
            for actual, expected in zip(before_areas, (1600.0, 2400.0))
        ):
            raise RuntimeError(
                f"mutual-trim input mismatch: bodies={len(before)}, areas={before_areas}"
            )
        z_mid = sum((box[2] + box[5]) * .5 for box in before_boxes) / len(before_boxes)

        feature = sw_part.trim_surface_standard(
            model,
            before,
            ((-.015, 0.0, z_mid), (.015, 0.0, z_mid), (0.0, -.010, z_mid)),
            target_surfaces=before,
            mutual_trim=True,
            remove_picked=False,
            split_system=True,
            extend_linearly=False,
            sew=False,
        )
        after = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
        after_areas = sorted(_area_mm2(body) for body in after)
        expected_total_area = 3200.0
        error_code = int(get_com_member(feature, "GetErrorCode"))
        rebuilt = bool(get_com_member(model, "EditRebuild3"))
        if (
            len(after) != 3
            or abs(sum(after_areas) - expected_total_area) > 1e-4
            or error_code != 0
            or not rebuilt
        ):
            raise RuntimeError(
                f"mutual-trim result mismatch: bodies={len(after)}, "
                f"areas={after_areas}, error={error_code}, rebuild={rebuilt}"
            )

        print(json.dumps({
            "status": "ok",
            "input_features": [
                str(get_com_member(first, "Name")),
                str(get_com_member(second, "Name")),
            ],
            "feature": str(get_com_member(feature, "Name")),
            "input_surface_body_count": len(before),
            "input_areas_mm2": before_areas,
            "input_boxes_m": before_boxes,
            "result_surface_body_count": len(after),
            "result_areas_mm2": after_areas,
            "result_total_area_mm2": sum(after_areas),
            "error_code": error_code,
            "rebuild": rebuilt,
            "live_document_title": title,
            "saved": False,
        }, ensure_ascii=False))
        completed = True
    finally:
        if not completed:
            try:
                sw.QuitDoc(title)
            except Exception:
                pass
        if not completed and original_title:
            try:
                sw.ActivateDoc2(original_title, False, 0)
            except Exception:
                pass


if __name__ == "__main__":
    main()
