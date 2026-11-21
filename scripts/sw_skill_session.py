"""Run native SolidWorks operations with optional persisted sketch sessions."""

from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile

from .sw_native_parametric import NativeParametric, SketchSession, _com_get, _doc_id, _find_feature


SESSION_DIR = Path(__file__).resolve().parents[1] / ".runtime" / "solidworks-sessions"
SKETCH_ACTIONS = (
    "rectangle", "rectangle_pair", "line", "corner_rectangle", "circle", "arc",
    "polygon", "straight_slot", "spline", "geometry", "dimension", "relation",
    "auto_define", "status", "sketch_plane", "finish", "extrude", "revolve", "sweep", "loft",
)
ACTIONS = ("document", "new_part", "begin", "offset_plane", "model_state", "measure_geometry", "save_part",
           "discard_session", *SKETCH_ACTIONS)
READ_ONLY = {"document", "geometry", "status", "sketch_plane", "model_state", "measure_geometry"}


def session_path(token: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{22}", token):
        raise ValueError("Invalid session_id")
    return SESSION_DIR / f"{token}.json"


def write_state(path: Path, state: dict) -> None:
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                            suffix=".tmp", delete=False) as temporary:
        temp_path = Path(temporary.name)
        try:
            json.dump(state, temporary, ensure_ascii=False)
            temporary.close()
            os.replace(temp_path, path)
        finally:
            temp_path.unlink(missing_ok=True)


def instance_identity(sw) -> dict:
    import win32api
    import win32con
    import win32process

    pid = int(_com_get(sw, "GetProcessID"))
    process = win32api.OpenProcess(win32con.PROCESS_QUERY_INFORMATION, False, pid)
    try:
        created = win32process.GetProcessTimes(process)["CreationTime"]
        return {"pid": pid, "created": created.isoformat()}
    finally:
        process.Close()


def verify_sketch(sw, model, session: SketchSession, reference: dict) -> None:
    from scripts.sw_entity_reference import resolve_persistent_reference

    if _doc_id(model) != (session.title, session.path):
        raise RuntimeError("Active Part changed. Activate the original Part to resume")
    resolved = resolve_persistent_reference(model, reference)
    feature = resolved["entity"]
    if (resolved["error_code"] != 0 or str(feature.Name) != session.sketch_name
            or _com_get(feature, "GetTypeName2") != "ProfileFeature"):
        raise RuntimeError("Saved sketch reference no longer matches the original feature")
    active = model.SketchManager.ActiveSketch
    if session.open:
        sketch = _com_get(feature, "GetSpecificFeature2")
        if active is None or sketch is None or int(sw.IsSame(active, sketch)) != 1:
            raise RuntimeError("The original sketch is no longer being edited")
    elif active is not None:
        raise RuntimeError("Exit the active sketch before using this finished session")


def save_part(model, expected_document_title: str, path: str | None = None) -> dict:
    from scripts.sw_connect import save_document

    title, current = _doc_id(model)
    if expected_document_title != title or model.SketchManager.ActiveSketch is not None:
        raise RuntimeError("Save requires the expected active Part with sketch editing closed")
    target = Path(path or current)
    if not target.is_absolute() or target.suffix.lower() != ".sldprt":
        raise ValueError("Provide an absolute .SLDPRT path for an unsaved Part")
    target = target.resolve()
    same_path = bool(current) and target == Path(current).resolve()
    if not same_path and target.exists():
        raise FileExistsError(f"Save As would overwrite {target}")
    if not save_document(model, None if same_path else str(target)):
        raise RuntimeError("SolidWorks did not save the Part")
    if Path(_doc_id(model)[1]).resolve() != target or not target.is_file() or not target.stat().st_size:
        raise RuntimeError("Saved Part did not match the expected path and file size")
    return {"status": "ok", "path": str(target)}


def _connect_active():
    from .sw_connect import _read_active_document, win32com_client

    try:
        sw = win32com_client.GetActiveObject("SldWorks.Application")
    except Exception as exc:
        raise RuntimeError(
            "Cannot attach to running SolidWorks. Start it in the same Windows session"
        ) from exc
    return sw, _read_active_document(sw)


def run_action(action: str, params: dict | None = None, token: str | None = None,
               connect=_connect_active) -> dict:
    """Run one operation and return its result, raising on failure."""
    from .sw_connect import _LaunchGuard

    if action not in ACTIONS:
        raise ValueError(f"Unknown SolidWorks action: {action}")
    if params is None:
        params = {}
    elif not isinstance(params, dict):
        raise TypeError("Parameters must be a dict")
    if token is None and action in (*SKETCH_ACTIONS, "discard_session"):
        raise ValueError("This action requires a session_id")
    if token is not None:
        if action not in (*SKETCH_ACTIONS, "model_state", "discard_session"):
            raise ValueError("This action does not accept a session_id")
        path = session_path(token)

    with _LaunchGuard("SolidWorksAutomation.Skill.Session"):
        if action == "discard_session":
            if params:
                raise ValueError("discard_session takes no parameters")
            path.unlink()
            return {"status": "ok", "session_id": token}
        return _run_action(action, params, token, connect)


def _run_action(action: str, params: dict, token: str | None, connect) -> dict:
    from scripts import sw_part
    from scripts.sw_connect import new_document
    from scripts.sw_entity_reference import create_persistent_reference

    sw, model = connect()
    if action == "document":
        if model is None:
            return {"status": "ok", "document": None}
        title, path = _doc_id(model)
        return {"status": "ok", "document": title, "path": path,
                "document_type": int(_com_get(model, "GetType"))}
    if action == "new_part":
        created = new_document(sw, "part", **params)
        title, path = _doc_id(created)
        return {"status": "ok", "document": title, "path": path}

    engine = NativeParametric(lambda: (sw, model), lambda: sw_part)
    model = engine._part()
    if action == "measure_geometry":
        from scripts.sw_review import collect_geometry_measurements

        if params:
            raise ValueError("measure_geometry takes no parameters")
        return {"status": "ok", "document": _doc_id(model)[0],
                **collect_geometry_measurements(model)}
    if action not in READ_ONLY and bool(_com_get(model, "IsOpenedReadOnly")):
        raise RuntimeError("Active Part is read-only")
    if action == "save_part":
        return save_part(model, **params)
    if action == "offset_plane" or (action == "model_state" and token is None):
        return getattr(engine, action)(**params)
    if action == "begin":
        identity = instance_identity(sw)
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        result = engine.begin(**params)
        session = engine.session
        try:
            feature = _find_feature(model, session.sketch_name)
            reference = create_persistent_reference(model, feature).to_dict()
            verify_sketch(sw, model, session, reference)
            write_state(session_path(session.token), {
                "version": 1, "instance": identity, "sketch_reference": reference,
                "session": asdict(session),
            })
        except Exception as exc:
            raise RuntimeError(f"Could not persist the new sketch session. Inspect the active sketch: {exc}") from exc
        return result

    path = session_path(token)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError("No matching skill session. Start a sketch first") from exc
    if state["version"] != 1 or state["instance"] != instance_identity(sw):
        raise RuntimeError("Session belongs to a different SolidWorks process or session format")
    session = SketchSession(**state["session"])
    if session.token != token:
        raise RuntimeError("Saved session_id does not match the requested session")
    verify_sketch(sw, model, session, state["sketch_reference"])
    engine.session = session
    result = getattr(engine, action)(token, **params)
    if action == "finish":
        state["session"] = asdict(session)
        write_state(path, state)
    return result
