"""Validate the native modeling skill without starting SolidWorks."""

import ast
from pathlib import Path

try:
    from .capabilities import load_capabilities
except ImportError:
    from capabilities import load_capabilities


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "SKILL.md", "README.md", "LICENSE", "requirements.txt", "agents/openai.yaml",
    "references/parametric-workflow.md", "references/native-capability-catalog.md",
    "scripts/sw_skill_session.py", "scripts/sw_native_parametric.py",
    "scripts/sw_connect.py", "scripts/sw_preflight.py", "scripts/sw_part.py",
    "scripts/sw_review.py", "scripts/sw_entity_reference.py",
    "scripts/sw_document_data.py", "scripts/sw_hole_features.py",
)


def main():
    missing = [name for name in REQUIRED if not (ROOT / name).is_file()]
    if missing:
        raise SystemExit("Missing skill files: " + ", ".join(missing))
    frontmatter = (ROOT / "SKILL.md").read_text(encoding="utf-8").split("---", 2)
    if len(frontmatter) != 3 or frontmatter[0] or "name: solidworks-automation" not in frontmatter[1]:
        raise SystemExit("Invalid SKILL.md frontmatter")
    files = [path for folder in ("scripts", "tests") for path in (ROOT / folder).glob("*.py")]
    for path in files:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    capabilities = load_capabilities()
    print(f"Validated {len(files)} Python files and {len(capabilities['capabilities'])} capability groups.")


if __name__ == "__main__":
    main()
