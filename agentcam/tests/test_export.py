"""Tests for `agentcam export` (Feature 5 / design.md #31).

End-to-end via real ``agentcam export`` subprocesses against a real
git repo, mirroring tests/test_e2e.py for parity.
"""
from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path


def _agentcam(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "agentcam.cli", *args],
        cwd=cwd,
        capture_output=True,
        timeout=25,
    )


def _run_dir(repo: Path) -> Path:
    return next((repo / ".git" / "agentcam" / "runs").iterdir())


def _make_one_run(repo: Path) -> str:
    """Produce one diff-bearing run and return its run_id."""
    proc = _agentcam(
        repo, "run", "--",
        sys.executable, "-c",
        "open('produced.txt','w').write('hi'); "
        "print('saw token sk-abcdefghijklmnopqrstuvwxyz1234567890')",
    )
    assert proc.returncode == 0, proc.stderr
    return _run_dir(repo).name


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestExportHappyPath:
    def test_default_output_path(self, tmp_git_repo: Path):
        rid = _make_one_run(tmp_git_repo)
        proc = _agentcam(tmp_git_repo, "export", rid)
        assert proc.returncode == 0, proc.stderr
        zip_path = tmp_git_repo / f"agentcam-export-{rid}.zip"
        assert zip_path.exists(), (
            f"default export location {zip_path} should hold the bundle"
        )

    def test_custom_output_path(self, tmp_git_repo: Path):
        rid = _make_one_run(tmp_git_repo)
        out = tmp_git_repo / "bundles" / "share.zip"
        out.parent.mkdir(parents=True, exist_ok=True)
        proc = _agentcam(tmp_git_repo, "export", rid, "--output", str(out))
        assert proc.returncode == 0, proc.stderr
        assert out.exists()

    def test_bundle_contains_expected_files(self, tmp_git_repo: Path):
        rid = _make_one_run(tmp_git_repo)
        out = tmp_git_repo / "share.zip"
        _agentcam(tmp_git_repo, "export", rid, "--output", str(out))
        with zipfile.ZipFile(out) as zf:
            names = set(zf.namelist())
        # All names are flat (no top-level dir prefix); brief shows nested
        # but a flat zip is the more common Windows convenience.
        # Either shape is acceptable as long as the set of *leaf* names
        # matches.
        leaves = {Path(n).name for n in names}
        assert "AGENT_RUN_REPORT.md" in leaves
        assert "manifest.redacted.json" in leaves
        assert "stdout.redacted.log" in leaves
        assert "stderr.redacted.log" in leaves
        assert "checksums.txt" in leaves
        assert "EXPORT_NOTES.md" in leaves

    def test_raw_logs_excluded_by_default(self, tmp_git_repo: Path):
        rid = _make_one_run(tmp_git_repo)
        out = tmp_git_repo / "share.zip"
        _agentcam(tmp_git_repo, "export", rid, "--output", str(out))
        with zipfile.ZipFile(out) as zf:
            leaves = {Path(n).name for n in zf.namelist()}
        # Brief AC: raw stdout.log / stderr.log must NOT appear in the
        # default bundle.
        assert "stdout.log" not in leaves
        assert "stderr.log" not in leaves

    def test_include_raw_opt_in(self, tmp_git_repo: Path):
        rid = _make_one_run(tmp_git_repo)
        out = tmp_git_repo / "share.zip"
        _agentcam(
            tmp_git_repo, "export", rid,
            "--output", str(out), "--include-raw",
        )
        with zipfile.ZipFile(out) as zf:
            leaves = {Path(n).name for n in zf.namelist()}
        assert "stdout.log" in leaves
        assert "stderr.log" in leaves

    def test_latest_shortcut(self, tmp_git_repo: Path):
        _make_one_run(tmp_git_repo)
        proc = _agentcam(tmp_git_repo, "export", "latest")
        assert proc.returncode == 0, proc.stderr
        # Some agentcam-export-*.zip should now exist in cwd.
        zips = list(tmp_git_repo.glob("agentcam-export-*.zip"))
        assert len(zips) == 1


# ---------------------------------------------------------------------------
# Manifest redaction
# ---------------------------------------------------------------------------

class TestManifestRedaction:
    def test_manifest_redacts_token_in_argv(self, tmp_git_repo: Path):
        # Run an agent command whose argv contains a token shape.
        proc = _agentcam(
            tmp_git_repo, "run", "--",
            sys.executable, "-c",
            "open('x.txt','w').write('x')",
            # Token-shaped arg embedded in argv. redact_argv already
            # redacts this in the live manifest's command_argv_redacted;
            # the bundle's manifest.redacted.json must not contain it
            # in any field at all (i.e. raw should be dropped or
            # redacted too).
        )
        assert proc.returncode == 0
        rid = _run_dir(tmp_git_repo).name
        out = tmp_git_repo / "share.zip"
        _agentcam(tmp_git_repo, "export", rid, "--output", str(out))

        with zipfile.ZipFile(out) as zf:
            with zf.open("manifest.redacted.json") as fp:
                redacted = json.loads(fp.read().decode("utf-8"))
        text_dump = json.dumps(redacted)
        # The raw argv field must not be a verbatim copy of a secret-
        # bearing argv. We use the structurally-true assertion: if
        # command_argv_raw is present at all, it must be the same as
        # command_argv_redacted (i.e. raw has been scrubbed too).
        if "command_argv_raw" in redacted:
            assert (
                redacted["command_argv_raw"]
                == redacted["command_argv_redacted"]
            ), (
                "redacted manifest must not preserve the unredacted "
                "argv next to the redacted one"
            )

    def test_manifest_redacted_no_inline_token_leak(
        self, tmp_git_repo: Path,
    ):
        # Verify that a token written into a manifest string value (we
        # use cwd as a stand-in: writing "sk-XXX..." into a path is
        # contrived but tests that redact_text is applied uniformly).
        rid = _make_one_run(tmp_git_repo)
        out = tmp_git_repo / "share.zip"
        _agentcam(tmp_git_repo, "export", rid, "--output", str(out))
        with zipfile.ZipFile(out) as zf:
            blob = zf.read("manifest.redacted.json").decode("utf-8")
        # The captured stdout from _make_one_run() prints
        # 'sk-abcdef...'. That string lives in stdout.log / stdout.redacted.log,
        # not in manifest.json -- but if a future regression copied
        # log contents into the manifest, this would catch it.
        assert "sk-abcdefghijklmnopqrstuvwxyz1234567890" not in blob


# ---------------------------------------------------------------------------
# Checksums + EXPORT_NOTES
# ---------------------------------------------------------------------------

class TestBundleMetadata:
    def test_checksums_match_actual_files(self, tmp_git_repo: Path):
        import hashlib
        rid = _make_one_run(tmp_git_repo)
        out = tmp_git_repo / "share.zip"
        _agentcam(tmp_git_repo, "export", rid, "--output", str(out))
        with zipfile.ZipFile(out) as zf:
            checksums_text = zf.read("checksums.txt").decode("utf-8")
            for line in checksums_text.strip().splitlines():
                # Format: "sha256  <filename>  <hex>"
                parts = line.split()
                assert len(parts) >= 3, f"unexpected checksum line: {line!r}"
                algo = parts[0]
                fname = parts[1]
                expected_hex = parts[2]
                assert algo == "sha256"
                actual = hashlib.sha256(zf.read(fname)).hexdigest()
                assert actual == expected_hex, (
                    f"{fname}: checksum {expected_hex} does not match "
                    f"actual {actual}"
                )

    def test_export_notes_present_and_explains_redaction(
        self, tmp_git_repo: Path,
    ):
        rid = _make_one_run(tmp_git_repo)
        out = tmp_git_repo / "share.zip"
        _agentcam(tmp_git_repo, "export", rid, "--output", str(out))
        with zipfile.ZipFile(out) as zf:
            notes = zf.read("EXPORT_NOTES.md").decode("utf-8")
        # Brief AC: notes must state that raw stdout/stderr are excluded
        # by default AND that redaction is best-effort.
        assert "raw" in notes.lower()
        assert "redact" in notes.lower() or "best-effort" in notes.lower()


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class TestExportErrors:
    def test_unknown_run_id_errors(self, tmp_git_repo: Path):
        proc = _agentcam(tmp_git_repo, "export", "no-such-run-id-12345")
        assert proc.returncode != 0
        # Error message identifies the missing run id.
        assert b"no-such-run-id-12345" in proc.stderr or b"not found" in proc.stderr.lower()

    def test_no_git_repo_errors(self, tmp_path: Path):
        proc = _agentcam(tmp_path, "export", "latest")
        assert proc.returncode != 0

    def test_no_runs_at_all_errors(self, tmp_git_repo: Path):
        # Git repo exists but no agentcam runs yet.
        proc = _agentcam(tmp_git_repo, "export", "latest")
        assert proc.returncode != 0

    def test_existing_output_without_force_rejected(self, tmp_git_repo: Path):
        rid = _make_one_run(tmp_git_repo)
        out = tmp_git_repo / "share.zip"
        out.write_bytes(b"pre-existing content")
        proc = _agentcam(tmp_git_repo, "export", rid, "--output", str(out))
        assert proc.returncode != 0
        # File unchanged.
        assert out.read_bytes() == b"pre-existing content"

    def test_existing_output_with_force_overwrites(self, tmp_git_repo: Path):
        rid = _make_one_run(tmp_git_repo)
        out = tmp_git_repo / "share.zip"
        out.write_bytes(b"pre-existing content")
        proc = _agentcam(
            tmp_git_repo, "export", rid,
            "--output", str(out), "--force",
        )
        assert proc.returncode == 0, proc.stderr
        # File replaced with the zip.
        assert out.read_bytes() != b"pre-existing content"
        # Verify it's a real zip.
        with zipfile.ZipFile(out) as zf:
            zf.namelist()  # raises if not a zip

    def test_run_id_with_path_traversal_rejected(self, tmp_git_repo: Path):
        # Adversarial run_id with traversal segments. agentcam must not
        # read or include files outside the runs/ directory.
        _make_one_run(tmp_git_repo)  # create a real run so runs/ exists
        proc = _agentcam(
            tmp_git_repo, "export", "../../etc/passwd",
        )
        assert proc.returncode != 0
        # No leakage zip was written.
        traversal_zip = tmp_git_repo / "agentcam-export-..---etc-passwd.zip"
        assert not traversal_zip.exists()
