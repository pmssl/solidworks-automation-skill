"""Persistent edge/vertex references across a topology change and reopen."""

from __future__ import annotations

import json
import math
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document, open_document, save_document
from scripts.sw_entity_reference import create_persistent_reference, resolve_persistent_reference


def point(vertex):
    return tuple(float(value) for value in get_com_member(vertex, "GetPoint")[:3])


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    open_title = None
    with tempfile.TemporaryDirectory(prefix="sw_persist_topology_") as temp_dir:
        path = Path(temp_dir) / "persistent_topology.SLDPRT"
        try:
            model = new_document(sw, "part")
            open_title = str(get_com_member(model, "GetTitle"))
            with sw_part.sketch(model, "Front Plane") as sketch_name:
                sw_part.sketch_rectangle(model, 0, 0, .040, .030)
            sw_part.extrude_boss_midplane(model, sketch_name, .020)
            long_edges = []
            for edge in sw_part.solid_edges(model):
                try: data = sw_part.edge_geometry(edge)
                except (TypeError, ValueError, RuntimeError): continue
                if abs(data["length"] - .040) < 1e-8:
                    long_edges.append((data["midpoint"], edge))
            long_edges.sort(key=lambda item: item[0])
            if len(long_edges) != 4:
                raise RuntimeError(f"40 mm edge count mismatch: {len(long_edges)}")
            target_edge = long_edges[0][1]
            fillet_edge = long_edges[-1][1]
            target_vertex = get_com_member(target_edge, "GetStartVertex")
            edge_before = sw_part.edge_geometry(target_edge)
            vertex_before = point(target_vertex)
            edge_ref = create_persistent_reference(model, target_edge)
            vertex_ref = create_persistent_reference(model, target_vertex)
            fillet = sw_part.fillet(model, .002, edges=(fillet_edge,))
            fillet_name = str(get_com_member(fillet, "Name"))
            immediate_edge = resolve_persistent_reference(model, edge_ref)
            immediate_vertex = resolve_persistent_reference(model, vertex_ref)
            if abs(sw_part.edge_geometry(immediate_edge["entity"])["length"] - .040) > 1e-8:
                raise RuntimeError("edge reference changed after fillet topology update")
            if math.dist(point(immediate_vertex["entity"]), vertex_before) > 1e-9:
                raise RuntimeError("vertex reference changed after fillet topology update")
            if not save_document(model, str(path)) or not path.is_file() or path.stat().st_size == 0:
                raise RuntimeError("topology persistent-reference part was not saved")
            sw.QuitDoc(str(get_com_member(model, "GetTitle"))); open_title = None
            reopened = open_document(sw, str(path), silent=True, raise_on_error=True)
            open_title = str(get_com_member(reopened, "GetTitle"))
            reopened_edge = resolve_persistent_reference(reopened, edge_ref)
            reopened_vertex = resolve_persistent_reference(reopened, vertex_ref)
            edge_after = sw_part.edge_geometry(reopened_edge["entity"])
            vertex_after = point(reopened_vertex["entity"])
            if abs(edge_after["length"] - edge_before["length"]) > 1e-9:
                raise RuntimeError(f"reopened edge mismatch: {edge_before} != {edge_after}")
            if math.dist(vertex_after, vertex_before) > 1e-9:
                raise RuntimeError(f"reopened vertex mismatch: {vertex_before} != {vertex_after}")
            print(json.dumps({
                "status": "ok", "topology_feature": fillet_name,
                "edge_reference_bytes": edge_ref.byte_count,
                "vertex_reference_bytes": vertex_ref.byte_count,
                "immediate_error_codes": [immediate_edge["error_code"], immediate_vertex["error_code"]],
                "reopen_error_codes": [reopened_edge["error_code"], reopened_vertex["error_code"]],
                "edge_length_mm": edge_after["length"] * 1000.0,
                "vertex_mm": [value * 1000.0 for value in vertex_after],
                "saved_size": path.stat().st_size,
            }, ensure_ascii=False))
        finally:
            if open_title:
                try: sw.QuitDoc(open_title)
                except Exception: pass
            if original_title:
                try: sw.ActivateDoc2(original_title, False, 0)
                except Exception: pass


if __name__ == "__main__":
    main()
