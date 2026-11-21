"""Real SolidWorks regression for recursive Feature parent/child graphs."""

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
    completed = False
    try:
        with sw_part.sketch(model, "Front Plane") as base_sketch:
            sw_part.sketch_rectangle(model, 0.0, 0.0, .040, .030)
        base = sw_part.extrude_boss_midplane(model, base_sketch, .020)
        with sw_part.sketch(model, "Front Plane") as cut_sketch:
            sw_part.sketch_circle(model, 0.0, 0.0, .005)
        cut = sw_part.extrude_cut_through_all(model, cut_sketch)

        circular = []
        for edge in sw_part.find_circular_edges(model, radius=.005, axis=(0.0, 0.0, 1.0)):
            circular.append((sw_part.circular_edge_geometry(edge), edge))
        if len(circular) != 2:
            raise RuntimeError(f"expected two hole rim edges, found {len(circular)}")
        circular.sort(key=lambda item: item[0]["center"][2])
        fillet = sw_part.fillet(model, .001, edges=(circular[-1][1],))

        graph = sw_part.feature_dependency_graph(model, fillet, recursive=True)
        names = {node["name"] for node in graph["nodes"]}
        base_name = str(get_com_member(base, "Name"))
        cut_name = str(get_com_member(cut, "Name"))
        fillet_name = str(get_com_member(fillet, "Name"))
        rebuilt = bool(get_com_member(model, "ForceRebuild3", False))
        error_codes = {
            str(get_com_member(feature, "Name")): int(get_com_member(feature, "GetErrorCode"))
            for feature in (base, cut, fillet)
        }
        if (
            not {base_name, cut_name, fillet_name}.issubset(names)
            or len(graph["edges"]) < 2
            or any(error_codes.values())
            or not rebuilt
        ):
            raise RuntimeError(
                f"feature dependency graph mismatch: names={sorted(names)}, "
                f"edges={graph['edges']}, errors={error_codes}, rebuild={rebuilt}"
            )

        print(json.dumps({
            "status": "ok",
            "root_feature": fillet_name,
            "required_chain": [base_name, cut_name, fillet_name],
            "node_count": len(graph["nodes"]),
            "edge_count": len(graph["edges"]),
            "graph": graph,
            "feature_error_codes": error_codes,
            "rebuild": rebuilt,
            "live_document_title": title,
            "saved": False,
        }, ensure_ascii=False))
        completed = True
    finally:
        if not completed:
            try:
                sw.QuitDoc(title)
            except Exception:
                pass
        if not completed and original_title:
            try:
                sw.ActivateDoc2(original_title, False, 0)
            except Exception:
                pass


if __name__ == "__main__":
    main()
