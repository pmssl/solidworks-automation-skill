"""Real SolidWorks regressions for twist, taper, and stretch Flex modes."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


CASES = (
    {"mode": "twisting", "amount": .200, "type": "Bending",
     "volume_range": (0.995, 1.005),
     "axes": ((0, 0, 1), (1, 0, 0), (0, 1, 0))},
    {"mode": "tapering", "amount": .200, "type": "Bending",
     "volume_range": (0.1, 10.0),
     "axes": ((1, 0, 0), (0, 0, 1), (0, -1, 0))},
    {"mode": "stretching", "amount": .200, "type": "Bending",
     "volume_range": (0.1, 10.0),
     "axes": ((1, 0, 0), (0, 0, 1), (0, -1, 0))},
)


def _geometry(model):
    bodies = tuple(get_com_member(model, "GetBodies2", 0, False) or ())
    if len(bodies) != 1:
        raise RuntimeError(f"expected one solid body, found {len(bodies)}")
    body = bodies[0]
    return body, {
        "body_count": 1,
        "bounding_box_mm": tuple(
            float(value) * 1000.0 for value in get_com_member(body, "GetBodyBox")
        ),
        "volume_mm3": float(get_com_member(body, "GetMassProperties", 1.0)[3]) * 1e9,
    }


def _spans(row):
    box = row["bounding_box_mm"]
    return tuple(box[index + 3] - box[index] for index in range(3))


def _assert_mode_geometry(mode, before, after, volume_ratio):
    before_spans = _spans(before)
    after_spans = _spans(after)

    def unchanged(left, right):
        return math.isclose(left, right, rel_tol=1e-5, abs_tol=1e-5)

    if mode == "twisting":
        if not unchanged(after_spans[0], before_spans[0]):
            raise RuntimeError("twisting unexpectedly changed the rotation-axis span")
        if not after_spans[1] > before_spans[1] or not after_spans[2] > before_spans[2]:
            raise RuntimeError("twisting did not rotate the rectangular section around Z")
    elif mode == "tapering":
        if not after_spans[0] > before_spans[0] or not after_spans[1] > before_spans[1]:
            raise RuntimeError("tapering did not change both transverse spans")
        if not unchanged(after_spans[2], before_spans[2]):
            raise RuntimeError("tapering unexpectedly changed the tangent-axis length")
    elif mode == "stretching":
        if not unchanged(after_spans[0], before_spans[0]) or not unchanged(
            after_spans[1], before_spans[1],
        ):
            raise RuntimeError("stretching changed a transverse span")
        length_ratio = after_spans[2] / before_spans[2]
        if length_ratio <= 1.0 or not math.isclose(
            volume_ratio, length_ratio, rel_tol=1e-4,
        ):
            raise RuntimeError("stretching did not increase Z length and volume consistently")


def _assert_amount_readback(case, evidence, before, after):
    d0 = next((row for row in evidence["dimensions"] if row["name"] == "D0"), None)
    if d0 is None:
        raise RuntimeError(f"{case['mode']} has no native D0 amount dimension")
    if case["mode"] == "stretching":
        extension_m = (_spans(after)[2] - _spans(before)[2]) / 1000.0
        if not math.isclose(d0["system_value"], extension_m, rel_tol=1e-8):
            raise RuntimeError("stretch D0 does not match the resulting axial extension")
    elif not math.isclose(d0["system_value"], case["amount"], rel_tol=1e-9):
        raise RuntimeError(f"{case['mode']} D0 does not preserve the requested angle")


def _run_case(sw, case):
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    completed = False
    try:
        with sw_part.sketch(model, "Front Plane") as sketch_name:
            sw_part.sketch_rectangle(model, 0.0, 0.0, .012, .006)
        base = sw_part.extrude_boss_midplane(model, sketch_name, .100)
        body, before = _geometry(model)
        rotation_axis, tangent_axis, radius_axis = case["axes"]
        flex = sw_part.flex_feature(
            model, body, case["mode"], case["amount"],
            rotation_axis=rotation_axis,
            tangent_axis=tangent_axis,
            radius_axis=radius_axis,
            pivot=(0.0, 0.0, 0.0),
            left_trim=.040, right_trim=.040,
            hard_edges=False,
        )
        evidence = sw_part.flex_feature_evidence(flex, model)
        _, after = _geometry(model)
        if evidence["type"] != case["type"] or evidence["error_code"] != 0:
            raise RuntimeError(f"Flex feature state mismatch: {evidence}")
        if all(math.isclose(a, b, abs_tol=1e-6) for a, b in zip(
            after["bounding_box_mm"], before["bounding_box_mm"],
        )):
            raise RuntimeError(f"{case['mode']} did not change body geometry")
        ratio = after["volume_mm3"] / before["volume_mm3"]
        low, high = case["volume_range"]
        if not low <= ratio <= high:
            raise RuntimeError(
                f"{case['mode']} produced an invalid volume ratio {ratio}: "
                f"before={before}, after={after}"
            )
        _assert_mode_geometry(case["mode"], before, after, ratio)
        _assert_amount_readback(case, evidence, before, after)
        if not bool(get_com_member(model, "ForceRebuild3", False)):
            raise RuntimeError(f"{case['mode']} rebuild failed")
        if any(int(get_com_member(feature, "GetErrorCode") or 0) != 0
               for feature in (base, flex)):
            raise RuntimeError(f"{case['mode']} feature tree contains an error")
        completed = True
        return title, {
            "status": "ok", "document": title, "saved": False,
            "mode": case["mode"], "amount": case["amount"],
            "feature": evidence, "before": before, "after": after,
            "volume_ratio": ratio,
        }
    finally:
        if not completed:
            sw.QuitDoc(title)


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    kept_title = str(get_com_member(original, "GetTitle")) if original else None
    results = []
    for case in CASES:
        title, row = _run_case(sw, case)
        results.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        if kept_title and kept_title != title:
            sw.QuitDoc(kept_title)
        kept_title = title
        sw.ActivateDoc2(title, False, 0)
    print(json.dumps({"status": "ok", "results": results}, ensure_ascii=False))


if __name__ == "__main__":
    main()
