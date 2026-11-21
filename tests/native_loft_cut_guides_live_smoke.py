"""Real SW2025 regression for a native guide-curve lofted cut."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import (
    connect_solidworks, get_com_member, new_document,
)


def volume_mm3(body):
    return float(list(get_com_member(body, "GetMassProperties", 1.0))[3]) * 1e9


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    completed = False
    try:
            with sw_part.sketch(model, "Front Plane") as base_profile:
                sw_part.sketch_rectangle(model, 0.0, 0.0, 0.060, 0.060)
            sw_part.extrude_boss_midplane(model, base_profile, 0.080)
            bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
            if len(bodies) != 1:
                raise RuntimeError(f"base body count mismatch: {len(bodies)}")
            before_volume = volume_mm3(bodies[0])

            plane = sw_part.offset_plane(model, "Front Plane", 0.030)
            plane_name = str(get_com_member(plane, "Name"))
            with sw_part.sketch(model, "Front Plane") as first_section:
                sw_part.sketch_circle(model, 0.0, 0.0, 0.010)
            with sw_part.sketch(model, plane_name) as second_section:
                sw_part.sketch_circle(model, 0.0, 0.0, 0.005)
            with sw_part.sketch_3d(model) as guide:
                sw_part.sketch_line_3d(
                    model, (0.010, 0.0, 0.0), (0.005, 0.0, 0.030),
                )

            feature = sw_part.loft_cut_with_guides(
                model, (first_section, second_section), (guide,),
            )
            error = int(get_com_member(feature, "GetErrorCode"))
            rebuilt = bool(model.ForceRebuild3(False))
            if error != 0 or not rebuilt:
                raise RuntimeError(f"lofted cut rebuild failed: error={error}")
            bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
            if len(bodies) != 1:
                raise RuntimeError(f"lofted cut body count mismatch: {len(bodies)}")
            after_volume = volume_mm3(bodies[0])
            removed = before_volume - after_volume
            expected_removed = math.pi * 30.0 / 3.0 * (
                10.0 ** 2 + 10.0 * 5.0 + 5.0 ** 2
            )
            if abs(removed - expected_removed) > 5.0:
                raise RuntimeError(
                    f"lofted cut volume mismatch: {removed} != {expected_removed}"
                )
            definition = get_com_member(feature, "GetDefinition")
            guide_count = int(get_com_member(definition, "GetGuideCurvesCount"))
            is_boss = bool(get_com_member(definition, "IsBossFeature"))
            if guide_count != 1 or is_boss:
                raise RuntimeError(
                    f"lofted cut semantics mismatch: guides={guide_count}, boss={is_boss}"
                )
            completed = True
            print(json.dumps({
                "status": "ok",
                "feature": str(get_com_member(feature, "Name")),
                "profiles": [first_section, second_section],
                "guide": guide,
                "guide_count": guide_count,
                "is_boss": is_boss,
                "body_count": len(bodies),
                "before_volume_mm3": before_volume,
                "after_volume_mm3": after_volume,
                "removed_volume_mm3": removed,
                "analytic_delta_mm3": removed - expected_removed,
                "rebuild": rebuilt,
                "live_document_title": title,
                "saved": False,
            }, ensure_ascii=False))
    finally:
        if not completed:
            try:
                sw.QuitDoc(title)
            except Exception:
                pass
        target = title if completed else original_title
        if target:
            try:
                sw.ActivateDoc2(target, False, 0)
            except Exception:
                pass


if __name__ == "__main__":
    main()
