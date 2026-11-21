"""Build and verify the drawing as a native SolidWorks part."""

import argparse
import json
import math
import shutil
import sys
from pathlib import Path
from tempfile import mkdtemp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import sw_part as part
from sw_connect import get_com_member as read, mm, create_empty_dispatch_variant
from sw_native_parametric import _exact_sketch_creation, _no_dimension_popup, _sketch_geometry, _sketch_status
from sw_review import collect_geometry_measurements, run_review, set_standard_view
from sw_session import SolidWorksSession

OUTPUT = ROOT / "output"
TARGET = OUTPUT / "bracket_from_drawing.SLDPRT"


def origin(model, mark):
    for name in ("Point1@Origin", "点1@原点", ""):
        if model.Extension.SelectByID2(
            name, "EXTSKETCHPOINT", 0, 0, 0, False, mark,
            create_empty_dispatch_variant(), 0,
        ):
            return
    raise RuntimeError("Could not select the sketch origin")


def dimension(model, entities, position, name, value, method="AddDimension2"):
    model.ClearSelection2(True)
    for index, entity in enumerate(entities):
        if not part._select_com_object(entity, append=index > 0):
            raise RuntimeError(f"Cannot select geometry for {name}")
    point = tuple(map(mm, position))
    display = getattr(model, method)(*point)
    model.ClearSelection2(True)
    if display is None:
        raise RuntimeError(f"Missing dimension {name}")
    dim = display.GetDimension2(0)
    if int(dim.DrivenState) != 2 or abs(float(dim.SystemValue) * 1000 - value) > .001:
        raise RuntimeError(f"Invalid driving dimension {name}: {dim.SystemValue}")
    dim.Name = name
    return dim


def line(model, start, end):
    return part.sketch_line(model, *map(mm, (*start, *end)))


def circle(model, x, y, radius):
    return part.sketch_circle(model, mm(x), mm(y), mm(radius))


def point(entity, suffix):
    return read(entity, "Get" + suffix + "Point2")


def relate(model, kind, *entities):
    part.add_sketch_relation_direct(model, entities, kind)


def polygon_relations(model, segments):
    for index, segment in enumerate(segments):
        next_segment = segments[(index + 1) % len(segments)]
        end, start = point(segment, "End"), point(next_segment, "Start")
        if read(end, "GetID") != read(start, "GetID"):
            relate(model, 9, end, start)


def base_profile(model):
    # Top sketch XY maps to model X,-Z.
    segments = part.sketch_corner_rectangle(model, mm(-41), 0, mm(41), mm(38))
    for segment in segments:
        a, b = point(segment, "Start"), point(segment, "End")
        dx, dy = abs(a.X - b.X), abs(a.Y - b.Y)
        if dx > dy and min(a.Y, b.Y) < .001:
            dimension(model, [segment], (0, -8, 0), "BaseWidth", 82)
        if dy > dx and max(a.X, b.X) > 0:
            dimension(model, [segment], (50, 19, 0), "BaseDepth", 38)


def upright_profile(model):
    d = (41, -48)
    distance_sq = sum(v*v for v in d)
    a = 19**2 / distance_sq
    b = 19 * math.sqrt(distance_sq - 19**2) / distance_sq
    right = (a*d[0] - b*d[1], 58 + a*d[1] + b*d[0])
    left = (-right[0], right[1])
    with _exact_sketch_creation(model.SketchManager):
        ls = line(model, (-41, 10), left)
        arc = part.sketch_arc(model, 0, mm(58), *map(mm, (*left, *right)), -1)
        rs = line(model, right, (41, 10))
        bottom = line(model, (41, 10), (-41, 10))
    polygon_relations(model, (ls, arc, rs, bottom))
    relate(model, 4, bottom)
    relate(model, 6, ls, arc)
    relate(model, 6, rs, arc)
    dimension(model, [bottom], (0, 2, -28), "UprightWidth", 82)
    dimension(model, [arc], (28, 76, -28), "CrownRadius", 19)


def rib_profile(model):
    # Right sketch XY maps to model -Z,Y.
    with _exact_sketch_creation(model.SketchManager):
        bottom = line(model, (0, 10), (28, 10))
        back = line(model, (28, 10), (28, 40))
        slope = line(model, (28, 40), (0, 10))
    polygon_relations(model, (bottom, back, slope))
    relate(model, 4, bottom)
    relate(model, 5, back)
    dimension(model, [bottom], (0, 1, -14), "RibRun", 28)
    dimension(model, [back], (0, 25, -35), "RibHeight", 30)


def circular_profile(centers, diameter, position):
    def draw(model):
        with _exact_sketch_creation(model.SketchManager):
            circles = [circle(model, x, y, diameter / 2) for x, y in centers]
        dimension(model, circles[:1], position, "Diameter", diameter)
        if len(circles) == 2:
            relate(model, 14, *circles)
            left, right = [point(item, "Center") for item in circles]
            relate(model, 25, left, right)
            dimension(model, [left, right], (0, 10, -2),
                      "HolePitch", 54, "AddHorizontalDimension2")
    return draw


def same_geometry(first, second):
    def equivalent(left, right):
        if left.keys() != right.keys():
            return False
        for key, a in left.items():
            b = right[key]
            if isinstance(a, (list, tuple)):
                if math.dist(a, b) > .005:
                    return False
            elif isinstance(a, float):
                if abs(a-b) > .005:
                    return False
            elif a != b:
                return False
        return True
    return len(first) == len(second) and all(map(equivalent, first, second))


def dimension_evidence(feature):
    result = {}
    display = read(feature, "GetFirstDisplayDimension")
    while display is not None:
        dim = display.GetDimension2(0)
        if int(dim.DrivenState) == 2:
            result[str(dim.Name)] = round(float(dim.SystemValue) * 1000, 6)
        display = read(feature, "GetNextDisplayDimension", display)
    return result


def build_sketch(sw, model, plane, name, draw, sketches):
    part.start_sketch(model, plane)
    active = model.SketchManager.ActiveSketch
    before = _sketch_geometry(active)
    if before:
        raise RuntimeError("Expected a new blank sketch")
    with _no_dimension_popup(sw):
        draw(model)
        initial = _sketch_geometry(active)
        if not _sketch_status(active)["fully_defined"]:
            model.ClearSelection2(True)
            origin(model, 2 | 4)
            null = create_empty_dispatch_variant()
            model.SketchManager.FullyDefineSketch(
                True, True, 2 | 4 | 512, True, 1, null, 1, null, 1, 1
            )
            model.ClearSelection2(True)
    status = _sketch_status(active)
    final = _sketch_geometry(active)
    if not status["fully_defined"] or not same_geometry(initial, final):
        raise RuntimeError(f"{name}: {status} geometry {initial} -> {final}")
    transform = read(read(active, "ModelToSketchTransform"), "ArrayData")
    normal = tuple(transform[i] for i in (2, 5, 8))
    offset = -1000.0 * transform[11]
    ref = part.end_sketch(model)
    if ref.feature is None:
        ref.feature = part._feature_object(model, ref.name)
    ref.feature.Name = name
    dims = dimension_evidence(ref.feature)
    if not dims:
        raise RuntimeError(f"{name}: no driving dimensions")
    sketches.append({"name": name, **status, "driving_mm": dims, "geometry_mm": final,
                     "normal_xyz": normal, "offset_mm": offset})
    print(name, dims, normal, offset, flush=True)
    return ref, normal, offset


def reverse_in_direction(normal, vector):
    alignment = sum(a*b for a, b in zip(normal, vector))
    if abs(alignment) < .999:
        raise RuntimeError(f"Extrusion axis mismatch: {normal}, {vector}")
    return alignment > 0


def verify_feature(model, feature, name, volume_change, rows):
    if feature is None:
        raise RuntimeError(f"SolidWorks did not create {name}")
    feature.Name = name
    rebuilt = bool(model.ForceRebuild3(False))
    error = int(read(feature, "GetErrorCode"))
    bodies = tuple(read(model, "GetBodies2", 0, False) or ())
    if error or not rebuilt or len(bodies) != 1:
        raise RuntimeError(f"{name}: rebuild={rebuilt}, error={error}, bodies={len(bodies)}")
    volume = float(read(bodies[0], "GetMassProperties", 1.0)[3]) * 1e9
    previous = rows[-1]["volume_mm3"] if rows else 0
    if abs(volume - previous - volume_change) > .03:
        raise RuntimeError(f"{name}: volume change {volume-previous} vs {volume_change}")
    row = {"name": str(feature.Name), "type": read(feature, "GetTypeName2"),
           "error": error, "rebuild": rebuilt, "solids": len(bodies),
           "volume_mm3": volume, "driving_mm": dimension_evidence(feature)}
    rows.append(row)
    print(row, flush=True)


def build_stages(session, model, sketches, features):
    def profile(plane, name, draw):
        return build_sketch(session.sw, model, plane, name, draw, sketches)

    def base_plate():
        base, n, _ = profile("Top Plane", "Base outline", base_profile)
        verify_feature(model, part.extrude_boss(model, base, mm(10),
                       direction=not reverse_in_direction(n, (0, 1, 0))),
                       "Base 10 mm", 82*38*10, features)

    def front_corners():
        edges = [edge for x in (-41, 41) for edge in part.find_solid_edges(
            model, length=mm(10), direction=(0, 1, 0), midpoint=(mm(x), mm(5), 0))]
        if len(edges) != 2:
            raise RuntimeError("Expected two front base corner edges")
        verify_feature(model, part.fillet(model, mm(14), edges), "Front corners R14",
                       -2 * 10 * 14**2 * (1-math.pi/4), features)

    plane_specs = (
        ("Base top Y10", "Top Plane", 10, False, (1, 10)),
        ("Upright front Z-28", "Front Plane", 28, True, (2, -28)),
        ("Upright rear Z-38", "Front Plane", 38, True, (2, -38)),
    )
    top, front, rear = (spec[0] for spec in plane_specs)

    def reference_planes():
        for label, ref, distance, reverse, expected in plane_specs:
            plane = part.offset_plane(model, ref, mm(distance), reverse)
            if plane is None:
                raise RuntimeError(f"Missing plane {label}")
            plane.Name = label
            origin_xyz = part.reference_plane_geometry(read(plane, "GetSpecificFeature2"))["origin"]
            index, coord = expected
            if int(read(plane, "GetErrorCode")) or not model.ForceRebuild3(False) or abs(origin_xyz[index]*1000-coord) > .001:
                raise RuntimeError(f"Invalid plane {label}: {origin_xyz}")
            model.ClearSelection2(True)
            if plane.Select2(False, 0):
                model.BlankRefGeom()
        model.ClearSelection2(True)

    def mounting_cut(diameter, depth, label):
        centers = [(-27, 14), (27, 14)]
        hole, normal, _ = profile(top, label + " layout",
                                  circular_profile(centers, diameter, (-38, 10, -18)))
        reverse = reverse_in_direction(normal, (0, -1, 0))
        cut = part.extrude_cut(model, hole, mm(depth), reverse_direction=reverse)
        area = math.pi * (diameter / 2)**2
        change = -2 * (area if not depth else area - math.pi*5**2) * (depth or 10)
        verify_feature(model, cut, label, change, features)

    def upright_plate():
        upright, n, _ = profile(front, "Tangent upright outline", upright_profile)
        crown = next(row for row in sketches[-1]["geometry_mm"] if "radius_mm" in row)
        tx, ty = crown["start_mm"]
        half_width = abs(tx)
        h = ty - 58
        segment_area = 19**2 * math.acos(h/19) - h*half_width
        area = (41 + half_width)*(ty-10) + segment_area
        verify_feature(model, part.extrude_boss(model, upright, mm(10),
                       direction=not reverse_in_direction(n, (0, 0, -1))),
                       "Upright 10 mm", area*10, features)

    def rear_boss():
        boss, n, _ = profile(rear, "Rear boss profile",
                             circular_profile([(0, 58)], 38, (28, 70, -38)))
        verify_feature(model, part.extrude_boss(model, boss, mm(2),
                       direction=not reverse_in_direction(n, (0, 0, -1))),
                       "Rear circular boss 2 mm", 2*math.pi*19**2, features)

    def upright_bore():
        bore, n, _ = profile(front, "Upright bore layout",
                             circular_profile([(0, 58)], 22, (22, 67, -28)))
        verify_feature(model, part.extrude_cut_through_all(model, bore,
                       reverse_direction=reverse_in_direction(n, (0, 0, -1))),
                       "Upright through hole D22", -12*math.pi*11**2, features)

    def center_rib():
        rib, _, _ = profile("Right Plane", "Triangle rib outline", rib_profile)
        verify_feature(model, part.extrude_boss_midplane(model, rib, mm(10)),
                       "Center rib 10 mm", .5*28*30*10, features)

    return {
        "base": base_plate,
        "round-corners": front_corners,
        "reference-planes": reference_planes,
        "mounting-holes": lambda: mounting_cut(10, 0, "Mounting holes 2 x D10"),
        "counterbores": lambda: mounting_cut(20, 2, "Counterbores 2 x D20 x 2"),
        "upright": upright_plate,
        "rear-boss": rear_boss,
        "upright-bore": upright_bore,
        "center-rib": center_rib,
    }

def finish_model(session, model, target, sketches, features):
    measures = collect_geometry_measurements(model)
    if measures["errors"]:
        raise RuntimeError(measures["errors"])
    expected = [(10, (x, 0, -14), 1, 8) for x in (-27, 27)]
    expected += [(20, (x, 0, -14), 1, 2) for x in (-27, 27)]
    expected += [(22, (0, 58, 0), 2, 12)]
    for diameter, center, axis, length in expected:
        assert any(abs(h["diameter_mm"]-diameter) < .001
                   and abs(h["axial_length_mm"]-length) < .001
                   and abs(h["axis"][axis]) > .999
                   and all(abs(h["position_mm"][i]-center[i]) < .001
                           for i in range(3) if i != axis)
                   for h in measures["holes"]), measures
    body = read(model, "GetBodies2", 0, False)[0]
    box_mm = [round(x*1000, 6) for x in read(body, "GetBodyBox")]
    assert all(abs(a-b) < .01 for a,b in zip(box_mm, [-41, 0, -40, 41, 77, 0])), box_mm
    assert all(int(read(part._feature_object(model, row["name"]), "GetErrorCode")) == 0
               for row in features + sketches)

    set_standard_view(model, "isometric")
    model.ViewZoomtofit2()
    if target.exists():
        raise RuntimeError(f"Output already exists: {target}")
    basename = target.stem
    _, report_path = run_review(
        model, str(target.parent / f"{basename}_review"), basename=basename,
        views=("isometric", "front", "top", "right"),
        expected_outputs=[read(model, "GetPathName")])
    set_standard_view(model, "isometric")
    model.ViewZoomtofit2()
    save_part(session, model, target)
    evidence = {"part": str(target), "box_xyz_mm": box_mm, "sketches": sketches,
                "features": features, "measurements": measures, "review": str(report_path),
                "assumption": "Rear 2 mm boss is a full diameter 38 circle concentric with D22."}
    path = target.parent / f"{basename}_evidence.json"
    path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"part": str(target), "evidence": str(path), "box_xyz_mm": box_mm}))


def save_part(session, model, path):
    current = Path(read(model, "GetPathName"))
    if not session.save(model, None if current == path else str(path)):
        raise RuntimeError(f"Native save failed: {path}")
    saved_path = Path(read(model, "GetPathName"))
    if saved_path != path:
        raise RuntimeError(f"SolidWorks saved the document at {saved_path}, expected {path}")
    if not path.is_file() or not path.stat().st_size:
        raise RuntimeError(f"Native save did not produce a nonempty file: {path}")


def validate_checkpoint(model, sketches, features):
    if not model.ForceRebuild3(False):
        raise RuntimeError("Checkpoint rebuild failed")
    for row in features + sketches:
        feature = part._feature_object(model, row["name"])
        if int(read(feature, "GetErrorCode")):
            raise RuntimeError(f"Checkpoint feature has errors: {row['name']}")
        if "geometry_mm" in row:
            native_sketch = read(feature, "GetSpecificFeature2")
            if (not _sketch_status(native_sketch)["fully_defined"]
                    or not same_geometry(row["geometry_mm"], _sketch_geometry(native_sketch))):
                raise RuntimeError(f"Checkpoint sketch changed: {row['name']}")
    bodies = read(model, "GetBodies2", 0, False) or ()
    if len(bodies) != 1:
        raise RuntimeError(f"Checkpoint contains {len(bodies)} solid bodies")
    volume = float(read(bodies[0], "GetMassProperties", 1.0)[3]) * 1e9
    if not math.isclose(volume, features[-1]["volume_mm3"], abs_tol=.03):
        raise RuntimeError("Checkpoint solid volume does not match the saved stage")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Path of the finished SLDPRT")
    parser.add_argument("--resume", type=Path, help="Checkpoint JSON path printed by a previous run")
    args = parser.parse_args(argv)

    latest = args.resume.resolve() if args.resume else None
    state = json.loads(latest.read_text(encoding="utf-8")) if latest else {}
    if latest and state["version"] != 1:
        raise RuntimeError(f"Unsupported checkpoint version: {latest}")
    target = (args.output or Path(state.get("target", TARGET))).resolve()
    if target.suffix.lower() != ".sldprt":
        parser.error("--output must have the .SLDPRT extension")
    if target.exists():
        raise RuntimeError(f"Output already exists: {target}. Choose a new --output path.")

    checkpoint_root = target.parent / f"{target.stem}_checkpoints"
    checkpoint_root.mkdir(parents=True, exist_ok=True)
    run_dir = Path(mkdtemp(prefix="run-", dir=checkpoint_root))
    working_part = run_dir / f"{run_dir.name}-working.SLDPRT"
    session = SolidWorksSession(version=2025, visible=True)
    model = None
    current_stage = "open checkpoint" if latest else "new part"
    sketches, features = state.get("sketches", []), state.get("features", [])
    completed = state.get("completed", [])
    try:
        if latest:
            shutil.copyfile(latest.with_suffix(".SLDPRT"), working_part)
            model = session.open(str(working_part), silent=True)
        else:
            model = session.new_part()
        active = session.active_doc
        expected_path = str(working_part) if latest else ""
        if (int(read(active, "GetType")) != 1
                or read(active, "GetTitle") != read(model, "GetTitle")
                or (read(active, "GetPathName") or "") != expected_path):
            raise RuntimeError("Active document is not the working part")

        stages = build_stages(session, model, sketches, features)
        if completed != list(stages)[:len(completed)] or (latest and not completed):
            raise RuntimeError(f"Checkpoint stage sequence is invalid: {completed}")
        if latest:
            validate_checkpoint(model, sketches, features)
            print(f"Resumed after {completed[-1]} from {latest}", flush=True)
        for current_stage, execute in list(stages.items())[len(completed):]:
            active = session.active_doc
            if (read(active, "GetTitle") != read(model, "GetTitle")
                    or read(active, "GetPathName") != read(model, "GetPathName")):
                raise RuntimeError("Activate the working part before continuing modeling")
            execute()
            save_part(session, model, working_part)
            completed.append(current_stage)
            checkpoint = run_dir / f"{len(completed):02d}-{current_stage}.json"
            shutil.copyfile(working_part, checkpoint.with_suffix(".SLDPRT"))
            pending = checkpoint.with_suffix(".json.tmp")
            pending.write_text(json.dumps({
                "version": 1, "target": str(target), "completed": completed,
                "features": features, "sketches": sketches,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            pending.replace(checkpoint)
            latest = checkpoint
            print(f"Checkpoint: {latest}", flush=True)

        current_stage = "final verification and save"
        finish_model(session, model, target, sketches, features)
    except (Exception, KeyboardInterrupt):
        print(f"Stopped at {current_stage}.", file=sys.stderr, flush=True)
        if latest:
            print(f'Resume: python "{Path(__file__).resolve()}" --resume "{latest}"',
                  file=sys.stderr, flush=True)
        if model is not None:
            session.close(model)
        raise


if __name__ == "__main__":
    main()
