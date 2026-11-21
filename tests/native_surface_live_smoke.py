"""Real SolidWorks regression for planar surface and Thicken."""

from __future__ import annotations

import json
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
        with sw_part.sketch(model, "Front Plane") as sketch_name:
            sw_part.sketch_rectangle(model, 0, 0, .040, .030)
        surface_feature = sw_part.planar_surface_from_sketch(model, sketch_name)
        surface_bodies = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
        if len(surface_bodies) != 1:
            raise RuntimeError(f"planar surface body count mismatch: {len(surface_bodies)}")
        faces = tuple(get_com_member(surface_bodies[0], "GetFaces") or ())
        area_mm2 = sum(float(get_com_member(face, "GetArea")) for face in faces) * 1e6
        if abs(area_mm2 - 1200.0) > 1e-5:
            raise RuntimeError(f"planar surface area mismatch: {area_mm2}")

        thicken = sw_part.thicken_surface(model, surface_bodies[0], .005, side=0)
        solids = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
        if len(solids) != 1:
            raise RuntimeError(f"thicken solid count mismatch: {len(solids)}")
        volume = float(list(get_com_member(solids[0], "GetMassProperties", 1.0))[3]) * 1e9
        if abs(volume - 6000.0) > 1e-4:
            raise RuntimeError(f"thicken volume mismatch: {volume}")
        data = get_com_member(thicken, "GetDefinition")
        thickness_mm = float(get_com_member(data, "Thickness")) * 1000.0
        side = int(get_com_member(data, "ThicknessSide"))
        if abs(thickness_mm - 5.0) > 1e-6 or side != 0:
            raise RuntimeError(f"thicken parameter mismatch: {thickness_mm}, {side}")
        print(json.dumps({
            "status": "ok",
            "surface_feature": str(get_com_member(surface_feature, "Name")),
            "surface_area_mm2": area_mm2,
            "thicken_feature": str(get_com_member(thicken, "Name")),
            "thickness_mm": thickness_mm,
            "thickness_side": side,
            "solid_volume_mm3": volume,
        }, ensure_ascii=False))
    finally:
        try: sw.QuitDoc(title)
        except Exception: pass
        if original_title:
            try: sw.ActivateDoc2(original_title, False, 0)
            except Exception: pass


if __name__ == "__main__":
    main()
