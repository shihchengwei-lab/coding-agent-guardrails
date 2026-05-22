"""Tests for the capture-visibility metadata (Feature 2 / design.md #28).

Two angles:
 - factory functions produce the right enum values per mode
 - serialize_manifest + render_report flow the metadata into JSON + Markdown
   without breaking the legacy ``capture=None`` path
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from agentcam.models import (
    CaptureCapability,
    ChangedFile,
    ExitDetail,
    GitState,
    ReportBundle,
    RunManifest,
    RunPaths,
    capture_for_claude_hook,
    capture_for_wrap_pipe,
)
from agentcam.report import render_report, serialize_manifest, write_manifest


# ---------------------------------------------------------------------------
# Builders (mirroring tests/test_report.py)
# ---------------------------------------------------------------------------

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
        diff_check="",
        diff_check_cached="",
        pre_existing_op=None,
        changed_files=[],
    )


def _paths(tmp_path: Path) -> RunPaths:
    base = tmp_path / ".git" / "agentcam" / "runs" / "20260522-000000-001-test"
    base.mkdir(parents=True, exist_ok=True)
    return RunPaths(
        run_dir=str(base),
        manifest_json=str(base / "manifest.json"),
        report_md=str(base / "AGENT_RUN_REPORT.md"),
        stdout_raw=str(base / "stdout.log"),
        stderr_raw=str(base / "stderr.log"),
        stdout_redacted=str(base / "stdout.redacted.log"),
        stderr_redacted=str(base / "stderr.redacted.log"),
    )


def _manifest(tmp_path: Path, *, capture: CaptureCapability | None) -> RunManifest:
    ed = ExitDetail(
        wrapper_exit=0,
        raw_returncode=0,
        raw_returncode_hex=None,
        platform="linux",
        interpretation="success",
        interpretation_source="known_table",
    )
    return RunManifest(
        schema_version="0.1",
        run_id="20260522-000000-001-test",
        started_at=datetime(2026, 5, 22, 0, 0, 0, 1000, tzinfo=timezone.utc),
        ended_at=datetime(2026, 5, 22, 0, 0, 1, 1000, tzinfo=timezone.utc),
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
        exit_detail=ed,
        shell_used=False,
        terminal_forward_degraded=False,
        platform="linux",
        agentcam_version="0.1.0",
        paths=_paths(tmp_path),
        capture=capture,
    )


# ---------------------------------------------------------------------------
# Factory enums
# ---------------------------------------------------------------------------

class TestFactories:
    def test_wrap_pipe_default_policy(self):
        c = capture_for_wrap_pipe(empty_run_policy="auto_delete_clean_no_diff")
        assert c.mode == "wrap_pipe"
        assert c.stdout == "captured"
        assert c.stderr == "captured"
        assert c.git_before_after == "captured"
        assert c.path_risk_scan == "enabled"
        assert c.output_risk_scan == "enabled"
        assert c.dependency_probe == "enabled"
        assert c.transcript == "not_supported"
        assert c.internal_tool_calls == "not_visible"
        assert c.file_reads == "not_visible"
        assert c.network_egress == "not_visible"
        assert c.empty_run_policy == "auto_delete_clean_no_diff"

    def test_wrap_pipe_keep_empty_policy(self):
        c = capture_for_wrap_pipe(empty_run_policy="keep_empty_requested")
        assert c.empty_run_policy == "keep_empty_requested"

    def test_claude_hook_with_transcript_path(self):
        c = capture_for_claude_hook(
            transcript_available=True,
            empty_run_policy="auto_delete_clean_no_diff",
        )
        assert c.mode == "claude_hook"
        assert c.stdout == "not_available"
        assert c.stderr == "not_available"
        assert c.output_risk_scan == "disabled_no_output_stream"
        assert c.transcript == "available_not_ingested"
        # Path scan + dep probe + git both still available in hook mode.
        assert c.path_risk_scan == "enabled"
        assert c.dependency_probe == "enabled"
        assert c.git_before_after == "captured"

    def test_claude_hook_without_transcript_path(self):
        c = capture_for_claude_hook(
            transcript_available=False,
            empty_run_policy="auto_delete_clean_no_diff",
        )
        assert c.transcript == "unknown"

    def test_capture_capability_is_frozen(self):
        c = capture_for_wrap_pipe(empty_run_policy="auto_delete_clean_no_diff")
        import dataclasses
        try:
            object.__setattr__  # noqa: B018
            # frozen dataclass should refuse field rebinding.
            try:
                c.mode = "wrap_pty"  # type: ignore[misc]
            except dataclasses.FrozenInstanceError:
                return
            raise AssertionError(
                "CaptureCapability should be frozen so renderers cannot "
                "mutate the reported visibility mid-render."
            )
        except dataclasses.FrozenInstanceError:
            pass


# ---------------------------------------------------------------------------
# Manifest serialization
# ---------------------------------------------------------------------------

class TestSerializeManifest:
    def test_capture_block_emitted_when_set(self, tmp_path: Path):
        c = capture_for_wrap_pipe(empty_run_policy="auto_delete_clean_no_diff")
        m = _manifest(tmp_path, capture=c)
        data = serialize_manifest(m)
        assert "capture" in data
        cap = data["capture"]
        assert cap["mode"] == "wrap_pipe"
        assert cap["stdout"] == "captured"
        assert cap["output_risk_scan"] == "enabled"
        assert cap["empty_run_policy"] == "auto_delete_clean_no_diff"

    def test_capture_block_omitted_when_none(self, tmp_path: Path):
        # Legacy callers (existing tests, test fixtures) that build a
        # RunManifest without setting `capture` must still serialize.
        m = _manifest(tmp_path, capture=None)
        data = serialize_manifest(m)
        # Either absent OR explicit None — both signal "legacy / unknown".
        # We pick "absent" so JSON consumers can use `"capture" in data`.
        assert data.get("capture") is None or "capture" not in data

    def test_manifest_round_trips_via_write_manifest(self, tmp_path: Path):
        c = capture_for_claude_hook(
            transcript_available=True,
            empty_run_policy="auto_delete_clean_no_diff",
        )
        m = _manifest(tmp_path, capture=c)
        out = tmp_path / "manifest.json"
        write_manifest(m, out)
        loaded = json.loads(out.read_text(encoding="utf-8"))
        assert loaded["capture"]["mode"] == "claude_hook"
        assert loaded["capture"]["transcript"] == "available_not_ingested"


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

class TestRenderReport:
    def test_capture_visibility_section_present_when_set(self, tmp_path: Path):
        c = capture_for_wrap_pipe(empty_run_policy="auto_delete_clean_no_diff")
        m = _manifest(tmp_path, capture=c)
        bundle = ReportBundle(
            manifest=m,
            state_before=_empty_state(),
            state_after=_empty_state(),
        )
        report = render_report(bundle)
        assert "## Capture Visibility" in report
        assert "wrap_pipe" in report
        # Network egress line must NOT be omitted — that's the whole point
        # of Feature 1 + Feature 2 working together.
        assert "network_egress" in report or "Network egress" in report

    def test_capture_visibility_section_absent_when_none(self, tmp_path: Path):
        m = _manifest(tmp_path, capture=None)
        bundle = ReportBundle(
            manifest=m,
            state_before=_empty_state(),
            state_after=_empty_state(),
        )
        report = render_report(bundle)
        assert "## Capture Visibility" not in report

    def test_capture_visibility_hook_mode_signals_no_output_scan(
        self, tmp_path: Path,
    ):
        c = capture_for_claude_hook(
            transcript_available=True,
            empty_run_policy="auto_delete_clean_no_diff",
        )
        m = _manifest(tmp_path, capture=c)
        bundle = ReportBundle(
            manifest=m,
            state_before=_empty_state(),
            state_after=_empty_state(),
        )
        report = render_report(bundle)
        assert "claude_hook" in report
        # The user must be able to see that output scanning was off here.
        assert "disabled_no_output_stream" in report
        assert "not_available" in report  # stdout / stderr lines


# ---------------------------------------------------------------------------
# Legacy positional render_report still works (back-compat: no capture arg)
# ---------------------------------------------------------------------------

class TestLegacySignatureBackCompat:
    def test_legacy_positional_call_does_not_require_capture(
        self, tmp_path: Path,
    ):
        m = _manifest(tmp_path, capture=None)
        report = render_report(m, _empty_state(), _empty_state(), [])
        # Legacy callers should not lose existing sections.
        assert "## Verdict" in report
        assert "## Capture Visibility" not in report
