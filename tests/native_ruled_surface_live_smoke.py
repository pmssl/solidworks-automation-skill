"""Real SolidWorks regression for a normal ruled surface."""

from __future__ import annotations

import json
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
        with sw_part.sketch(model, "Front Plane") as sketch_name:
            sw_part.sketch_rectangle(model, 0, 0, .040, .030)
        sw_part.planar_surface_from_sketch(model, sketch_name)
        bodies_before = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
        edges = tuple(get_com_member(bodies_before[0], "GetEdges") or ())
        candidates = []
        for edge in edges:
            try:
                data = sw_part.edge_geometry(edge)
            except (TypeError, ValueError, RuntimeError):
                continue
            if abs(data["length"] - .040) < 1e-8:
                candidates.append(edge)
        if len(candidates) != 2:
            raise RuntimeError(f"40 mm boundary edge count mismatch: {len(candidates)}")
        feature = sw_part.ruled_surface_from_edges(model, candidates[0], .010)
        bodies_after = tuple(get_com_member(model, "GetBodies2", 1, False) or ())
        area_after = sum(
            float(get_com_member(face, "GetArea"))
            for body in bodies_after
            for face in tuple(get_com_member(body, "GetFaces") or ())
        ) * 1e6
        expected_area = 1200.0 + 400.0
        if abs(area_after - expected_area) > 1e-4:
            raise RuntimeError(f"ruled surface area mismatch: {area_after} vs {expected_area}")
        print(json.dumps({
            "status": "ok",
            "feature": str(get_com_member(feature, "Name")),
            "surface_type": 1,
            "edge_length_mm": 40.0,
            "ruled_length_mm": 10.0,
            "surface_body_count": len(bodies_after),
            "total_area_mm2": area_after,
        }, ensure_ascii=False))
    finally:
        try: sw.QuitDoc(title)
        except Exception: pass
        if original_title:
            try: sw.ActivateDoc2(original_title, False, 0)
            except Exception: pass


if __name__ == "__main__":
    main()
