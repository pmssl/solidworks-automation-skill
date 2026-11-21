"""Real SolidWorks regression for explicit revolve feature-scope bodies."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def body_summary(body):
    box = [float(value) * 1000.0 for value in body.GetBodyBox()]
    return {
        "center_y_mm": 0.5 * (box[1] + box[4]),
        "volume_mm3": float(list(body.GetMassProperties(1.0))[3]) * 1e9,
        "box_mm": box,
    }


def annular_body(model, center_y_mm):
    with sw_part.sketch(model, "Front Plane") as sketch_name:
        axis = sw_part.sketch_line(model, 0.0, -0.040, 0.0, 0.040)
        sw_part.set_sketch_construction(axis, True)
        sw_part.sketch_rectangle(
            model, 0.015, center_y_mm / 1000.0, 0.010, 0.008,
        )
    return sw_part.revolve_feature(
        model, sketch_name, math.tau, merge=False,
    )


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    try:
        annular_body(model, -12.0)
        annular_body(model, 12.0)
        before_bodies = tuple(model.GetBodies2(0, False) or ())
        if len(before_bodies) != 2:
            raise RuntimeError(f"expected two seed bodies, got {len(before_bodies)}")
        before = sorted(
            (body_summary(body) for body in before_bodies),
            key=lambda item: item["center_y_mm"],
        )
        lower_body = min(
            before_bodies,
            key=lambda body: body_summary(body)["center_y_mm"],
        )

        with sw_part.sketch(model, "Front Plane") as cut_sketch:
            axis = sw_part.sketch_line(model, 0.0, -0.040, 0.0, 0.040)
            sw_part.set_sketch_construction(axis, True)
            # R17..22 intersects both R10..20 annular bodies and removes only
            # their outer R17..20 band.  Feature scope must protect the upper.
            sw_part.sketch_rectangle(model, 0.0195, 0.0, 0.005, 0.040)

        cut = sw_part.revolve_feature(
            model, cut_sketch, math.tau, cut=True,
            affected_bodies=(lower_body,),
        )
        error = int(get_com_member(cut, "GetErrorCode"))
        rebuilt = bool(model.ForceRebuild3(False))
        if error != 0 or not rebuilt:
            raise RuntimeError(f"scoped revolve cut failed: error={error}")

        after_bodies = tuple(model.GetBodies2(0, False) or ())
        if len(after_bodies) != 2:
            raise RuntimeError(f"scoped cut body count mismatch: {len(after_bodies)}")
        after = sorted(
            (body_summary(body) for body in after_bodies),
            key=lambda item: item["center_y_mm"],
        )
        full_volume = math.pi * (20.0 ** 2 - 10.0 ** 2) * 8.0
        scoped_volume = math.pi * (17.0 ** 2 - 10.0 ** 2) * 8.0
        if abs(before[0]["volume_mm3"] - full_volume) > 0.05:
            raise RuntimeError(f"lower seed volume mismatch: {before[0]}")
        if abs(before[1]["volume_mm3"] - full_volume) > 0.05:
            raise RuntimeError(f"upper seed volume mismatch: {before[1]}")
        if abs(after[0]["volume_mm3"] - scoped_volume) > 0.05:
            raise RuntimeError(f"scoped lower volume mismatch: {after[0]}")
        if abs(after[1]["volume_mm3"] - full_volume) > 0.05:
            raise RuntimeError(f"unscoped upper body changed: {after[1]}")

        definition = get_com_member(cut, "GetDefinition")
        accessed = bool(get_com_member(
            definition, "AccessSelections", model, sw_part._empty_callout(),
        ))
        if not accessed:
            raise RuntimeError("scoped revolve selections were not accessible")
        try:
            feature_scope = bool(get_com_member(definition, "FeatureScope"))
            auto_select = bool(get_com_member(definition, "AutoSelect"))
            scope_count = int(get_com_member(
                definition, "GetFeatureScopeBodiesCount",
            ))
        finally:
            get_com_member(definition, "ReleaseSelectionAccess")
        if not feature_scope or auto_select or scope_count != 1:
            raise RuntimeError(
                "feature-scope readback mismatch: "
                f"scope={feature_scope}, auto={auto_select}, count={scope_count}"
            )

        print(json.dumps({
            "status": "ok",
            "feature": str(get_com_member(cut, "Name")),
            "profile": str(cut_sketch),
            "feature_scope": feature_scope,
            "auto_select": auto_select,
            "feature_scope_body_count": scope_count,
            "solid_body_count": len(after_bodies),
            "before_bodies": before,
            "after_bodies": after,
            "expected_scoped_volume_mm3": scoped_volume,
            "expected_unscoped_volume_mm3": full_volume,
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
