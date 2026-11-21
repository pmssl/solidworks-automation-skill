"""Exercise separate Python processes against one disposable native Part."""

from __future__ import annotations

from multiprocessing import get_context
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.sw_connect import get_com_member, win32com_client
from scripts.sw_skill_session import run_action


def main() -> None:
    sw = win32com_client.GetActiveObject("SldWorks.Application")
    original = get_com_member(sw, "ActiveDoc")
    original_title = get_com_member(original, "GetTitle") if original is not None else None
    with TemporaryDirectory() as cwd, get_context("spawn").Pool(1, maxtasksperchild=1) as pool:
        def run(action, session_id=None, **params):
            pending = pool.apply_async(run_action, (action, params, session_id))
            return pending.get(timeout=45)

        title = None
        token = None
        cut_tokens = []
        unrelated_title = None
        try:
            title = run("new_part")["document"]
            token = run("begin", expected_document_title=title,
                        plane_name="Front Plane")["session_id"]
            run("rectangle", token, width_mm=50, height_mm=30)
            run("dimension", token, axis="horizontal", value_mm=50)
            run("dimension", token, axis="vertical", value_mm=30)
            if not run("status", token)["fully_defined"]:
                run("auto_define", token)
            assert run("finish", token)["fully_defined"]
            unrelated_title = run("new_part")["document"]
            try:
                run("extrude", token, depth_mm=10)
            except RuntimeError as exc:
                assert "Active Part changed" in str(exc), exc
            else:
                raise AssertionError("Session accepted a different Part")
            sw.CloseDoc(unrelated_title)
            unrelated_title = None
            sw.ActivateDoc2(title, False, 0)
            run("extrude", token, depth_mm=10)
            assert run("model_state", token)["solid_body_count"] == 1
            plane = run("offset_plane", expected_document_title=title,
                        base_plane_name="Front Plane", offset_mm=10)
            for plane_name, center, radius, direction, depth in (
                ("Front Plane", -10, 2, "along_normal", 0),
                (plane["feature"], 10, 3, "against_normal", 4),
            ):
                cut_token = run("begin", expected_document_title=title,
                                plane_name=plane_name)["session_id"]
                cut_tokens.append(cut_token)
                run("circle", cut_token, center_x_mm=center, center_y_mm=0, radius_mm=radius)
                run("auto_define", cut_token)
                run("finish", cut_token)
                sketch_plane = run("sketch_plane", cut_token)
                assert sketch_plane["normal_xyz"] == [0, 0, 1], sketch_plane
                assert abs(sketch_plane["offset_mm"] - (10 if depth else 0)) < 0.01, sketch_plane
                cut = run("extrude", cut_token, depth_mm=depth, cut=True, cut_direction=direction)
                assert cut["solid_body_count"] == 1 and cut["through_all"] == (depth == 0), cut
            measurement = run("measure_geometry")
            assert not measurement["errors"], measurement
            for diameter, length in ((4, 10), (6, 4)):
                assert any(
                    abs(hole["diameter_mm"] - diameter) < 0.01
                    and abs(hole["axial_length_mm"] - length) < 0.01
                    for hole in measurement["holes"]
                ), measurement
            target = Path(cwd) / "skill-session-smoke.sldprt"
            saved = run("save_part", expected_document_title=title, path=str(target))
            title = run("document")["document"]
            assert Path(saved["path"]) == target and target.stat().st_size > 0
        finally:
            for cut_token in cut_tokens:
                run("discard_session", cut_token)
            if token:
                run("discard_session", token)
            if unrelated_title:
                sw.CloseDoc(unrelated_title)
            if title:
                sw.QuitDoc(title)
            if original_title:
                sw.ActivateDoc2(original_title, False, 0)
    print("PASS: independent Python processes reused the session, rejected a different Part and saved one native solid")


if __name__ == "__main__":
    main()
