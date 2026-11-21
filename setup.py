from pathlib import Path
import shutil
import sys

from setuptools import setup
from setuptools.command.install import install


ROOT = Path(__file__).resolve().parent


class PostInstallCommand(install):
    def run(self):
        super().run()
        items = (
            "scripts", "references", "subskills", "agents", "capabilities.yaml",
            "SKILL.md", "README.md", "requirements.txt",
        )
        for client in (".claude", ".codex"):
            target = Path.home() / client / "skills" / "solidworks-automation"
            try:
                target.mkdir(parents=True, exist_ok=True)
                for name in items:
                    source = ROOT / name
                    if source.is_dir():
                        shutil.copytree(source, target / name, dirs_exist_ok=True,
                                        ignore=shutil.ignore_patterns("__pycache__"))
                    else:
                        shutil.copy2(source, target / name)
            except OSError as exc:
                print(f"Could not install skill at {target}: {exc}", file=sys.stderr)


setup(
    name="solidworks-automation",
    version="1.2.0",
    author="wzyn20051216",
    description="Python automation toolkit for SolidWorks API",
    long_description=(ROOT / "README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    url="https://github.com/pmssl/solidworks-automation-skill",
    license="MIT",
    packages=["solidworks_automation"],
    package_dir={"solidworks_automation": "scripts"},
    cmdclass={"install": PostInstallCommand},
    install_requires=["pywin32>=305", "comtypes>=1.2.0"],
    python_requires=">=3.10",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: Microsoft :: Windows",
    ],
    keywords="solidworks automation cad api",
)
