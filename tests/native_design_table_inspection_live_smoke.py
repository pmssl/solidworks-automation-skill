"""Read-only live check for native design-table inspection."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import sw_document_data
from scripts.sw_connect import connect_solidworks, get_com_member


def main():
    _sw, model = connect_solidworks(wait_seconds=1)
    if model is None:
        raise RuntimeError("no active SolidWorks document")
    result = sw_document_data.inspect_design_table(model)
    print(json.dumps({
        "status": "ok", "document": str(get_com_member(model, "GetTitle")),
        "saved": False, "design_table": result,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
