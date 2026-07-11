"""Tests for the built-in scanner fingerprint recorded in every run."""
from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timezone
from pathlib import Path

from agentcam import __version__


def test_release_version_matches_product_closure_release():
    assert __version__ == "0.5.0"


def test_release_workflow_uses_oidc_and_releases_only_after_pypi():
    workflow = (
        Path(__file__).resolve().parents[2]
        / ".github" / "workflows" / "agentcam-publish.yml"
    ).read_text(encoding="utf-8")

    assert "tags: ['agentcam-v*']" in workflow
    assert "id-token: write" in workflow
    assert "pypa/gh-action-pypi-publish@release/v1" in workflow
    assert "needs: [build, publish-pypi]" in workflow
    assert "gh release create" in workflow
    assert "python -m build" in workflow
from agentcam.models import (
    ExitDetail,
    GitState,
    ReportBundle,
    RulesetProvenance,
    RunManifest,
    RunPaths,
    capture_for_wrap_pipe,
)
from agentcam.report import render_report, serialize_manifest
from agentcam.scanner import builtin_ruleset_sha256, provenance_for_builtin_ruleset


def _empty_state() -> GitState:
    return GitState(
        head="abc",
        branch="main",
        is_detached_head=False,
        porcelain_raw=b"",
        diff_stat="",
        diff_stat_cached="",
        diff_name_status="",
        diff_name_status_cached="",
        changed_files=[],
    )


def _manifest(tmp_path: Path) -> RunManifest:
    base = tmp_path / ".git" / "agentcam" / "runs" / "test"
    base.mkdir(parents=True, exist_ok=True)
    paths = RunPaths(
        run_dir=str(base),
        manifest_json=str(base / "manifest.json"),
        report_md=str(base / "AGENT_RUN_REPORT.md"),
        stdout_raw=str(base / "stdout.log"),
        stderr_raw=str(base / "stderr.log"),
        stdout_redacted=str(base / "stdout.redacted.log"),
        stderr_redacted=str(base / "stderr.redacted.log"),
    )
    return RunManifest(
        schema_version="0.1",
        run_id="test",
        started_at=datetime(2026, 5, 22, tzinfo=timezone.utc),
        ended_at=datetime(2026, 5, 22, 0, 0, 1, tzinfo=timezone.utc),
        duration_seconds=1.0,
        cwd=str(tmp_path),
        git_root=str(tmp_path),
        git_dir=str(tmp_path / ".git"),
        branch="main",
        is_detached_head=False,
        head_before="abc",
        head_after="abc",
        pre_existing_op=None,
        pre_run_dirty=False,
        command_argv_raw=["python", "-c", "pass"],
        command_argv_redacted=["python", "-c", "pass"],
        exit_detail=ExitDetail(
            wrapper_exit=0,
            raw_returncode=0,
            raw_returncode_hex=None,
            platform="linux",
            interpretation="success",
            interpretation_source="known_table",
        ),
        shell_used=False,
        terminal_forward_degraded=False,
        platform="linux",
        agentcam_version="0.1.0",
        paths=paths,
        capture=capture_for_wrap_pipe(empty_run_policy="auto_delete_clean_no_diff"),
        ruleset=provenance_for_builtin_ruleset(),
    )


def test_builtin_fingerprint_is_deterministic_sha256():
    first = builtin_ruleset_sha256()
    assert first == builtin_ruleset_sha256()
    assert first.startswith("sha256:")
    assert len(first.removeprefix("sha256:")) == 64
    int(first.removeprefix("sha256:"), 16)


def test_provenance_contains_only_the_ruleset_that_exists():
    assert [field.name for field in dataclasses.fields(RulesetProvenance)] == [
        "builtin_ruleset_id",
        "builtin_ruleset_version",
        "rules_sha256",
    ]
    provenance = provenance_for_builtin_ruleset()
    assert provenance.builtin_ruleset_id == "agentcam-default"
    assert provenance.builtin_ruleset_version == __version__
    assert provenance.rules_sha256 == builtin_ruleset_sha256()


def test_manifest_requires_capture_and_ruleset():
    fields = {field.name: field for field in dataclasses.fields(RunManifest)}
    assert fields["capture"].default is dataclasses.MISSING
    assert fields["ruleset"].default is dataclasses.MISSING


def test_manifest_serializes_compact_ruleset(tmp_path: Path):
    data = json.loads(json.dumps(serialize_manifest(_manifest(tmp_path))))
    assert set(data["ruleset"]) == {
        "builtin_ruleset_id",
        "builtin_ruleset_version",
        "rules_sha256",
    }
    assert data["ruleset"]["rules_sha256"] == builtin_ruleset_sha256()


def test_report_renders_builtin_ruleset(tmp_path: Path):
    state = _empty_state()
    report = render_report(
        ReportBundle(manifest=_manifest(tmp_path), state_before=state, state_after=state)
    )
    assert "## Scanner Ruleset" in report
    assert "agentcam-default" in report
    assert builtin_ruleset_sha256() in report
