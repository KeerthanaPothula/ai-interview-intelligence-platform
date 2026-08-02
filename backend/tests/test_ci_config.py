"""Phase 4 — structural validation of the GitHub Actions workflow files.

Catches a malformed workflow (bad YAML, a renamed/missing job) at test time
rather than discovering it only after a push fails in Actions.
"""

from __future__ import annotations

from pathlib import Path

import yaml

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
