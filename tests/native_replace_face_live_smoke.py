"""Real SolidWorks regression for native Replace Face with a planar surface."""

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
            sw_part.sketch_rectangle(model, 0.0, 0.0, .040, .030)
        sw_part.extrude_boss_midplane(model, base_sketch, .020)
        target_faces = sw_part.find_planar_faces(
            model, area=.040 * .030, center=(0.0, 0.0, .010),
            normal=(0.0, 0.0, 1.0), tolerance=1e-8,
        )
        if len(target_faces) != 1:
            raise RuntimeError(f"Replace Face target mismatch: {len(target_faces)}")

        offset = sw_part.offset_plane(model, "Front Plane", .015)
        offset_name = str(get_com_member(offset, "Name"))
        with sw_part.sketch(model, offset_name) as surface_sketch:
            sw_part.sketch_rectangle(model, 0.0, 0.0, .050, .040)
        sw_part.planar_surface_from_sketch(model, surface_sketch)
        surfaces = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
        if len(surfaces) != 1:
            raise RuntimeError(f"Replace Face surface body mismatch: {len(surfaces)}")

        feature = sw_part.replace_faces(model, target_faces[0], surfaces[0])
        solids = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
        volume = volume_mm3(solids[0]) if len(solids) == 1 else 0.0
        bounds = tuple(float(value) for value in get_com_member(model, "GetPartBox", True)[:6])
        solid_bounds = tuple(float(value) for value in get_com_member(solids[0], "GetBodyBox")[:6])
        if len(solids) != 1 or abs(volume - 30000.0) > 1e-3:
            raise RuntimeError(f"Replace Face volume mismatch: solids={len(solids)}, volume={volume}")
        if abs(bounds[2] + .010) > 1e-8 or abs(bounds[5] - .015) > 1e-8:
            raise RuntimeError(f"Replace Face bounds mismatch: {bounds}")
        expected_solid_bounds = (-.020, -.015, -.010, .020, .015, .015)
        if any(abs(actual - expected) > 1e-8
               for actual, expected in zip(solid_bounds, expected_solid_bounds)):
            raise RuntimeError(f"Replace Face solid bounds mismatch: {solid_bounds}")
        rebuild = int(model.ForceRebuild3(False))
        print(json.dumps({
            "status": "ok",
            "feature": str(get_com_member(feature, "Name")),
            "volume_mm3": volume,
            "bounds_mm": [value * 1000.0 for value in bounds],
            "solid_bounds_mm": [value * 1000.0 for value in solid_bounds],
            "solid_body_count": len(solids),
            "surface_body_count": len(tuple(get_com_member(model, "GetBodies2", 1, False) or ())),
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
