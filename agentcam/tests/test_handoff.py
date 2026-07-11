"""Tests for manifest evidence, `agentcam handoff`, and `export --files`.

End-to-end via real agentcam subprocesses against a real git repo,
mirroring tests/test_export.py.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from cli_harness import _agentcam, _make_one_run, _run_dir
from agentcam.git_state import compute_product_fingerprint
from agentcam.models import ChangedFile


# ---------------------------------------------------------------------------
# Manifest evidence block
# ---------------------------------------------------------------------------

class TestManifestEvidence:
    def test_product_fingerprint_ignores_transient_git_status(
        self, tmp_git_repo: Path
    ):
        product = tmp_git_repo / "same.txt"
        product.write_text("same delivery", encoding="utf-8")

        dirty = compute_product_fingerprint(
            tmp_git_repo,
            [ChangedFile(path="same.txt", status="unstaged_modified")],
        )
        committed = compute_product_fingerprint(
            tmp_git_repo,
            [ChangedFile(path="same.txt", status="committed")],
        )

        assert dirty == committed

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

    def test_committed_change_is_preserved_in_turn_delta(
        self, tmp_git_repo: Path
    ):
        body = (
            "import subprocess;"
            "open('committed.txt','w').write('committed');"
            "subprocess.run(['git','add','committed.txt'],check=True);"
            "subprocess.run(['git','-c','user.email=test@example.com','-c',"
            "'user.name=Test','commit','-qm','agent commit'],check=True)"
        )

        _make_one_run(tmp_git_repo, body)
        manifest = json.loads(
            (_run_dir(tmp_git_repo) / "manifest.json").read_text("utf-8")
        )

        assert [f["path"] for f in manifest["evidence"]["changed_files"]] == [
            "committed.txt"
        ]
        assert manifest["evidence"]["changed_files"][0]["status"] == "committed"

    def test_unchanged_preexisting_dirty_file_is_not_attributed_to_run(
        self, tmp_git_repo: Path
    ):
        tracked = tmp_git_repo / "user-dirty.txt"
        tracked.write_text("base", encoding="utf-8")
        subprocess.run(["git", "add", "user-dirty.txt"], cwd=tmp_git_repo, check=True)
        subprocess.run(
            [
                "git", "-c", "user.email=test@example.com", "-c",
                "user.name=Test", "commit", "-qm", "base",
            ],
            cwd=tmp_git_repo,
            check=True,
        )
        tracked.write_text("user dirt", encoding="utf-8")

        _make_one_run(tmp_git_repo)
        manifest = json.loads(
            (_run_dir(tmp_git_repo) / "manifest.json").read_text("utf-8")
        )

        assert [f["path"] for f in manifest["evidence"]["changed_files"]] == [
            "produced.txt"
        ]

    def test_modified_preexisting_dirty_file_is_attributed_to_run(
        self, tmp_git_repo: Path
    ):
        tracked = tmp_git_repo / "user-dirty.txt"
        tracked.write_text("base", encoding="utf-8")
        subprocess.run(["git", "add", "user-dirty.txt"], cwd=tmp_git_repo, check=True)
        subprocess.run(
            [
                "git", "-c", "user.email=test@example.com", "-c",
                "user.name=Test", "commit", "-qm", "base",
            ],
            cwd=tmp_git_repo,
            check=True,
        )
        tracked.write_text("user dirt", encoding="utf-8")

        _make_one_run(
            tmp_git_repo,
            "open('user-dirty.txt','w').write('agent changed it')",
        )
        manifest = json.loads(
            (_run_dir(tmp_git_repo) / "manifest.json").read_text("utf-8")
        )

        assert [f["path"] for f in manifest["evidence"]["changed_files"]] == [
            "user-dirty.txt"
        ]

    def test_manifest_binds_final_state_product_and_declared_scope(
        self, tmp_git_repo: Path
    ):
        slime = tmp_git_repo / ".slime"
        slime.mkdir()
        (slime / "corridor.md").write_text(
            "# Corridor: test\n\n## Rigor\nnormal\n\n## Paths\n- src/**\n",
            encoding="utf-8",
        )

        _make_one_run(tmp_git_repo)
        manifest = json.loads(
            (_run_dir(tmp_git_repo) / "manifest.json").read_text("utf-8")
        )

        assert manifest["declared_scope"] == []
        assert len(manifest["final_state_fingerprint"]) == 64
        assert len(manifest["evidence"]["product_fingerprint"]) == 64


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
        assert lines[1].startswith("Scope: <fill in:")
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

    def test_handoff_refuses_untracked_secret_like_filename(self, tmp_git_repo: Path):
        proc = _agentcam(
            tmp_git_repo, "run", "--",
            sys.executable, "-c",
            "open('.env.production','w').write('K=1')",
        )
        assert proc.returncode == 0, proc.stderr
        proc = _agentcam(tmp_git_repo, "handoff")
        assert proc.returncode == 2
        assert b"untracked secret-like" in proc.stderr

    def test_handoff_uses_real_tracked_secret_like_path(self, tmp_git_repo: Path):
        secret = tmp_git_repo / ".env.production"
        secret.write_text("K=base", encoding="utf-8")
        subprocess.run(["git", "add", ".env.production"], cwd=tmp_git_repo, check=True)
        subprocess.run(
            [
                "git", "-c", "user.email=test@example.com", "-c",
                "user.name=Test", "commit", "-qm", "track filename",
            ],
            cwd=tmp_git_repo,
            check=True,
        )
        slime = tmp_git_repo / ".slime"
        slime.mkdir()
        (slime / "corridor.md").write_text(
            "# Corridor: secret\n\n## Rigor\nnormal\n\n## Paths\n- .env.production\n",
            encoding="utf-8",
        )

        _make_one_run(tmp_git_repo, "open('.env.production','w').write('K=changed')")
        proc = _agentcam(tmp_git_repo, "handoff")

        assert proc.returncode == 0, proc.stderr
        assert "Scope: <fill in:" in proc.stdout.decode("utf-8")
        assert "Review first: .env.production" in proc.stdout.decode("utf-8")

    def test_handoff_ignores_archived_corridor_scope(
        self, tmp_git_repo: Path
    ):
        slime = tmp_git_repo / ".slime"
        slime.mkdir()
        (slime / "corridor.md").write_text(
            "# Corridor: declared\n\n## Rigor\nnormal\n\n## Paths\n- src/**\n",
            encoding="utf-8",
        )

        _make_one_run(tmp_git_repo)
        proc = _agentcam(tmp_git_repo, "handoff")

        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.decode("utf-8").splitlines()[1].startswith("Scope: <fill in:")

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
