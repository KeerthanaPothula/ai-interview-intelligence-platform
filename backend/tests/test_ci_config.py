"""Phase 4 — structural validation of the GitHub Actions workflow files.

Catches a malformed workflow (bad YAML, a renamed/missing job) at test time
rather than discovering it only after a push fails in Actions.
"""

from __future__ import annotations

import json
import re
from importlib import metadata
from pathlib import Path

import pytest
import yaml
from packaging.requirements import Requirement
from packaging.version import Version

from scripts import audit_dependencies

WORKFLOWS_DIR = Path(__file__).resolve().parents[2] / ".github" / "workflows"

# PyYAML follows the YAML 1.1 spec, which resolves an unquoted `on` mapping
# key to the boolean True (the "Norway problem") rather than the string
# "on". GitHub's own workflow parser does not do this — it is purely a
# PyYAML behaviour we have to account for when reading the file back here.
ON_KEY = True


def _load(filename: str) -> dict:
    path = WORKFLOWS_DIR / filename
    assert path.is_file(), f"{path} does not exist"
    with path.open() as fh:
        return yaml.safe_load(fh)


class TestCiWorkflow:
    def test_ci_workflow_parses_as_valid_yaml(self):
        workflow = _load("ci.yml")
        assert isinstance(workflow, dict)

    def test_ci_workflow_triggers_on_push_and_pull_request(self):
        workflow = _load("ci.yml")
        triggers = workflow[ON_KEY]
        assert "push" in triggers
        assert "pull_request" in triggers

    def test_ci_workflow_has_required_jobs(self):
        jobs = _load("ci.yml")["jobs"]
        for job in (
            "backend-lint",
            "frontend-lint",
            "backend-test",
            "frontend-test",
            "frontend-build",
            "docker-build",
        ):
            assert job in jobs, f"expected job {job!r} in ci.yml"

    def test_backend_test_job_runs_pytest_with_coverage(self):
        jobs = _load("ci.yml")["jobs"]
        steps = jobs["backend-test"]["steps"]
        run_commands = [s.get("run", "") for s in steps]
        assert any("pytest" in cmd and "--cov" in cmd for cmd in run_commands)

    def test_backend_test_job_gates_on_a_coverage_floor(self):
        jobs = _load("ci.yml")["jobs"]
        steps = jobs["backend-test"]["steps"]
        run_commands = [s.get("run", "") for s in steps]
        assert any("--cov-fail-under" in cmd for cmd in run_commands), (
            "coverage gating was removed from ci.yml — a coverage regression "
            "would no longer fail the build"
        )


class TestSecurityWorkflow:
    def test_security_workflow_parses_as_valid_yaml(self):
        workflow = _load("security.yml")
        assert isinstance(workflow, dict)

    def test_security_workflow_has_required_jobs(self):
        jobs = _load("security.yml")["jobs"]
        for job in ("pip-audit", "npm-audit", "secrets-scan", "codeql"):
            assert job in jobs, f"expected job {job!r} in security.yml"

    def test_codeql_job_declares_security_events_permission(self):
        jobs = _load("security.yml")["jobs"]
        assert jobs["codeql"]["permissions"]["security-events"] == "write"


# ---------------------------------------------------------------------------
# Dependency audits are a BLOCKING gate — guard against quietly weakening them
# ---------------------------------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"
_DEV_ONLY_PACKAGES = ("pytest", "pytest-cov", "black", "ruff", "pip-audit", "pyyaml")


def _pinned_names(path: Path) -> set[str]:
    names = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line and not line.startswith("-"):
            names.add(re.split(r"[=<>!~\[ ]", line, maxsplit=1)[0].lower())
    return names


class TestDependencyAuditGate:
    def _audit_job(self, name: str) -> dict:
        return _load("security.yml")["jobs"][name]

    def test_audit_jobs_are_not_job_level_non_blocking(self):
        for name in ("pip-audit", "npm-audit"):
            assert "continue-on-error" not in self._audit_job(name), (
                f"{name} must fail the workflow — job-level continue-on-error "
                "turns the audit back into a report nobody has to act on"
            )

    def test_only_the_named_dev_tooling_steps_may_fail(self):
        for name in ("pip-audit", "npm-audit"):
            tolerated = [
                step
                for step in self._audit_job(name)["steps"]
                if step.get("continue-on-error")
            ]
            assert len(tolerated) == 1, f"{name}: exactly one informational step"
            assert "dev" in tolerated[0]["name"].lower()
            assert "informational" in tolerated[0]["name"].lower()

    def test_no_audit_command_swallows_its_exit_code(self):
        text = (WORKFLOWS_DIR / "security.yml").read_text(encoding="utf-8")
        assert "|| true" not in text and "||true" not in text
        assert "|| exit 0" not in text

    def test_python_gate_audits_runtime_requirements_via_the_strict_runner(self):
        commands = [s.get("run", "") for s in self._audit_job("pip-audit")["steps"]]
        assert "python scripts/audit_dependencies.py" in commands
        # An un-auditable package must fail the run, not silently vanish.
        command = audit_dependencies.build_command(Path("reqs.txt"), [])
        assert "--strict" in command
        # Production audit = runtime requirements only, never the dev file.
        assert audit_dependencies.REQUIREMENTS == BACKEND_DIR / "requirements.txt"

    def test_node_gate_runs_the_exception_checked_production_audit(self):
        commands = [s.get("run", "") for s in self._audit_job("npm-audit")["steps"]]
        assert "npm run audit" in commands
        scripts = json.loads((FRONTEND_DIR / "package.json").read_text())["scripts"]
        assert scripts["audit"] == "node scripts/audit-prod.mjs"

    def test_audits_also_run_on_a_schedule(self):
        assert "schedule" in _load("security.yml")[ON_KEY]

    def test_ci_installs_dev_requirements_for_the_test_job(self):
        steps = _load("ci.yml")["jobs"]["backend-test"]["steps"]
        commands = " ".join(s.get("run", "") for s in steps)
        assert "-r requirements-dev.txt" in commands


class TestRequirementsSplit:
    def test_runtime_requirements_contain_no_dev_tooling(self):
        leaked = _pinned_names(BACKEND_DIR / "requirements.txt") & set(
            _DEV_ONLY_PACKAGES
        )
        assert not leaked, (
            f"{sorted(leaked)} belong in requirements-dev.txt: anything in "
            "requirements.txt is shipped in the image and audited as production"
        )

    def test_dev_requirements_extend_and_hold_the_tooling(self):
        dev = BACKEND_DIR / "requirements-dev.txt"
        assert "-r requirements.txt" in dev.read_text(encoding="utf-8")
        assert set(_DEV_ONLY_PACKAGES) <= _pinned_names(dev)

    def test_httpx_stays_a_runtime_dependency(self):
        # app/core/ai_reliability.py imports it.
        assert "httpx" in _pinned_names(BACKEND_DIR / "requirements.txt")


class TestPipAuditExceptions:
    def _text(self) -> str:
        return (BACKEND_DIR / "pip-audit-exceptions.txt").read_text(encoding="utf-8")

    def test_file_parses_with_no_duplicates(self):
        ids = audit_dependencies.parse_exceptions(self._text())
        assert ids, "an empty exceptions file means the gate has nothing to triage"

    def test_every_block_states_its_reason_and_removal_condition(self):
        blocks = re.split(r"\n(?=# --- )", self._text())[1:]
        assert blocks
        for block in blocks:
            header = block.splitlines()[0]
            assert "Why not blocking:" in block, f"{header}: no reason"
            assert "Remove when:" in block, f"{header}: no removal condition"
            assert "Category:" in block, f"{header}: no category"
            assert re.search(r"^(?:PYSEC|GHSA|CVE)-", block, re.M), f"{header}: no IDs"

    def test_every_id_sits_inside_a_documented_block(self):
        first_block = self._text().index("# --- ")
        assert not audit_dependencies.parse_exceptions(self._text()[:first_block])

    def test_malformed_and_duplicate_ids_are_rejected(self):
        with pytest.raises(ValueError):
            audit_dependencies.parse_exceptions("not-an-advisory\n")
        with pytest.raises(ValueError):
            audit_dependencies.parse_exceptions("PYSEC-2026-1\nPYSEC-2026-1\n")


class TestAuditRunner:
    def test_cpu_local_version_is_rewritten_so_torch_is_auditable(self):
        text = "torch==2.6.0+cpu\n--extra-index-url https://download.pytorch.org/whl/cpu\nfastapi==0.1\n"
        assert audit_dependencies.auditable_requirements(text) == (
            "torch==2.6.0\nfastapi==0.1\n"
        )

    def test_command_is_strict_and_ignores_only_the_listed_ids(self):
        cmd = audit_dependencies.build_command(
            Path("reqs.txt"), ["PYSEC-1-1", "GHSA-a-b-c"]
        )
        assert "--strict" in cmd
        ignored = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "--ignore-vuln"]
        assert ignored == ["PYSEC-1-1", "GHSA-a-b-c"]
        assert "--no-deps" not in cmd  # transitive dependencies must be audited too


class TestStarletteSecurityPin:
    """Starlette parses every upload and login form. 0.47.2 fixed PYSEC-2026-1941
    (multipart parsing blocking the event loop); a bare fastapi bump would NOT
    upgrade an already-installed Starlette, so the pin is explicit and guarded."""

    MINIMUM = Version("0.47.2")

    def _pins(self) -> dict[str, Version]:
        pins = {}
        for line in (BACKEND_DIR / "requirements.txt").read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            if line.startswith(("fastapi==", "starlette==")):
                name, version = line.split("==")
                pins[name] = Version(version)
        return pins

    def test_requirements_pin_a_patched_starlette(self):
        pins = self._pins()
        assert pins["starlette"] >= self.MINIMUM

    def test_pinned_starlette_is_inside_the_pinned_fastapi_range(self):
        pins = self._pins()
        fastapi_requirements = metadata.requires("fastapi")
        ranges = [
            Requirement(r)
            for r in fastapi_requirements
            if r.lower().startswith("starlette")
        ]
        assert ranges, "installed fastapi no longer declares a starlette range"
        assert pins["fastapi"] == Version(metadata.version("fastapi"))
        assert all(r.specifier.contains(pins["starlette"]) for r in ranges)

    def test_environment_runs_the_pinned_patched_starlette(self):
        installed = Version(metadata.version("starlette"))
        assert installed >= self.MINIMUM, (
            f"starlette {installed} is installed but requirements.txt pins "
            f"{self._pins()['starlette']}; run pip install -r requirements-dev.txt"
        )
        assert installed == self._pins()["starlette"]

    def test_resolved_advisory_is_not_kept_as_an_exception(self):
        # PYSEC-2026-1941 is fixed by the pin above. Re-listing it would hide a
        # regression if someone later downgrades Starlette.
        ids = audit_dependencies.parse_exceptions(
            (BACKEND_DIR / "pip-audit-exceptions.txt").read_text(encoding="utf-8")
        )
        assert "PYSEC-2026-1941" not in ids
