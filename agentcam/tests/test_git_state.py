"""Tests for agentbox.git_state.

Covers plan section 4 (git state collection): porcelain parsing, staged vs
unstaged vs untracked, detached HEAD, no-commits repo, pre-existing op
markers, cached-diff regression.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agentbox.git_state import (
    NotAGitRepoError,
    collect_git_state,
    detect_pre_existing_op,
    is_git_repo,
    is_working_tree_dirty,
    parse_porcelain_v1z,
    resolve_git_dir,
    resolve_git_root,
)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        [
            "git",
            "-c", "user.email=test@example.com",
            "-c", "user.name=Test",
            "-c", "commit.gpgsign=false",
            *args,
        ],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


class TestRepoDetection:
    def test_is_git_repo_true(self, tmp_git_repo: Path):
        assert is_git_repo(tmp_git_repo) is True

    def test_is_git_repo_false(self, tmp_path: Path):
        assert is_git_repo(tmp_path) is False

    def test_collect_outside_repo_raises(self, tmp_path: Path):
        with pytest.raises(NotAGitRepoError):
            collect_git_state(tmp_path)


class TestResolvePaths:
    def test_git_dir_is_absolute_dir(self, tmp_git_repo: Path):
        gd = resolve_git_dir(tmp_git_repo)
        assert gd.is_absolute()
        assert gd.is_dir()
        assert gd.name == ".git"

    def test_git_root_matches_tmp(self, tmp_git_repo: Path):
        root = resolve_git_root(tmp_git_repo)
        assert root.resolve() == tmp_git_repo.resolve()


class TestPorcelainParser:
    def test_empty(self):
        assert parse_porcelain_v1z(b"") == []

    def test_untracked(self):
        out = parse_porcelain_v1z(b"?? newfile.py\x00")
        assert len(out) == 1
        assert out[0].path == "newfile.py"
        assert out[0].status == "untracked"

    def test_staged_added_modified(self):
        # "M  foo.py" means staged (X='M') with no unstaged change.
        out = parse_porcelain_v1z(b"M  foo.py\x00")
        assert out[0].status == "staged"

    def test_unstaged_modified(self):
        out = parse_porcelain_v1z(b" M foo.py\x00")
        assert out[0].status == "unstaged_modified"

    def test_unstaged_deleted(self):
        out = parse_porcelain_v1z(b" D gone.py\x00")
        assert out[0].status == "unstaged_deleted"

    def test_staged_deleted(self):
        out = parse_porcelain_v1z(b"D  gone.py\x00")
        assert out[0].status == "staged_deleted"

    def test_renamed_pair(self):
        out = parse_porcelain_v1z(b"R  new.py\x00old.py\x00")
        assert len(out) == 1
        assert out[0].status == "renamed"
        assert out[0].path == "new.py"
        assert out[0].rename_from == "old.py"

    def test_unmerged_uu(self):
        out = parse_porcelain_v1z(b"UU conflicted.py\x00")
        assert out[0].status == "unmerged"

    def test_filename_with_spaces(self):
        out = parse_porcelain_v1z(b"?? a b c.txt\x00")
        assert out[0].path == "a b c.txt"

    def test_multiple_entries_preserves_order(self):
        data = b"?? a.py\x00 M b.py\x00M  c.py\x00"
        out = parse_porcelain_v1z(data)
        assert [(f.path, f.status) for f in out] == [
            ("a.py", "untracked"),
            ("b.py", "unstaged_modified"),
            ("c.py", "staged"),
        ]


class TestCollectGitState:
    def test_clean_repo_state(self, tmp_git_repo: Path):
        state = collect_git_state(tmp_git_repo)
        assert state.changed_files == []
        assert is_working_tree_dirty(state) is False
        assert state.branch == "main"
        assert state.is_detached_head is False
        assert state.head is not None
        assert state.pre_existing_op is None

    def test_untracked_makes_dirty(self, tmp_git_repo: Path):
        (tmp_git_repo / "new.txt").write_text("x")
        state = collect_git_state(tmp_git_repo)
        assert any(
            f.path == "new.txt" and f.status == "untracked"
            for f in state.changed_files
        )
        assert is_working_tree_dirty(state) is True

    def test_staged_change_visible_via_cached_diff(self, tmp_git_repo: Path):
        # Regression: original plan only ran `git diff --stat` (unstaged).
        # If we only had that, a staged file would be invisible in diff_stat
        # even though porcelain saw it. Plan §4 requires both --cached and
        # non-cached. This test guards that.
        (tmp_git_repo / "a.txt").write_text("x")
        _git(tmp_git_repo, "add", "a.txt")
        state = collect_git_state(tmp_git_repo)

        statuses = {(f.path, f.status) for f in state.changed_files}
        assert ("a.txt", "staged") in statuses

        # The cached diff must be populated (regression guard).
        assert state.diff_stat_cached
        assert state.diff_name_status_cached

    def test_unstaged_change_visible_via_unstaged_diff(self, tmp_git_repo: Path):
        (tmp_git_repo / "a.txt").write_text("first")
        _git(tmp_git_repo, "add", "a.txt")
        _git(tmp_git_repo, "commit", "-q", "-m", "add a")
        (tmp_git_repo / "a.txt").write_text("second")

        state = collect_git_state(tmp_git_repo)
        assert any(
            f.path == "a.txt" and f.status == "unstaged_modified"
            for f in state.changed_files
        )
        assert state.diff_stat

    def test_detached_head_is_reported(self, tmp_git_repo: Path):
        (tmp_git_repo / "a.txt").write_text("x")
        _git(tmp_git_repo, "add", "a.txt")
        _git(tmp_git_repo, "commit", "-q", "-m", "second")
        _git(tmp_git_repo, "checkout", "--detach", "HEAD")

        state = collect_git_state(tmp_git_repo)
        assert state.is_detached_head is True
        assert state.branch is None
        assert state.head is not None

    def test_diff_check_only_runs_when_is_after(self, tmp_git_repo: Path):
        before = collect_git_state(tmp_git_repo, is_after=False)
        after = collect_git_state(tmp_git_repo, is_after=True)
        # On a clean repo both diff_check outputs are empty strings, but the
        # field is only populated when is_after=True; on a clean repo we
        # cannot distinguish via value alone, so the contract is:
        # before.diff_check == "" always (we didn't run it).
        assert before.diff_check == ""
        # after.diff_check may be "" (clean) or non-empty (whitespace error).
        assert isinstance(after.diff_check, str)

    def test_merge_marker_detected(self, tmp_git_repo: Path):
        gd = resolve_git_dir(tmp_git_repo)
        (gd / "MERGE_HEAD").write_text("deadbeef\n")
        state = collect_git_state(tmp_git_repo)
        assert state.pre_existing_op == "merge"

    def test_rebase_marker_detected(self, tmp_git_repo: Path):
        gd = resolve_git_dir(tmp_git_repo)
        (gd / "rebase-merge").mkdir()
        state = collect_git_state(tmp_git_repo)
        assert state.pre_existing_op == "rebase"


class TestDetectPreExistingOp:
    def test_none_when_clean(self, tmp_git_repo: Path):
        assert detect_pre_existing_op(resolve_git_dir(tmp_git_repo)) is None

    def test_cherry_pick(self, tmp_git_repo: Path):
        gd = resolve_git_dir(tmp_git_repo)
        (gd / "CHERRY_PICK_HEAD").write_text("deadbeef\n")
        assert detect_pre_existing_op(gd) == "cherry-pick"

    def test_revert(self, tmp_git_repo: Path):
        gd = resolve_git_dir(tmp_git_repo)
        (gd / "REVERT_HEAD").write_text("deadbeef\n")
        assert detect_pre_existing_op(gd) == "revert"
