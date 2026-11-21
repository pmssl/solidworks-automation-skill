"""Real SolidWorks regression for advanced native 2D sketch entities."""

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
    title = None
    try:
        model = new_document(sw, "part")
        title = str(get_com_member(model, "GetTitle"))
        with sw_part.sketch(model, "Front Plane"):
            ellipse = sw_part.sketch_ellipse(model, 0, 0, .030, .012, math.radians(37))
            parabola = sw_part.sketch_parabola(
                model, (0, .010), (0, 0), (-.020, .010), (.030, .0225)
            )
            equation = sw_part.sketch_equation_curve(
                model, "0.01*t", "0.002*t^2", -2, 3
            )
            text = sw_part.sketch_text(model, .040, -.020, "SW2025", width_factor=1.2)
        types = {
            "ellipse": int(get_com_member(ellipse, "GetType")),
            "parabola": int(get_com_member(parabola, "GetType")),
            "equation": int(get_com_member(equation, "GetType")),
        }
        if types != {"ellipse": 2, "parabola": 5, "equation": 3}:
            raise RuntimeError(f"advanced sketch entity types mismatch: {types}")
        curve = get_com_member(ellipse, "GetCurve")
        if curve is None or not bool(get_com_member(curve, "IsEllipse")):
            raise RuntimeError("ellipse did not retain analytic ellipse geometry")
        ellipse_params = [float(value) for value in get_com_member(curve, "GetEllipseParams")]
        text_value = str(get_com_member(text, "Text"))
        text_coordinates = [float(value) for value in get_com_member(text, "GetCoordinates")]
        if text_value != "SW2025":
            raise RuntimeError(f"sketch text readback mismatch: {text_value}")
        feature = get_com_member(model, "FeatureByName", "草图1") or get_com_member(model, "FeatureByName", "Sketch1")
        if feature is None or int(get_com_member(feature, "GetErrorCode")) != 0:
            raise RuntimeError("advanced sketch feature tree verification failed")
        if not bool(model.ForceRebuild3(False)):
            raise RuntimeError("advanced sketch rebuild failed")
        print(json.dumps({"status": "ok", "types": types,
                          "ellipse_params": ellipse_params,
                          "text": text_value, "text_coordinates": text_coordinates},
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
