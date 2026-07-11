"""Tests for manifest evidence, `agentcam handoff`, and `export --files`.

End-to-end via real agentcam subprocesses against a real git repo,
mirroring tests/test_export.py.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from cli_harness import _agentcam, _make_one_run, _run_dir


# ---------------------------------------------------------------------------
# Manifest evidence block
# ---------------------------------------------------------------------------

class TestManifestEvidence:
    def test_manifest_contains_evidence_block(self, tmp_git_repo: Path):
        _make_one_run(tmp_git_repo)
        manifest = json.loads(
            (_run_dir(tmp_git_repo) / "manifest.json").read_text("utf-8")
        )
        assert "evidence" in manifest
        ev = manifest["evidence"]
        assert [cf["path"] for cf in ev["changed_files"]] == ["produced.txt"]
        assert ev["overall_risk"] in {"NONE_DETECTED", "MEDIUM", "HIGH"}
        assert isinstance(ev["risk_flags"], list)
        assert "diff_stat" in ev
        assert "diff_stat_cached" in ev


# ---------------------------------------------------------------------------
# `agentcam handoff`
# ---------------------------------------------------------------------------

class TestHandoff:
    def test_prints_five_line_corridor_handoff(self, tmp_git_repo: Path):
        _make_one_run(tmp_git_repo)
        proc = _agentcam(tmp_git_repo, "handoff")
        assert proc.returncode == 0, proc.stderr
        lines = proc.stdout.decode("utf-8").strip().splitlines()
        assert [line.split(":")[0] for line in lines] == [
            "Decision", "Scope", "Review first", "Verified", "Risk",
        ]
        assert lines[1] == "Scope: produced.txt"
        assert lines[2] == "Review first: produced.txt"
        # Decision and Verified stay with the author.
        assert "<fill in" in lines[0]
        assert "<fill in" in lines[3]
        assert lines[4] == "Risk: none-detected"

    def test_partial_capture_reports_unknown_instead_of_low(self, tmp_git_repo: Path):
        _make_one_run(tmp_git_repo)
        manifest_path = _run_dir(tmp_git_repo) / "manifest.json"
        data = json.loads(manifest_path.read_text("utf-8"))
        data["capture"]["mode"] = "claude_hook"
        data["capture"]["output_risk_scan"] = "disabled_no_output_stream"
        manifest_path.write_text(json.dumps(data), encoding="utf-8")

        proc = _agentcam(tmp_git_repo, "handoff")

        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.decode("utf-8").splitlines()[4] == "Risk: unknown"

    def test_handoff_redacts_secret_like_filenames(self, tmp_git_repo: Path):
        # The handoff is drafted for a PR body; a secret-like filename must
        # not leave the machine through it (same rule as report/export).
        proc = _agentcam(
            tmp_git_repo, "run", "--",
            sys.executable, "-c",
            "open('.env.production','w').write('K=1')",
        )
        assert proc.returncode == 0, proc.stderr
        proc = _agentcam(tmp_git_repo, "handoff")
        assert proc.returncode == 0, proc.stderr
        out = proc.stdout.decode("utf-8")
        assert ".env.production" not in out
        assert "<redacted-secret-filename>" in out

    def test_old_manifest_without_evidence_errors(self, tmp_git_repo: Path):
        _make_one_run(tmp_git_repo)
        manifest_path = _run_dir(tmp_git_repo) / "manifest.json"
        data = json.loads(manifest_path.read_text("utf-8"))
        data.pop("evidence")
        manifest_path.write_text(json.dumps(data), encoding="utf-8")
        proc = _agentcam(tmp_git_repo, "handoff")
        assert proc.returncode == 2
        assert b"older agentcam" in proc.stderr

    def test_outside_git_repo_errors(self, tmp_path: Path):
        proc = _agentcam(tmp_path, "handoff")
        assert proc.returncode == 2
        # Same contract as `agentcam export` outside a repo: exit 2
        # with an agentcam-prefixed error (exact git wording varies).
        assert proc.stderr.startswith(b"agentcam:")


# ---------------------------------------------------------------------------
# `agentcam export --files`
# ---------------------------------------------------------------------------

class TestExportFiles:
    def test_writes_committable_artifacts(self, tmp_git_repo: Path):
        rid = _make_one_run(tmp_git_repo)
        dest = tmp_git_repo / ".agentcam"
        proc = _agentcam(tmp_git_repo, "export", rid, "--files", str(dest))
        assert proc.returncode == 0, proc.stderr
        assert (dest / "AGENT_RUN_REPORT.md").exists()
        redacted = json.loads(
            (dest / "manifest.redacted.json").read_text("utf-8")
        )
        assert "evidence" in redacted
        # Logs are never part of the committable form.
        assert not list(dest.glob("*.log"))

    def test_refuses_overwrite_without_force(self, tmp_git_repo: Path):
        rid = _make_one_run(tmp_git_repo)
        dest = tmp_git_repo / ".agentcam"
        assert _agentcam(
            tmp_git_repo, "export", rid, "--files", str(dest)
        ).returncode == 0
        proc = _agentcam(tmp_git_repo, "export", rid, "--files", str(dest))
        assert proc.returncode == 2
        assert b"already exists" in proc.stderr
        proc = _agentcam(
            tmp_git_repo, "export", rid, "--files", str(dest), "--force"
        )
        assert proc.returncode == 0, proc.stderr

    def test_rejects_include_raw(self, tmp_git_repo: Path):
        rid = _make_one_run(tmp_git_repo)
        proc = _agentcam(
            tmp_git_repo, "export", rid,
            "--files", str(tmp_git_repo / ".agentcam"), "--include-raw",
        )
        assert proc.returncode == 2
        assert b"--include-raw" in proc.stderr
