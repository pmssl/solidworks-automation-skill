"""Real SolidWorks regression for Delete Face with native Fill mode."""

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
        with sw_part.sketch(model, "Front Plane") as sketch_name:
            sw_part.sketch_rectangle(model, 0.0, 0.0, .040, .030)
        sw_part.extrude_boss_midplane(model, sketch_name, .020)
        top_faces = sw_part.find_planar_faces(
            model, area=.040 * .030, center=(0.0, 0.0, .010),
            normal=(0.0, 0.0, 1.0), tolerance=1e-8,
        )
        if len(top_faces) != 1:
            raise RuntimeError(f"delete-fill face mismatch: {len(top_faces)}")
        feature = sw_part.delete_faces(model, top_faces[0], mode="fill")
        bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
        surfaces = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
        volume = volume_mm3(bodies[0]) if len(bodies) == 1 else 0.0
        if len(bodies) != 1 or surfaces or abs(volume - 24000.0) > 1e-3:
            raise RuntimeError(
                f"delete-fill geometry mismatch: solids={len(bodies)}, "
                f"surfaces={len(surfaces)}, volume={volume}"
            )
        definition = get_com_member(feature, "GetDefinition")
        accessed = bool(get_com_member(
            definition, "AccessSelections", model, sw_part._empty_callout(),
        ))
        if not accessed:
            raise RuntimeError("delete-fill feature data selection access failed")
        try:
            options = int(get_com_member(definition, "Options"))
        finally:
            get_com_member(definition, "ReleaseSelectionAccess")
        if options not in (0, 2):
            raise RuntimeError(f"delete-fill option readback was unexpected: {options}")
        rebuild = int(model.ForceRebuild3(False))
        print(json.dumps({
            "status": "ok",
            "feature": str(get_com_member(feature, "Name")),
            "requested_option": 2,
            "feature_data_options": options,
            "volume_mm3": volume,
            "solid_body_count": len(bodies),
            "surface_body_count": len(surfaces),
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
