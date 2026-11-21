"""Real SolidWorks regression for a boss sweep with one guide curve."""

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
        with sw_part.sketch(model, "Top Plane") as profile_name:
            sw_part.sketch_circle(model, 0.0, 0.0, 0.010)
        with sw_part.sketch(model, "Front Plane") as path_name:
            sw_part.sketch_line(model, 0.0, 0.0, 0.0, 0.040)
        with sw_part.sketch(model, "Front Plane") as guide_name:
            sw_part.sketch_line(model, -0.010, 0.0, -0.005, 0.040)
        feature = sw_part.sweep_boss_with_guides(
            model, profile_name, path_name, (guide_name,)
        )
        error = int(get_com_member(feature, "GetErrorCode"))
        if error != 0 or not bool(model.ForceRebuild3(False)):
            raise RuntimeError(f"guide sweep rebuild failed: error={error}")
        bodies = tuple(model.GetBodies2(0, False) or ())
        if len(bodies) != 1:
            raise RuntimeError(f"guide sweep body count mismatch: {len(bodies)}")
        definition = get_com_member(feature, "GetDefinition")
        guide_count = int(get_com_member(definition, "GetGuideCurvesCount"))
        if guide_count != 1:
            raise RuntimeError(f"guide sweep count mismatch: {guide_count}")
        volume_mm3 = float(list(bodies[0].GetMassProperties(1.0))[3]) * 1e9
        analytic_cylinder = math.pi * 10.0 ** 2 * 40.0
        relative_delta = abs(volume_mm3 - analytic_cylinder) / analytic_cylinder
        if relative_delta > 0.001:
            raise RuntimeError(
                f"guide sweep volume differs excessively: {volume_mm3}, {analytic_cylinder}"
            )
        bounds = [float(value) * 1000.0 for value in model.GetPartBox(True)]
        spans = sorted(abs(bounds[index + 3] - bounds[index]) for index in range(3))
        if max(spans) < 39.9:
            raise RuntimeError(f"guide sweep did not span the 40 mm path: {bounds}")

        with sw_part.sketch(model, "Top Plane") as cut_profile:
            sw_part.sketch_circle(model, 0.0, 0.0, 0.002)
        with sw_part.sketch(model, "Front Plane") as cut_path:
            sw_part.sketch_line(model, 0.0, 0.0, 0.0, 0.040)
        with sw_part.sketch(model, "Front Plane") as cut_guide:
            sw_part.sketch_line(model, -0.002, 0.0, -0.001, 0.040)
        cut_feature = sw_part.sweep_cut_with_guides(
            model, cut_profile, cut_path, (cut_guide,)
        )
        cut_error = int(get_com_member(cut_feature, "GetErrorCode"))
        if cut_error != 0 or not bool(model.ForceRebuild3(False)):
            raise RuntimeError(f"guide cut sweep rebuild failed: error={cut_error}")
        cut_bodies = tuple(model.GetBodies2(0, False) or ())
        if len(cut_bodies) != 1:
            raise RuntimeError(f"guide cut sweep body count mismatch: {len(cut_bodies)}")
        cut_definition = get_com_member(cut_feature, "GetDefinition")
        cut_guide_count = int(get_com_member(cut_definition, "GetGuideCurvesCount"))
        if cut_guide_count != 1:
            raise RuntimeError(f"guide cut sweep count mismatch: {cut_guide_count}")
        after_volume_mm3 = float(
            list(cut_bodies[0].GetMassProperties(1.0))[3]
        ) * 1e9
        removed_volume_mm3 = volume_mm3 - after_volume_mm3
        analytic_cut = math.pi * 2.0 ** 2 * 40.0
        cut_relative_delta = abs(removed_volume_mm3 - analytic_cut) / analytic_cut
        if cut_relative_delta > 0.001:
            raise RuntimeError(
                "guide cut sweep removed volume differs excessively: "
                f"{removed_volume_mm3}, {analytic_cut}"
            )
        print(json.dumps({
            "status": "ok",
            "feature": str(get_com_member(feature, "Name")),
            "profile": profile_name,
            "path": path_name,
            "guide": guide_name,
            "guide_count": guide_count,
            "volume_mm3": volume_mm3,
            "analytic_cylinder_relative_delta": relative_delta,
            "spans_mm": spans,
            "cut_feature": str(get_com_member(cut_feature, "Name")),
            "cut_profile": cut_profile,
            "cut_path": cut_path,
            "cut_guide": cut_guide,
            "cut_guide_count": cut_guide_count,
            "after_cut_volume_mm3": after_volume_mm3,
            "removed_volume_mm3": removed_volume_mm3,
            "analytic_cut_relative_delta": cut_relative_delta,
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
