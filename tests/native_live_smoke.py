"""Disposable live-COM smoke test for the native parametric workflow.

Creates one unsaved Part, exercises the same engine used by the Skill CLI,
and always closes the temporary document.
"""

from __future__ import annotations

import json

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document
from scripts.sw_native_parametric import NativeParametric, _com_get


def main() -> None:
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    temp = None
    temp_title = None
    try:
        temp = new_document(sw, "part")
        temp_title = str(get_com_member(temp, "GetTitle"))
        engine = NativeParametric(
            connect=lambda: connect_solidworks(wait_seconds=1),
            part_ops=lambda: sw_part,
        )
        begun = engine.begin(temp_title, "Front Plane")
        token = begun["session_id"]
        steps = [begun]
        steps.append(engine.rectangle(token, 100, 60))
        steps.append(engine.dimension(token, "horizontal", 100))
        steps.append(engine.dimension(token, "vertical", 60))
        steps.append(engine.status(token))
        if not steps[-1]["fully_defined"]:
            sketch = temp.SketchManager.ActiveSketch
            points = _com_get(sketch, "GetSketchPoints2") or ()
            print(json.dumps({
                "diagnostic_sketch_points": [
                    [float(point.X), float(point.Y)] for point in points
                ]
            }), flush=True)
            steps.append(engine.auto_define(token))
            steps.append(engine.status(token))
        steps.append(engine.finish(token))
        steps.append(engine.extrude(token, 20))
        steps.append(engine.model_state(token))
        print(json.dumps({"status": "ok", "steps": steps}, ensure_ascii=False))
    finally:
        if temp_title:
            sw.CloseDoc(temp_title)
        if original_title:
            try:
                sw.ActivateDoc2(original_title, False, 0)
            except Exception:
                pass


if __name__ == "__main__":
    main()
