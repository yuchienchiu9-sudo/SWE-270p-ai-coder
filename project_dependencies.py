# Name: Yu-Chien Chiu
# Student ID: 56176405
# Name: Mars Huang
# Student ID: 79666292
"""Resolve per-project verification dependencies without executing untrusted pip specs.

Generated requirements are DATA, not trusted installer commands. The host maps
approved names to reviewed pinned versions; unknown packages fail closed.
"""

import hashlib
import re
from pathlib import Path

BASE_PACKAGES = frozenset({"pytest", "streamlit"})
# Expand this catalog deliberately after reviewing packages and their dependencies.
APPROVED_EXTRAS = {
    "matplotlib": "matplotlib==3.10.7",
    "pandas": "pandas==2.3.3",
    "numpy": "numpy==2.3.5",
    "plotly": "plotly==6.5.0",
    "altair": "altair==5.5.0",
}
PACKAGE_LINE = re.compile(r"^([A-Za-z][A-Za-z0-9_.-]*)(?:\s*==\s*([0-9]+(?:\.[0-9]+)*))?$")


class DependencyNotApproved(ValueError):
    """A generated project requested an unreviewed or unsupported dependency."""


def resolve_dependencies(run: Path) -> tuple[str, ...]:
    """Return canonical pinned extras from this run's requirements.txt.

    Planner may supply a version, but the sandbox uses only reviewed versions.
    Reject arbitrary pip syntax, URLs, options, relative paths and unknown names.
    """
    requirements = Path(run) / "requirements.txt"
    if requirements.is_symlink():
        raise DependencyNotApproved("Symlinked requirements.txt is not allowed")
    if requirements.exists() and requirements.stat().st_size > 4096:
        raise DependencyNotApproved("requirements.txt exceeds the 4 KiB limit")
    if not requirements.exists():
        return ()  # Backward compatibility with existing tests/older runs.
    requested = set()
    for raw in requirements.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = PACKAGE_LINE.fullmatch(line)
        if not match:
            raise DependencyNotApproved("Unsupported requirement syntax; use approved package names or exact versions")
        name = match.group(1).lower().replace("_", "-").replace(".", "-")
        if name in BASE_PACKAGES:
            pinned_base = {"streamlit": "1.67.0", "pytest": "9.2.0"}
            if match.group(2) and match.group(2) != pinned_base[name]:
                raise DependencyNotApproved(f"Unapproved version for {name!r}")
            continue
        if name not in APPROVED_EXTRAS:
            raise DependencyNotApproved(f"Package {name!r} is not in the approved sandbox catalog")
        if match.group(2) and match.group(2) != APPROVED_EXTRAS[name].split("==")[1]:
            raise DependencyNotApproved(f"Unapproved version for {name!r}")
        requested.add(name)
    return tuple(APPROVED_EXTRAS[name] for name in sorted(requested))


def image_for_dependencies(packages: tuple[str, ...]) -> str:
    if not packages:
        return "ai-coder-test-sandbox:local"
    digest = hashlib.sha256("\n".join(packages).encode("utf-8")).hexdigest()[:16]
    return f"ai-coder-test-sandbox:deps-{digest}"
