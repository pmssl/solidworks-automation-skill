"""Real regressions for bidirectional and constant-twist native sweeps."""

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


_latest_title = None


def new_live_part(sw):
    """Create an unnamed in-memory Part and retain only the latest case."""
    global _latest_title
    if _latest_title:
        try:
            sw.QuitDoc(_latest_title)
        except Exception:
            pass
        _latest_title = None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    _latest_title = title
    return model, title


def discard(sw, title):
    global _latest_title
    try:
        sw.QuitDoc(title)
    except Exception:
        pass
    if _latest_title == title:
        _latest_title = None


def body_result(model, feature, expected_volume):
    error = int(get_com_member(feature, "GetErrorCode"))
    rebuilt = bool(model.ForceRebuild3(False))
    if error != 0 or not rebuilt:
        raise RuntimeError(f"advanced sweep failed: error={error}")
    bodies = tuple(model.GetBodies2(0, False) or ())
    if len(bodies) != 1:
        raise RuntimeError(f"advanced sweep body count mismatch: {len(bodies)}")
    body = bodies[0]
    volume = float(list(body.GetMassProperties(1.0))[3]) * 1e9
    if abs(volume - expected_volume) > 0.1:
        raise RuntimeError(f"advanced sweep volume mismatch: {volume} != {expected_volume}")
    box = [float(value) * 1000.0 for value in body.GetBodyBox()]
    return {
        "solid_body_count": len(bodies),
        "volume_mm3": volume,
        "analytic_volume_delta_mm3": volume - expected_volume,
        "body_box_mm": box,
        "spans_mm": sorted(abs(box[index + 3] - box[index]) for index in range(3)),
        "rebuild": rebuilt,
    }


def bidirectional_case(sw):
    model, title = new_live_part(sw)
    completed = False
    try:
        with sw_part.sketch(model, "Top Plane") as profile:
            sw_part.sketch_circle(model, 0.0, 0.0, 0.003)
        with sw_part.sketch(model, "Front Plane") as path:
            sw_part.sketch_line(model, 0.0, -0.020, 0.0, 0.020)
        feature = sw_part.sweep_feature_advanced(
            model, profile, path, direction=1,
        )
        result = body_result(model, feature, math.pi * 3.0 ** 2 * 40.0)
        definition = get_com_member(feature, "GetDefinition")
        result.update({
            "feature": str(get_com_member(feature, "Name")),
            "profile": profile,
            "path": path,
            "direction": int(get_com_member(definition, "Direction")),
            "twist_control": int(get_com_member(definition, "TwistControlType")),
            "live_document_title": title,
            "saved": False,
        })
        if result["direction"] != 1:
            raise RuntimeError(f"bidirectional sweep readback: {result}")
        expected_spans = [6.0, 6.0, 40.0]
        if max(abs(a - e) for a, e in zip(result["spans_mm"], expected_spans)) > 0.1:
            raise RuntimeError(f"bidirectional sweep spans mismatch: {result}")
        completed = True
        return result
    finally:
        if not completed:
            discard(sw, title)


def circle_single_case(sw):
    """Prove the long sweep signature for a one-direction circular baseline."""
    model, title = new_live_part(sw)
    completed = False
    try:
        with sw_part.sketch(model, "Top Plane") as profile:
            sw_part.sketch_circle(model, 0.0, 0.0, 0.003)
        with sw_part.sketch(model, "Front Plane") as path:
            sw_part.sketch_line(model, 0.0, 0.0, 0.0, 0.040)
        feature = sw_part.sweep_feature_advanced(model, profile, path)
        result = body_result(model, feature, math.pi * 3.0 ** 2 * 40.0)
        definition = get_com_member(feature, "GetDefinition")
        result.update({
            "feature": str(get_com_member(feature, "Name")),
            "profile": profile,
            "path": path,
            "direction": int(get_com_member(definition, "Direction")),
            "twist_control": int(get_com_member(definition, "TwistControlType")),
            "live_document_title": title,
            "saved": False,
        })
        completed = True
        return result
    finally:
        if not completed:
            discard(sw, title)


def twist_case(sw, *, twist_control=8, twist_angle=math.pi / 2.0):
    model, title = new_live_part(sw)
    completed = False
    try:
        with sw_part.sketch(model, "Top Plane") as profile:
            # The path start is an actual profile vertex, not merely an
            # unreferenced point inside the rectangular region.
            sw_part.sketch_corner_rectangle(model, 0.0, 0.0, 0.008, 0.004)
        profile_feature = sw_part._last_model_feature(model)
        with sw_part.sketch(model, "Front Plane") as path:
            sw_part.sketch_line(model, 0.0, 0.0, 0.0, 0.040)
        path_feature = sw_part._last_model_feature(model)
        feature = sw_part.sweep_feature_advanced(
            model, profile_feature, path_feature,
            twist_control=twist_control, twist_angle=twist_angle,
        )
        result = body_result(model, feature, 8.0 * 4.0 * 40.0)
        definition = get_com_member(feature, "GetDefinition")
        result.update({
            "feature": str(get_com_member(feature, "Name")),
            "profile": profile,
            "path": path,
            "direction": int(get_com_member(definition, "Direction")),
            "twist_control": int(get_com_member(definition, "TwistControlType")),
            "twist_angle_deg": math.degrees(float(get_com_member(
                definition, "GetTwistAngle",
            ))),
            "live_document_title": title,
            "saved": False,
        })
        if result["twist_control"] != twist_control:
            raise RuntimeError(f"constant-twist type readback: {result}")
        if abs(result["twist_angle_deg"] - math.degrees(twist_angle)) > 1e-7:
            raise RuntimeError(f"constant-twist angle readback: {result}")
        completed = True
        return result
    finally:
        if not completed:
            discard(sw, title)


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    try:
        if "--bidirectional-only" in sys.argv:
            results = {"bidirectional": bidirectional_case(sw)}
        elif "--circle-single-only" in sys.argv:
            results = {"circle_single": circle_single_case(sw)}
        elif "--twist-baseline-only" in sys.argv:
            results = {"twist_baseline": twist_case(
                sw, twist_control=0, twist_angle=0.0,
            )}
        elif "--twist-only" in sys.argv:
            results = {"constant_twist": twist_case(sw)}
        elif "--normal-constant-twist-only" in sys.argv:
            results = {"normal_constant_twist": twist_case(
                sw, twist_control=9, twist_angle=math.pi / 2.0,
            )}
        else:
            results = {
                "bidirectional": bidirectional_case(sw),
                "constant_twist": twist_case(sw),
            }
        print(json.dumps({"status": "ok", **results}, ensure_ascii=False))
    finally:
        target = _latest_title or original_title
        if target:
            try:
                sw.ActivateDoc2(target, False, 0)
            except Exception:
                pass


if __name__ == "__main__":
    main()
