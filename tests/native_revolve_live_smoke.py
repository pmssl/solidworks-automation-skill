"""Live SolidWorks smoke test for native construction axis and revolve."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document
from scripts.sw_native_parametric import NativeParametric


def main() -> None:
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    temp_title = None
    try:
        model = new_document(sw, "part")
        temp_title = str(get_com_member(model, "GetTitle"))
        engine = NativeParametric(
            connect=lambda: connect_solidworks(wait_seconds=1),
            part_ops=lambda: sw_part,
        )
        begun = engine.begin(temp_title, "Front Plane")
        token = begun["session_id"]
        engine.corner_rectangle(token, 10, -5, 20, 5)
        axis = engine.line(token, 0, -25, 0, 25, construction=True)
        if not axis["created_segments"][0]["construction"]:
            raise RuntimeError("The requested revolve axis is not construction geometry")
        engine.auto_define(token)
        geometry = engine.geometry(token)
        axes = [row for row in geometry["segments"] if row["construction"]]
        if len(axes) != 1:
            raise RuntimeError(f"Expected one construction axis, got {len(axes)}")
        engine.finish(token)
        revolved = engine.revolve(token, 270.0, reverse_direction=True)
        state = engine.model_state(token)
        if revolved["solid_body_count"] != 1:
            raise RuntimeError(f"Revolve did not create one solid: {revolved}")
        if abs(revolved["angle_deg"] - 270.0) > 1e-5:
            raise RuntimeError(f"Revolve angle readback failed: {revolved}")
        if not revolved["reverse_direction"]:
            raise RuntimeError(f"Revolve direction readback failed: {revolved}")
        bounds = [float(value) * 1000.0 for value in (model.GetPartBox(True) or ())]
        if len(bounds) != 6:
            raise RuntimeError(f"Part bounding box unavailable: {bounds}")
        spans = sorted(abs(bounds[index + 3] - bounds[index]) for index in range(3))
        expected = [10.0, 40.0, 40.0]
        if any(abs(actual - wanted) > 0.05 for actual, wanted in zip(spans, expected)):
            raise RuntimeError(f"Unexpected revolved body size: spans={spans}, bounds={bounds}")
        names = [row["name"] for row in state["features"]]
        if begun["sketch"] not in names or revolved["feature"] not in names:
            raise RuntimeError(f"Feature tree verification failed: {names}")

        cut_begun = engine.begin(temp_title, "Front Plane")
        cut_token = cut_begun["session_id"]
        engine.corner_rectangle(cut_token, 15, -2, 25, 2)
        engine.line(cut_token, 0, -25, 0, 25, construction=True)
        engine.auto_define(cut_token)
        engine.finish(cut_token)
        cut = engine.revolve(cut_token, 210.0, cut=True, reverse_direction=False)
        if not cut["cut"] or abs(cut["angle_deg"] - 210.0) > 1e-5:
            raise RuntimeError(f"Revolve cut definition readback failed: {cut}")
        if cut["solid_body_count"] != 1:
            raise RuntimeError(f"Revolve cut damaged body topology: {cut}")
        cut_state = engine.model_state(cut_token)
        cut_names = [row["name"] for row in cut_state["features"]]
        if cut_begun["sketch"] not in cut_names or cut["feature"] not in cut_names:
            raise RuntimeError(f"Cut feature tree verification failed: {cut_names}")
        print(json.dumps({
            "status": "ok",
            "document": temp_title,
            "sketch": begun["sketch"],
            "feature": revolved["feature"],
            "feature_type": revolved["feature_type"],
            "angle_deg": revolved["angle_deg"],
            "reverse_direction": revolved["reverse_direction"],
            "axis": revolved["axis"],
            "solid_body_count": revolved["solid_body_count"],
            "spans_mm": spans,
            "cut_feature": cut["feature"],
            "cut_angle_deg": cut["angle_deg"],
            "cut_body_count": cut["solid_body_count"],
        }, ensure_ascii=False))
    finally:
        if temp_title:
            sw.QuitDoc(temp_title)
        if original_title:
            try:
                sw.ActivateDoc2(original_title, False, 0)
            except Exception:
                pass


if __name__ == "__main__":
    main()
