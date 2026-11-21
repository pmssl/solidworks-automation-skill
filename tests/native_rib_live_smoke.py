"""Real SolidWorks regression for an open-sketch native rib."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def volume_mm3(model):
    body = (model.GetBodies2(0, False) or ())[0]
    return float(list(body.GetMassProperties(1.0))[3]) * 1e9


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    title = None
    try:
        model = new_document(sw, "part")
        title = str(get_com_member(model, "GetTitle"))
        with sw_part.sketch(model, "Front Plane") as profile:
            points = [(0, 0), (.040, 0), (.040, .005), (.005, .005), (.005, .030), (0, .030)]
            for start, end in zip(points, points[1:] + points[:1]):
                sw_part.sketch_line(model, start[0], start[1], end[0], end[1])
        base = sw_part.extrude_boss_midplane(model, profile, .020)
        if base is None or int(get_com_member(base, "GetErrorCode")) != 0:
            raise RuntimeError("L-profile base failed")
        before = volume_mm3(model)
        if abs(before - 6500.0) > 0.5:
            raise RuntimeError(f"L-profile base volume mismatch: {before}")
        with sw_part.sketch(model, "Front Plane") as rib_sketch:
            # Extend both endpoints into the wall/base so the rib solver can trim
            # the open contour robustly instead of relying on coincident contact.
            segment = sw_part.sketch_line(model, .003, .022, .022, .003)
            if segment is None:
                raise RuntimeError("rib sketch line was not created")
        feature = None
        chosen = None
        for two_sided in (True, False):
            for normal_to_sketch in (False, True):
                for reverse_material in (False, True):
                    try:
                        feature = sw_part.rib_feature(
                            model, rib_sketch, .003, two_sided=two_sided,
                            reverse_material=reverse_material,
                            normal_to_sketch=normal_to_sketch,
                        )
                    except RuntimeError:
                        continue
                    if feature is not None:
                        chosen = {
                            "two_sided": two_sided,
                            "normal_to_sketch": normal_to_sketch,
                            "reverse_material": reverse_material,
                        }
                        break
                if feature is not None:
                    break
            if feature is not None:
                break
        if feature is None:
            raise RuntimeError("rib failed in both material directions")
        error = int(get_com_member(feature, "GetErrorCode"))
        if error != 0 or not bool(model.ForceRebuild3(False)):
            raise RuntimeError(f"rib feature/rebuild failed: {error}")
        if len(model.GetBodies2(0, False) or ()) != 1:
            raise RuntimeError("rib did not retain one merged solid body")
        definition = get_com_member(feature, "GetDefinition")
        thickness_mm = float(get_com_member(definition, "Thickness")) * 1000.0
        two_sided = bool(get_com_member(definition, "IsTwoSided"))
        after = volume_mm3(model)
        if abs(thickness_mm - 3.0) > 1e-5 or after <= before:
            raise RuntimeError(
                f"rib readback mismatch: thickness={thickness_mm}, two_sided={two_sided}, volume={after}"
            )
        print(json.dumps({"status": "ok", "feature": str(feature.Name),
                          "thickness_mm": thickness_mm, "two_sided": two_sided,
                          "chosen_options": chosen,
                          "volume_before_mm3": before, "volume_after_mm3": after},
                         ensure_ascii=False))
    finally:
        if title:
            try: sw.QuitDoc(title)
            except Exception: pass
        if original_title:
            try: sw.ActivateDoc2(original_title, False, 0)
            except Exception: pass


if __name__ == "__main__":
    main()
