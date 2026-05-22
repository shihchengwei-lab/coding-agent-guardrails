"""Tests for ruleset provenance metadata (Feature 4 / design.md #29).

Provenance lets the report explain "which rule set produced these
flags" so two reports diffed by future `agentcam compare` (or a human)
cannot silently disagree because one used a custom YAML and the other
used the built-in.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agentcam import __version__
from agentcam.models import (
    ChangedFile,
    ExitDetail,
    GitState,
    ReportBundle,
    RulesetProvenance,
    RunManifest,
    RunPaths,
)
from agentcam.report import render_report, serialize_manifest
from agentcam.scanner import (
    PathMatchers,
    RuleSet,
    compute_ruleset_sha256,
    default_ruleset,
    provenance_for_builtin_ruleset,
)


# ---------------------------------------------------------------------------
# Builders
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


def _manifest(
    tmp_path: Path,
    *,
    ruleset: RulesetProvenance | None,
) -> RunManifest:
    return RunManifest(
        schema_version="0.1",
        run_id="20260522-000000-001-test",
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
            wrapper_exit=0, raw_returncode=0, raw_returncode_hex=None,
            platform="linux", interpretation="success",
            interpretation_source="known_table",
        ),
        shell_used=False,
        terminal_forward_degraded=False,
        platform="linux",
        agentcam_version="0.1.0",
        paths=_paths(tmp_path),
        ruleset=ruleset,
    )


# ---------------------------------------------------------------------------
# Hash determinism
# ---------------------------------------------------------------------------

class TestRulesetHash:
    def test_hash_is_deterministic_across_calls(self):
        rs = default_ruleset()
        h1 = compute_ruleset_sha256(rs)
        h2 = compute_ruleset_sha256(rs)
        assert h1 == h2

    def test_hash_starts_with_sha256_prefix(self):
        h = compute_ruleset_sha256(default_ruleset())
        assert h.startswith("sha256:")
        # Hex digits after the prefix.
        suffix = h.removeprefix("sha256:")
        assert len(suffix) == 64
        int(suffix, 16)  # raises if not hex

    def test_hash_changes_when_rules_change(self):
        base = default_ruleset()
        modified = RuleSet(
            high_paths=PathMatchers(
                segments=base.high_paths.segments + (("zzz", "extra zzz"),),
                prefixes=base.high_paths.prefixes,
                basenames=base.high_paths.basenames,
                extensions=base.high_paths.extensions,
            ),
            medium_paths=base.medium_paths,
            high_output=base.high_output,
            medium_output=base.medium_output,
        )
        assert compute_ruleset_sha256(base) != compute_ruleset_sha256(modified)

    def test_hash_independent_of_segment_input_order(self):
        # Canonical form sorts before hashing so two rule lists with
        # the same content but different order hash equal. Otherwise
        # future migrations that reorder tuples for readability would
        # silently change the hash and confuse `agentcam compare`.
        base = default_ruleset()
        reordered_segments = tuple(
            sorted(base.high_paths.segments, reverse=True)
        )
        reshuffled = RuleSet(
            high_paths=PathMatchers(
                segments=reordered_segments,
                prefixes=base.high_paths.prefixes,
                basenames=base.high_paths.basenames,
                extensions=base.high_paths.extensions,
            ),
            medium_paths=base.medium_paths,
            high_output=base.high_output,
            medium_output=base.medium_output,
        )
        assert compute_ruleset_sha256(base) == compute_ruleset_sha256(reshuffled)


# ---------------------------------------------------------------------------
# Built-in provenance helper
# ---------------------------------------------------------------------------

class TestProvenanceForBuiltin:
    def test_default_values(self):
        p = provenance_for_builtin_ruleset()
        assert p.builtin_ruleset_id == "agentcam-default"
        assert p.builtin_ruleset_version == __version__
        assert p.custom_rules_path is None
        assert p.custom_rules_sha256 is None
        assert p.load_status == "builtin_only"
        # The merged hash matches the built-in hash because there is no
        # custom layer on top.
        assert p.merged_rules_sha256 == compute_ruleset_sha256(default_ruleset())

    def test_is_frozen(self):
        import dataclasses
        p = provenance_for_builtin_ruleset()
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.load_status = "custom_loaded"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Manifest serialization
# ---------------------------------------------------------------------------

class TestSerializeRuleset:
    def test_ruleset_block_emitted_when_set(self, tmp_path: Path):
        p = provenance_for_builtin_ruleset()
        m = _manifest(tmp_path, ruleset=p)
        data = serialize_manifest(m)
        assert "ruleset" in data
        rs = data["ruleset"]
        assert rs["builtin_ruleset_id"] == "agentcam-default"
        assert rs["load_status"] == "builtin_only"
        assert rs["custom_rules_path"] is None
        assert rs["custom_rules_sha256"] is None
        assert rs["merged_rules_sha256"].startswith("sha256:")

    def test_ruleset_block_omitted_when_none(self, tmp_path: Path):
        m = _manifest(tmp_path, ruleset=None)
        data = serialize_manifest(m)
        assert data.get("ruleset") is None or "ruleset" not in data

    def test_merged_hash_round_trips_via_json(self, tmp_path: Path):
        p = provenance_for_builtin_ruleset()
        m = _manifest(tmp_path, ruleset=p)
        loaded = json.loads(json.dumps(serialize_manifest(m)))
        assert loaded["ruleset"]["merged_rules_sha256"] == p.merged_rules_sha256


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

class TestRenderRuleset:
    def test_section_present_when_set(self, tmp_path: Path):
        p = provenance_for_builtin_ruleset()
        m = _manifest(tmp_path, ruleset=p)
        bundle = ReportBundle(
            manifest=m,
            state_before=_empty_state(),
            state_after=_empty_state(),
        )
        report = render_report(bundle)
        assert "## Scanner Ruleset" in report
        assert "agentcam-default" in report
        assert "builtin_only" in report

    def test_section_absent_when_none(self, tmp_path: Path):
        m = _manifest(tmp_path, ruleset=None)
        bundle = ReportBundle(
            manifest=m,
            state_before=_empty_state(),
            state_after=_empty_state(),
        )
        report = render_report(bundle)
        assert "## Scanner Ruleset" not in report
