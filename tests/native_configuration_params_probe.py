"""Read-only probe for ConfigurationManager parameter array marshaling."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.sw_connect import connect_solidworks, get_com_member
from scripts.sw_preflight import import_com_dependencies


pythoncom, _win32com, VARIANT = import_com_dependencies()


def main():
    _sw, model = connect_solidworks(wait_seconds=1)
    if model is None:
        raise RuntimeError("no active document")
    manager = get_com_member(model, "ConfigurationManager")
    active = get_com_member(manager, "ActiveConfiguration")
    name = str(get_com_member(active, "Name"))
    count = int(manager.GetConfigurationParamsCount(name))
    attempts = []
    for args in ((name,), (name, None, None)):
        try:
            value = manager.GetConfigurationParams(*args)
            attempts.append({
                "args": len(args), "ok": True,
                "type": type(value).__name__, "repr": repr(value)[:2000],
            })
        except Exception as exc:
            attempts.append({"args": len(args), "ok": False, "error": repr(exc)})
    params = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_VARIANT, None)
    values = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_VARIANT, None)
    try:
        returned = bool(manager.GetConfigurationParams(name, params, values))
        attempts.append({
            "args": "byref_variant", "ok": returned,
            "params_type": type(params.value).__name__, "params": repr(params.value)[:2000],
            "values_type": type(values.value).__name__, "values": repr(values.value)[:2000],
        })
    except Exception as exc:
        attempts.append({"args": "byref_variant", "ok": False, "error": repr(exc)})
    print(json.dumps({
        "status": "ok", "configuration": name, "count": count,
        "attempts": attempts,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
