"""Blocking vulnerability audit of the production (runtime) dependencies.

Run from ``backend/`` — locally and in CI it is the same command::

    python scripts/audit_dependencies.py

What it does
------------
Runs ``pip-audit`` against ``requirements.txt`` (runtime only — dev tooling lives
in ``requirements-dev.txt`` and is deliberately not audited here), resolving
transitive dependencies exactly as ``pip install`` would, and exits non-zero on:

* any advisory that is not listed in ``pip-audit-exceptions.txt``, and
* any dependency that could not be audited (``--strict``) — so a package can
  never silently drop out of coverage.

Every exception in ``pip-audit-exceptions.txt`` carries a written reason and a
"Remove when" condition; see SECURITY.md "Dependency Security".

The ``+cpu`` local version
--------------------------
``torch==X+cpu`` (the CPU-only wheel from PyTorch's own index) does not exist on
PyPI, so ``pip-audit`` cannot look it up and would skip it. It is the same
upstream release as ``torch==X``, so we audit that version instead and drop the
extra-index line. Without this the largest dependency would be unaudited.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REQUIREMENTS = BACKEND_DIR / "requirements.txt"
EXCEPTIONS = BACKEND_DIR / "pip-audit-exceptions.txt"

_ADVISORY_ID = re.compile(r"^(?:PYSEC|GHSA|CVE)-[0-9A-Za-z-]+$")


def auditable_requirements(text: str) -> str:
    """Return `text` rewritten so every pin can be looked up on PyPI."""
    lines = [
        re.sub(r"\+cpu\b", "", line)
        for line in text.splitlines()
        if not line.lstrip().startswith("--extra-index-url")
    ]
    return "\n".join(lines) + "\n"


def parse_exceptions(text: str) -> list[str]:
    """Return the advisory IDs listed in an exceptions file (``#`` = comment)."""
    ids: list[str] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if not _ADVISORY_ID.match(line):
            raise ValueError(f"Malformed advisory ID in {EXCEPTIONS.name}: {raw!r}")
        ids.append(line)
    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate advisory IDs in {EXCEPTIONS.name}")
    return ids


def build_command(requirements_file: Path, exception_ids: list[str]) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "pip_audit",
        "-r",
        str(requirements_file),
        "--strict",
        "--progress-spinner",
        "off",
    ]
    for advisory_id in exception_ids:
        command += ["--ignore-vuln", advisory_id]
    return command


def main() -> int:
    exception_ids = parse_exceptions(EXCEPTIONS.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        audit_file = Path(tmp) / "requirements-audit.txt"
        audit_file.write_text(
            auditable_requirements(REQUIREMENTS.read_text(encoding="utf-8")),
            encoding="utf-8",
        )
        print(
            f"Auditing {REQUIREMENTS.name} (runtime deps + transitive) with "
            f"{len(exception_ids)} documented exception(s) from {EXCEPTIONS.name}",
            flush=True,
        )
        return subprocess.run(build_command(audit_file, exception_ids)).returncode


if __name__ == "__main__":
    sys.exit(main())
