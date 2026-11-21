"""Real SolidWorks regression for native reference-point modes 2 through 6."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def mm(point): return [float(value) * 1000.0 for value in point]


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    try:
        with sw_part.sketch(model, "Front Plane") as sketch_name:
            sw_part.sketch_rectangle(model, 0.0, 0.0, .040, .030)
        sw_part.extrude_boss_midplane(model, sketch_name, .020)

        with sw_part.sketch(model, "Front Plane") as cylinder_sketch:
            sw_part.sketch_circle(model, .050, 0.0, .010)
        sw_part.extrude_boss_midplane(model, cylinder_sketch, .030, merge=False)

        top_faces = sw_part.find_planar_faces(
            model, area=.040 * .030, center=(0.0, 0.0, .010),
            normal=(0.0, 0.0, 1.0), tolerance=1e-8,
        )
        x_edges = sw_part.find_solid_edges(
            model, length=.040, direction=(1.0, 0.0, 0.0),
            midpoint=(0.0, .015, .010), tolerance=1e-8,
        )
        y_edges = sw_part.find_solid_edges(
            model, length=.030, direction=(0.0, 1.0, 0.0),
            midpoint=(.020, 0.0, .010), tolerance=1e-8,
        )
        bottom_vertices = sw_part.find_solid_vertices(
            model, (-.020, -.015, -.010), tolerance=1e-8,
        )
        circular_edges = sw_part.find_circular_edges(
            model, center=(.050, 0.0, .015), radius=.010,
            axis=(0.0, 0.0, 1.0), tolerance=1e-8,
        )
        if not all(len(items) == 1 for items in (
            top_faces, x_edges, y_edges, bottom_vertices, circular_edges,
        )):
            raise RuntimeError(
                f"reference-point inputs mismatch: face={len(top_faces)}, "
                f"xedge={len(x_edges)}, yedge={len(y_edges)}, vertex={len(bottom_vertices)}, "
                f"circle={len(circular_edges)}"
            )

        face_center_feature = sw_part.reference_point_face_center(model, top_faces[0])
        face_center = sw_part.reference_point_geometry(face_center_feature)
        if math.dist(face_center, (0.0, 0.0, .010)) > 1e-8:
            raise RuntimeError(f"face-center reference point mismatch: {face_center}")

        edge_center_feature = sw_part.reference_point_edge_center(model, circular_edges[0])
        edge_center = sw_part.reference_point_geometry(edge_center_feature)
        if math.dist(edge_center, (.050, 0.0, .015)) > 1e-8:
            raise RuntimeError(f"edge-center reference point mismatch: {edge_center}")

        along_feature = sw_part.reference_point_along_curve(
            model, x_edges[0], 25.0, mode="percentage",
        )[0]
        along_point = sw_part.reference_point_geometry(along_feature)
        hinge = sw_part.edge_geometry(x_edges[0])
        if abs(along_point[1] - .015) > 1e-8 or abs(along_point[2] - .010) > 1e-8:
            raise RuntimeError(f"along-edge reference point left edge: {along_point}")
        endpoint_distance = min(
            math.dist(along_point, hinge["start"]),
            math.dist(along_point, hinge["end"]),
        )
        if abs(endpoint_distance - .010) > 1e-8:
            raise RuntimeError(f"along-edge percentage mismatch: {along_point}")

        distance_feature = sw_part.reference_point_along_curve(
            model, x_edges[0], .012, mode="distance",
        )[0]
        distance_point = sw_part.reference_point_geometry(distance_feature)
        distance_to_endpoint = min(
            math.dist(distance_point, hinge["start"]),
            math.dist(distance_point, hinge["end"]),
        )
        if abs(distance_to_endpoint - .012) > 1e-8:
            raise RuntimeError(f"along-edge distance mismatch: {distance_point}")

        distributed_features = sw_part.reference_point_along_curve(
            model, x_edges[0], 0.0, mode="evenly_distributed", count=3,
        )
        distributed_points = [sw_part.reference_point_geometry(feature)
                              for feature in distributed_features]
        if len(distributed_points) != 3:
            raise RuntimeError(f"distributed reference point count mismatch: {len(distributed_points)}")
        sorted_x = sorted(point[0] for point in distributed_points)
        if any(abs(point[1] - .015) > 1e-8 or abs(point[2] - .010) > 1e-8
               for point in distributed_points):
            raise RuntimeError(f"distributed points left edge: {distributed_points}")
        if abs((sorted_x[1] - sorted_x[0]) - (sorted_x[2] - sorted_x[1])) > 1e-8:
            raise RuntimeError(f"distributed points are not uniform: {distributed_points}")

        projection_feature = sw_part.reference_point_face_vertex_projection(
            model, top_faces[0], bottom_vertices[0],
        )
        projection = sw_part.reference_point_geometry(projection_feature)
        if math.dist(projection, (-.020, -.015, .010)) > 1e-8:
            raise RuntimeError(f"face-vertex projection mismatch: {projection}")

        intersection_feature = sw_part.reference_point_intersection(
            model, x_edges[0], y_edges[0],
        )
        intersection = sw_part.reference_point_geometry(intersection_feature)
        if math.dist(intersection, (.020, .015, .010)) > 1e-8:
            raise RuntimeError(f"edge intersection reference point mismatch: {intersection}")

        with sw_part.sketch(model, "Front Plane"):
            native_sketch_point = sw_part.sketch_point(model, .005, -.006)
        sketch_point_feature = sw_part.reference_point_from_sketch_point(
            model, native_sketch_point,
        )
        sketch_point = sw_part.reference_point_geometry(sketch_point_feature)
        if math.dist(sketch_point, (.005, -.006, 0.0)) > 1e-8:
            raise RuntimeError(f"sketch-point reference mismatch: {sketch_point}")

        rebuild = int(model.ForceRebuild3(False))
        print(json.dumps({
            "status": "ok",
            "face_center_mm": mm(face_center),
            "edge_center_mm": mm(edge_center),
            "along_25_percent_mm": mm(along_point),
            "along_12_mm": mm(distance_point),
            "distributed_mm": [mm(point) for point in distributed_points],
            "projection_mm": mm(projection),
            "intersection_mm": mm(intersection),
            "sketch_point_mm": mm(sketch_point),
            "rebuild": rebuild,
        }, ensure_ascii=False))
    finally:
        try: sw.QuitDoc(title)
        except Exception: pass
        if original_title:
            try: sw.ActivateDoc2(original_title, False, 0)
            except Exception: pass


if __name__ == "__main__":
    main()
