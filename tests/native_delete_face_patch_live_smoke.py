"""Real SolidWorks regression for Delete Face with native patch/heal."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def volume_mm3(body):
    return float(list(get_com_member(body, "GetMassProperties", 1.0))[3]) * 1e9


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    try:
        with sw_part.sketch(model, "Front Plane") as base_sketch:
            sw_part.sketch_rectangle(model, 0.0, 0.0, .040, .040)
        sw_part.extrude_boss_midplane(model, base_sketch, .010)
        base_bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
        if len(base_bodies) != 1 or abs(volume_mm3(base_bodies[0]) - 16000.0) > 1e-4:
            raise RuntimeError("delete-patch base body mismatch")

        sw_part.start_sketch_on_largest_planar_face(model)
        boss_sketch = sw_part.current_sketch_name(model)
        sw_part.sketch_circle(model, 0.0, 0.0, .005)
        sw_part.end_sketch(model)
        boss = sw_part.extrude_boss(model, boss_sketch, .005, direction=False, merge=True)
        if boss is None:
            raise RuntimeError("delete-patch boss failed")
        before_bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
        before_volume = volume_mm3(before_bodies[0])
        expected_before = 16000.0 + 3.141592653589793 * 25.0 * 5.0
        if len(before_bodies) != 1 or abs(before_volume - expected_before) > 1e-3:
            raise RuntimeError(
                f"delete-patch boss volume mismatch: {before_volume} != {expected_before}"
            )
        boss_cylinders = sw_part.find_cylindrical_faces(
            model, radius=.005, axis=(0.0, 0.0, 1.0), tolerance=1e-8,
        )
        if len(boss_cylinders) != 1:
            raise RuntimeError(f"delete-patch cylinder mismatch: {len(boss_cylinders)}")
        boss_caps = sw_part.find_planar_faces(
            model, area=3.141592653589793 * .005 * .005,
            normal=(0.0, 0.0, 1.0), tolerance=1e-8,
        )
        if len(boss_caps) != 1:
            raise RuntimeError(f"delete-patch cap mismatch: {len(boss_caps)}")

        feature = sw_part.delete_faces(
            model, (boss_cylinders[0], boss_caps[0]), heal=True,
        )
        after_bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
        after_surfaces = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
        after_volume = volume_mm3(after_bodies[0]) if len(after_bodies) == 1 else 0.0
        if len(after_bodies) != 1 or after_surfaces or abs(after_volume - 16000.0) > 1e-3:
            raise RuntimeError(
                f"delete-patch result mismatch: solids={len(after_bodies)}, "
                f"surfaces={len(after_surfaces)}, volume={after_volume}"
            )
        patch_feature_name = str(get_com_member(feature, "Name"))

        sw_part.start_sketch_on_largest_planar_face(model)
        tangent_sketch = sw_part.current_sketch_name(model)
        sw_part.sketch_circle(model, 0.0, 0.0, .005)
        sw_part.end_sketch(model)
        sw_part.extrude_boss(model, tangent_sketch, .005, direction=False, merge=True)
        tangent_cylinders = sw_part.find_cylindrical_faces(
            model, radius=.005, axis=(0.0, 0.0, 1.0), tolerance=1e-8,
        )
        tangent_caps = sw_part.find_planar_faces(
            model, area=3.141592653589793 * .005 * .005,
            normal=(0.0, 0.0, 1.0), tolerance=1e-8,
        )
        if len(tangent_cylinders) != 1 or len(tangent_caps) != 1:
            raise RuntimeError(
                f"delete-tangent-fill inputs mismatch: cylinder={len(tangent_cylinders)}, "
                f"cap={len(tangent_caps)}"
            )
        tangent_feature = sw_part.delete_faces(
            model, (tangent_cylinders[0], tangent_caps[0]), mode="fill_tangent",
        )
        tangent_bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
        tangent_surfaces = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
        tangent_volume = volume_mm3(tangent_bodies[0]) if len(tangent_bodies) == 1 else 0.0
        if (len(tangent_bodies) != 1 or tangent_surfaces
                or abs(tangent_volume - 16000.0) > 1e-3):
            raise RuntimeError(
                f"delete-tangent-fill result mismatch: solids={len(tangent_bodies)}, "
                f"surfaces={len(tangent_surfaces)}, volume={tangent_volume}"
            )
        rebuild = int(model.ForceRebuild3(False))
        print(json.dumps({
            "status": "ok",
            "patch_feature": patch_feature_name,
            "tangent_fill_feature": str(get_com_member(tangent_feature, "Name")),
            "before_volume_mm3": before_volume,
            "after_volume_mm3": after_volume,
            "tangent_fill_volume_mm3": tangent_volume,
            "solid_body_count": len(after_bodies),
            "surface_body_count": len(after_surfaces),
            "rebuild": rebuild,
        }, ensure_ascii=False))
    finally:
        try: sw.QuitDoc(title)
        except Exception: pass
        if original_title:
            try: sw.ActivateDoc2(original_title, False, 0)
            except Exception: pass


if __name__ == "__main__":
    main()
