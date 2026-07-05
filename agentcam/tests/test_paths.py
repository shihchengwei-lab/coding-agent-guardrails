"""Tests for agentcam.paths.

Covers plan section 7 (run id format) and section 13 (parallel collision).
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

import pytest

from agentcam.paths import (
    RunIdCollisionError,
    create_run_dir,
    format_run_id,
    slugify,
)


class TestSlugify:
    def test_none_returns_default(self):
        assert slugify(None) == "run"

    def test_empty_returns_default(self):
        assert slugify("") == "run"

    def test_lowercases(self):
        assert slugify("FixLogin") == "fixlogin"

    def test_replaces_specials_with_dash(self):
        assert slugify("fix login bug!") == "fix-login-bug"

    def test_collapses_consecutive_dashes(self):
        assert slugify("fix---login") == "fix-login"

    def test_strips_surrounding_dashes(self):
        assert slugify("---fix---") == "fix"

    def test_trims_to_max_length(self):
        s = slugify("a" * 100)
        assert len(s) <= 40

    def test_non_ascii_falls_back_to_default(self):
        # All chars get replaced by '-', then collapsed/trimmed to empty.
        assert slugify("中文") == "run"


class TestFormatRunId:
    def test_basic_format(self):
        ts = datetime(2026, 5, 16, 21, 30, 55, 742000)
        rid = format_run_id(ts, "claude-fix-login")
        assert rid.text == "20260516-213055-742-claude-fix-login"

    def test_with_suffix(self):
        ts = datetime(2026, 5, 16, 21, 30, 55, 742000)
        rid = format_run_id(ts, "run", "a1b2")
        assert rid.text == "20260516-213055-742-run-a1b2"

    def test_millisecond_zero_padded(self):
        # 5000 microseconds = 5 ms -> "005" (three digits, zero-padded)
        ts = datetime(2026, 1, 1, 0, 0, 0, 5000)
        rid = format_run_id(ts, "run")
        assert "-005-" in rid.text


class TestCreateRunDir:
    def test_creates_expected_layout(self, tmp_path: Path):
        ts = datetime(2026, 5, 16, 21, 30, 55, 742000)
        run_id, paths = create_run_dir(tmp_path, ts, "test")

        # Directory exists.
        assert Path(paths.run_dir).is_dir()
        # Layout under <git_dir>/agentcam/runs/<run_id>/.
        rel = Path(paths.run_dir).relative_to(tmp_path)
        assert rel.parts == ("agentcam", "runs", run_id.text)
        # File paths point inside run_dir.
        assert paths.manifest_json.endswith("manifest.json")
        assert paths.report_md.endswith("AGENT_RUN_REPORT.md")
        assert paths.stdout_raw.endswith("stdout.log")
        assert paths.stderr_raw.endswith("stderr.log")
        assert paths.stdout_redacted.endswith("stdout.redacted.log")
        assert paths.stderr_redacted.endswith("stderr.redacted.log")

    def test_collision_retry_yields_unique_dirs(self, tmp_path: Path):
        ts = datetime(2026, 5, 16, 21, 30, 55, 742000)
        run_id_a, _ = create_run_dir(tmp_path, ts, "test")
        run_id_b, paths_b = create_run_dir(tmp_path, ts, "test")

        assert run_id_a.text != run_id_b.text
        assert Path(paths_b.run_dir).is_dir()
        # Second run_id must carry a 4-hex collision suffix.
        assert re.match(r".+-[0-9a-f]{4}$", run_id_b.text), run_id_b.text

    def test_collision_exhausts_retries_raises(self, monkeypatch, tmp_path: Path):
        """Force every collision retry to land on a pre-existing dir."""
        ts = datetime(2026, 5, 16, 21, 30, 55, 742000)

        # Make secrets.token_hex deterministic so all retries land on -dead.
        from agentcam import paths as paths_mod
        monkeypatch.setattr(paths_mod.secrets, "token_hex", lambda n: "dead")

        base = tmp_path / "agentcam" / "runs"
        os.makedirs(base / "20260516-213055-742-test")
        os.makedirs(base / "20260516-213055-742-test-dead")

        with pytest.raises(RunIdCollisionError):
            create_run_dir(tmp_path, ts, "test")
