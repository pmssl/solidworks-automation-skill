"""Live smoke test for adding a centered boss on an existing planar face."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts import sw_part
from scripts.sw_connect import (
    connect_solidworks,
    get_com_member,
    open_document,
)
from scripts.sw_native_parametric import NativeParametric


def main(path: str) -> None:
    target = Path(path).resolve()
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = None
    title = None
    try:
        model = open_document(sw, str(target), silent=True, raise_on_error=True)
        title = str(get_com_member(model, "GetTitle"))
        engine = NativeParametric(
            connect=lambda: connect_solidworks(wait_seconds=1),
            part_ops=lambda: sw_part,
        )
        begun = engine.begin(title, "largest_planar_face")
        token = begun["session_id"]
        engine.rectangle(token, 40, 40)
        engine.dimension(token, "horizontal", 40)
        try:
            engine.dimension(token, "vertical", 40)
        except RuntimeError as exc:
            if "reference/driven" not in str(exc):
                raise
        if not engine.status(token)["fully_defined"]:
            engine.auto_define(token)
        finished = engine.finish(token)
        extrusion = engine.extrude(token, 40)
        state = engine.model_state(token)
        box = list(get_com_member(model, "GetPartBox", True) or ())
        envelope = [round((float(box[index + 3]) - float(box[index])) * 1000.0, 6)
                    for index in range(3)] if len(box) >= 6 else None
        print(json.dumps({
            "status": "ok",
            "document": title,
            "sketch": begun["sketch"],
            "finished": finished,
            "extrusion": extrusion,
            "solid_body_count": state["solid_body_count"],
            "envelope_mm": envelope,
            "features": [row for row in state["features"]
                         if row["type"] in {"ProfileFeature", "Extrusion"}],
            "saved": False,
        }, ensure_ascii=False))
    finally:
        if title:
            sw.QuitDoc(title)
        if original_title:
            try:
                sw.ActivateDoc2(original_title, False, 0)
            except Exception:
                pass


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m tests.native_face_boss_live_smoke FILE.SLDPRT")
    main(sys.argv[1])
