"""Real SolidWorks regression for vertex-based reference geometry."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_part
from scripts.sw_connect import connect_solidworks, get_com_member, new_document


def mm_values(values):
    return [float(value) * 1000.0 for value in values]


def main():
    sw, original = connect_solidworks(wait_seconds=1)
    original_title = str(get_com_member(original, "GetTitle")) if original else None
    model = new_document(sw, "part")
    title = str(get_com_member(model, "GetTitle"))
    try:
        with sw_part.sketch(model, "Front Plane") as sketch_name:
            sw_part.sketch_rectangle(model, 0, 0, .040, .030)
        base = sw_part.extrude_boss_midplane(model, sketch_name, .020)
        if base is None:
            raise RuntimeError("reference geometry base failed")
        targets = ((.020, .015, .010), (-.020, -.015, -.010))
        vertices = []
        for target in targets:
            matches = sw_part.find_solid_vertices(model, target, tolerance=1e-8)
            if len(matches) != 1:
                raise RuntimeError(f"vertex resolution mismatch at {target}: {len(matches)}")
            vertices.append(matches[0])

        face = sw_part.find_largest_outer_planar_face(model)
        face_center = sw_part.planar_face_geometry(face)["center"]
        point_feature = sw_part.reference_point_face_center(model, face)
        point_specific = get_com_member(point_feature, "GetSpecificFeature2")
        math_point = get_com_member(point_specific, "GetRefPoint")
        point = list(get_com_member(math_point, "ArrayData") or ())[:3]
        if math.dist(point, face_center) > 1e-8:
            raise RuntimeError(f"reference point mismatch: {point}")

        axis_feature = sw_part.reference_axis_from_vertices(
            model, vertices[0], vertices[1], auto_size=False
        )
        axis_specific = get_com_member(axis_feature, "GetSpecificFeature2")
        axis_params = list(get_com_member(axis_specific, "GetRefAxisParams") or ())[:6]
        if len(axis_params) != 6:
            raise RuntimeError(f"reference axis parameter mismatch: {axis_params}")
        direction = [axis_params[index + 3] - axis_params[index] for index in range(3)]
        expected = [targets[1][index] - targets[0][index] for index in range(3)]
        cross = (
            direction[1] * expected[2] - direction[2] * expected[1],
            direction[2] * expected[0] - direction[0] * expected[2],
            direction[0] * expected[1] - direction[1] * expected[0],
        )
        if math.sqrt(sum(value * value for value in cross)) > 1e-8:
            raise RuntimeError(f"reference axis direction mismatch: {axis_params}")

        plane_targets = (
            (.020, .015, .010),
            (-.020, .015, -.010),
            (.020, -.015, -.010),
        )
        plane_vertices = []
        for target in plane_targets:
            matches = sw_part.find_solid_vertices(model, target, tolerance=1e-8)
            if len(matches) != 1:
                raise RuntimeError(f"plane vertex resolution mismatch at {target}: {len(matches)}")
            plane_vertices.append(matches[0])
        ref_plane = sw_part.reference_plane_through_three_vertices(model, *plane_vertices)
        plane_geometry = sw_part.reference_plane_geometry(ref_plane)
        normal = plane_geometry["normal"]
        origin = plane_geometry["origin"]
        for target in plane_targets:
            distance = sum(normal[index] * (target[index] - origin[index]) for index in range(3))
            if abs(distance) > 1e-8:
                raise RuntimeError(
                    f"three-vertex reference plane misses {target}: distance={distance}"
                )
        plane_feature = sw_part._last_model_feature(model)
        plane_name = str(get_com_member(plane_feature, "Name"))

        base_faces = sw_part.find_planar_faces(
            model, area=.040 * .030, center=(0.0, 0.0, .010), normal=(0.0, 0.0, 1.0),
            tolerance=1e-8,
        )
        hinge_edges = sw_part.find_solid_edges(
            model, length=.040, direction=(1.0, 0.0, 0.0),
            midpoint=(0.0, .015, .010), tolerance=1e-8,
        )
        if len(base_faces) != 1 or len(hinge_edges) != 1:
            raise RuntimeError(
                f"angle plane references mismatch: faces={len(base_faces)}, edges={len(hinge_edges)}"
            )
        angle_plane = sw_part.reference_plane_at_angle(
            model, base_faces[0], hinge_edges[0], math.radians(37.0),
        )
        angle_geometry = sw_part.reference_plane_geometry(angle_plane)
        angle_normal = angle_geometry["normal"]
        base_normal = sw_part.planar_face_geometry(base_faces[0])["normal"]
        recovered_angle = math.acos(min(1.0, abs(sum(
            angle_normal[index] * base_normal[index] for index in range(3)
        ))))
        if abs(recovered_angle - math.radians(37.0)) > 1e-8:
            raise RuntimeError(f"angle reference plane mismatch: {math.degrees(recovered_angle)}")
        hinge_geometry = sw_part.edge_geometry(hinge_edges[0])
        angle_origin = angle_geometry["origin"]
        for point in (hinge_geometry["start"], hinge_geometry["end"]):
            residual = sum(angle_normal[index] * (point[index] - angle_origin[index])
                           for index in range(3))
            if abs(residual) > 1e-8:
                raise RuntimeError(f"angle plane misses hinge endpoint {point}: {residual}")
        angle_plane_name = str(get_com_member(sw_part._last_model_feature(model), "Name"))

        opposite_faces = sw_part.find_planar_faces(
            model, area=.040 * .030, center=(0.0, 0.0, -.010), normal=(0.0, 0.0, 1.0),
            tolerance=1e-8,
        )
        if len(opposite_faces) != 1:
            raise RuntimeError(f"midplane opposite face mismatch: {len(opposite_faces)}")
        midplane = sw_part.reference_midplane(model, base_faces[0], opposite_faces[0])
        midplane_geometry = sw_part.reference_plane_geometry(midplane)
        midplane_normal = midplane_geometry["normal"]
        midplane_distance = abs(midplane_geometry["origin"][2])
        if midplane_distance > 1e-8:
            raise RuntimeError(f"reference midplane offset mismatch: {midplane_distance}")
        if abs(abs(midplane_normal[2]) - 1.0) > 1e-8:
            raise RuntimeError(f"reference midplane normal mismatch: {midplane_normal}")
        midplane_name = str(get_com_member(sw_part._last_model_feature(model), "Name"))

        side_faces = sw_part.find_planar_faces(
            model, area=.040 * .020, center=(0.0, .015, 0.0), normal=(0.0, 1.0, 0.0),
            tolerance=1e-8,
        )
        if len(side_faces) != 1:
            raise RuntimeError(f"two-plane reference axis side face mismatch: {len(side_faces)}")
        plane_axis = sw_part.reference_axis_from_planes(
            model, base_faces[0], side_faces[0], auto_size=False,
        )
        plane_axis_specific = get_com_member(plane_axis, "GetSpecificFeature2")
        plane_axis_params = list(get_com_member(plane_axis_specific, "GetRefAxisParams") or ())[:6]
        if len(plane_axis_params) != 6:
            raise RuntimeError(f"two-plane reference axis parameters missing: {plane_axis_params}")
        plane_axis_direction = [
            plane_axis_params[index + 3] - plane_axis_params[index] for index in range(3)
        ]
        direction_length = math.sqrt(sum(value * value for value in plane_axis_direction))
        unit_direction = [value / direction_length for value in plane_axis_direction]
        if abs(abs(unit_direction[0]) - 1.0) > 1e-8:
            raise RuntimeError(f"two-plane reference axis direction mismatch: {unit_direction}")
        for point in (plane_axis_params[:3], plane_axis_params[3:6]):
            if abs(point[1] - .015) > 1e-8 or abs(point[2] - .010) > 1e-8:
                raise RuntimeError(f"two-plane reference axis location mismatch: {plane_axis_params}")

        with sw_part.sketch(model, "Front Plane") as cylinder_sketch:
            sw_part.sketch_circle(model, .050, 0.0, .010)
        cylinder_feature = sw_part.extrude_boss_midplane(
            model, cylinder_sketch, .030, merge=False,
        )
        if cylinder_feature is None:
            raise RuntimeError("reference-axis cylinder failed")
        cylinder_faces = sw_part.find_cylindrical_faces(
            model, radius=.010, axis=(0.0, 0.0, 1.0), tolerance=1e-8,
        )
        if len(cylinder_faces) != 1:
            raise RuntimeError(f"cylindrical reference face mismatch: {len(cylinder_faces)}")
        cylinder_axis = sw_part.reference_axis_from_cylindrical_face(
            model, cylinder_faces[0], auto_size=False,
        )
        cylinder_axis_specific = get_com_member(cylinder_axis, "GetSpecificFeature2")
        cylinder_axis_params = list(
            get_com_member(cylinder_axis_specific, "GetRefAxisParams") or ()
        )[:6]
        cylinder_direction = [
            cylinder_axis_params[index + 3] - cylinder_axis_params[index]
            for index in range(3)
        ]
        if abs(cylinder_axis_params[0] - .050) > 1e-8 or abs(cylinder_axis_params[1]) > 1e-8:
            raise RuntimeError(f"cylindrical reference axis location mismatch: {cylinder_axis_params}")
        if abs(cylinder_direction[0]) > 1e-8 or abs(cylinder_direction[1]) > 1e-8:
            raise RuntimeError(f"cylindrical reference axis direction mismatch: {cylinder_axis_params}")

        point_target = (-.020, -.015, -.010)
        point_matches = sw_part.find_solid_vertices(model, point_target, tolerance=1e-8)
        if len(point_matches) != 1:
            raise RuntimeError(f"point-plane axis vertex mismatch: {len(point_matches)}")
        point_plane_axis = sw_part.reference_axis_from_point_and_plane(
            model, point_matches[0], base_faces[0], auto_size=False,
        )
        point_plane_specific = get_com_member(point_plane_axis, "GetSpecificFeature2")
        point_plane_params = list(
            get_com_member(point_plane_specific, "GetRefAxisParams") or ()
        )[:6]
        point_plane_direction = [
            point_plane_params[index + 3] - point_plane_params[index]
            for index in range(3)
        ]
        if any(abs(point_plane_params[index] - point_target[index]) > 1e-8
               for index in (0, 1)):
            raise RuntimeError(f"point-plane reference axis location mismatch: {point_plane_params}")
        if abs(point_plane_direction[0]) > 1e-8 or abs(point_plane_direction[1]) > 1e-8:
            raise RuntimeError(f"point-plane reference axis direction mismatch: {point_plane_params}")

        edge_axis = sw_part.reference_axis_from_straight_edge(
            model, hinge_edges[0], auto_size=False,
        )
        edge_axis_specific = get_com_member(edge_axis, "GetSpecificFeature2")
        edge_axis_params = list(get_com_member(edge_axis_specific, "GetRefAxisParams") or ())[:6]
        edge_axis_points = (tuple(edge_axis_params[:3]), tuple(edge_axis_params[3:6]))
        hinge_points = (hinge_geometry["start"], hinge_geometry["end"])
        if not all(any(math.dist(point, hinge) <= 1e-8 for hinge in hinge_points)
                   for point in edge_axis_points):
            raise RuntimeError(f"straight-edge reference axis mismatch: {edge_axis_params}")

        with sw_part.sketch(model, "Front Plane") as cone_base_sketch:
            sw_part.sketch_circle(model, .085, 0.0, .012)
        cone_plane = sw_part.offset_plane(model, "Front Plane", .030)
        cone_plane_name = str(get_com_member(cone_plane, "Name"))
        with sw_part.sketch(model, cone_plane_name) as cone_top_sketch:
            sw_part.sketch_circle(model, .085, 0.0, .006)
        cone_feature = sw_part.loft_feature(
            model, (cone_base_sketch, cone_top_sketch), cut=False, merge=False,
        )
        if cone_feature is None:
            raise RuntimeError("reference-axis conical frustum failed")
        expected_half_angle = math.atan((.012 - .006) / .030)
        conical_faces = sw_part.find_conical_faces(
            model, axis=(0.0, 0.0, 1.0), half_angle=expected_half_angle, tolerance=1e-8,
        )
        if len(conical_faces) != 1:
            all_cones = [sw_part.conical_face_geometry(face) for face in sw_part.solid_faces(model)
                         if bool(get_com_member(get_com_member(face, "GetSurface"), "IsCone"))]
            raise RuntimeError(f"conical reference face mismatch: {len(conical_faces)}, {all_cones}")
        conical_axis = sw_part.reference_axis_from_conical_face(
            model, conical_faces[0], auto_size=False,
        )
        conical_axis_specific = get_com_member(conical_axis, "GetSpecificFeature2")
        conical_axis_params = list(
            get_com_member(conical_axis_specific, "GetRefAxisParams") or ()
        )[:6]
        conical_direction = [
            conical_axis_params[index + 3] - conical_axis_params[index]
            for index in range(3)
        ]
        if abs(conical_axis_params[0] - .085) > 1e-8 or abs(conical_axis_params[1]) > 1e-8:
            raise RuntimeError(f"conical reference axis location mismatch: {conical_axis_params}")
        if abs(conical_direction[0]) > 1e-8 or abs(conical_direction[1]) > 1e-8:
            raise RuntimeError(f"conical reference axis direction mismatch: {conical_axis_params}")

        location = (.007, -.004, .003)
        rotation = tuple(math.radians(value) for value in (17.0, 23.0, 31.0))
        coordinate_feature = sw_part.coordinate_system_numeric(model, location, rotation)
        coordinate_name = str(get_com_member(coordinate_feature, "Name"))
        transform = list(get_com_member(model, "GetCoordinateSystemXformByName", coordinate_name) or ())
        if len(transform) < 12:
            raise RuntimeError(f"coordinate-system transform missing: {transform}")
        rows = [transform[0:3], transform[3:6], transform[6:9]]
        recovered_location = tuple(
            -sum(rows[row][column] * transform[9 + column] for column in range(3))
            for row in range(3)
        )
        if math.dist(recovered_location, location) > 1e-8:
            raise RuntimeError(
                f"coordinate-system location mismatch: recovered={recovered_location}, "
                f"transform={transform}"
            )
        if all(abs(transform[index] - (1.0 if index in (0, 4, 8) else 0.0)) < 1e-9
               for index in range(9)):
            raise RuntimeError("coordinate-system rotation unexpectedly remained identity")

        rebuild = int(model.ForceRebuild3(False))
        print(json.dumps({
            "status": "ok",
            "reference_point": {"feature": str(get_com_member(point_feature, "Name")),
                                "point_mm": mm_values(point)},
            "reference_axis": {"feature": str(get_com_member(axis_feature, "Name")),
                               "params_mm": mm_values(axis_params)},
            "reference_plane": {"feature": plane_name,
                                "origin_mm": mm_values(origin),
                                "normal": normal,
                                "points_mm": [mm_values(point) for point in plane_targets]},
            "angle_reference_plane": {"feature": angle_plane_name,
                                      "angle_deg": math.degrees(recovered_angle),
                                      "normal": angle_normal,
                                      "hinge_mm": [mm_values(hinge_geometry["start"]),
                                                   mm_values(hinge_geometry["end"])]},
            "midplane": {"feature": midplane_name,
                         "offset_mm": midplane_distance * 1000.0,
                         "normal": midplane_normal},
            "two_plane_axis": {"feature": str(get_com_member(plane_axis, "Name")),
                               "params_mm": mm_values(plane_axis_params)},
            "cylindrical_axis": {"feature": str(get_com_member(cylinder_axis, "Name")),
                                 "params_mm": mm_values(cylinder_axis_params)},
            "point_plane_axis": {"feature": str(get_com_member(point_plane_axis, "Name")),
                                 "params_mm": mm_values(point_plane_params)},
            "straight_edge_axis": {"feature": str(get_com_member(edge_axis, "Name")),
                                   "params_mm": mm_values(edge_axis_params)},
            "conical_axis": {"feature": str(get_com_member(conical_axis, "Name")),
                             "params_mm": mm_values(conical_axis_params),
                             "half_angle_deg": math.degrees(expected_half_angle)},
            "coordinate_system": {"feature": coordinate_name,
                                  "translation_mm": mm_values(transform[9:12]),
                                  "recovered_origin_mm": mm_values(recovered_location),
                                  "rotation_matrix": transform[:9]},
            "rebuild": rebuild,
        }, ensure_ascii=False))
    finally:
        try:
            sw.QuitDoc(title)
        except Exception:
            pass
        if original_title:
            try:
                sw.ActivateDoc2(original_title, False, 0)
            except Exception:
                pass


if __name__ == "__main__":
    main()
