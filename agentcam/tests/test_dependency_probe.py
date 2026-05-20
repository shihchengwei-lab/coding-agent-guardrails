"""Tests for agentcam.dependency_probe.

Covers:
- Per-ecosystem parsers (pip requirements.txt, pyproject.toml, package.json)
  as pure functions on content strings.
- Dep-set diff (added / removed / version_changed).
- End-to-end ``scan_dependencies`` against a tmp git repo.

The parsers intentionally tolerate malformed input rather than raise -- a
dependency probe must never crash the wrapped run on a half-edited
manifest. Tests pin that behavior with explicit "garbage in, empty out"
cases per parser.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agentcam.dependency_probe import (
    _is_safe_repo_relative_path,
    _redact_url_creds,
    diff_dep_sets,
    parse_package_json,
    parse_pyproject_toml,
    parse_requirements_txt,
    scan_dependencies,
)
from agentcam.models import DependencyChange


# ---------------------------------------------------------------------------
# requirements.txt parser
# ---------------------------------------------------------------------------

class TestParseRequirementsTxt:
    def test_simple_pinned(self):
        assert parse_requirements_txt("requests==2.31.0") == {
            "requests": "==2.31.0"
        }

    def test_unpinned(self):
        assert parse_requirements_txt("requests") == {"requests": ""}

    def test_range(self):
        assert parse_requirements_txt("requests>=2.0,<3.0") == {
            "requests": ">=2.0,<3.0"
        }

    def test_multiple_lines(self):
        content = "requests==2.0.0\nflask>=1.0\nnumpy"
        assert parse_requirements_txt(content) == {
            "requests": "==2.0.0",
            "flask": ">=1.0",
            "numpy": "",
        }

    def test_comments_stripped(self):
        content = "# top comment\nrequests==2.0  # inline\n# another"
        assert parse_requirements_txt(content) == {"requests": "==2.0"}

    def test_blank_lines_ignored(self):
        assert parse_requirements_txt("\n\nrequests==1\n\n") == {
            "requests": "==1"
        }

    def test_extras(self):
        assert parse_requirements_txt("requests[security]==2.0") == {
            "requests[security]": "==2.0"
        }

    def test_env_marker_stripped(self):
        # The marker isn't part of the version spec we report.
        assert parse_requirements_txt(
            "tomli==2.0; python_version < '3.11'"
        ) == {"tomli": "==2.0"}

    def test_directives_skipped(self):
        # -r, -e, --editable, --index-url etc. aren't packages we can diff.
        content = (
            "-r other.txt\n"
            "--index-url https://pypi.org/simple\n"
            "-e ./local-pkg\n"
            "requests==1\n"
        )
        assert parse_requirements_txt(content) == {"requests": "==1"}

    def test_empty_input(self):
        assert parse_requirements_txt("") == {}

    def test_garbage_lines_skipped(self):
        # Lines that aren't recognizable as a pkg spec must not crash.
        content = "!!!\n@@@\nrequests==1\n^^^"
        result = parse_requirements_txt(content)
        assert result.get("requests") == "==1"

    def test_case_preserved(self):
        # PyPI is case-insensitive at install time but we preserve what's
        # written -- the diff should still match if both files agree.
        assert parse_requirements_txt("Django==4.0") == {"Django": "==4.0"}

    def test_url_fragment_egg_preserved(self):
        # Codex review MEDIUM #3: ``#egg=name`` is a URL fragment, not a
        # comment. Previous splitting on bare ``#`` destroyed the URL and
        # misclassified the dep name as ``git``.
        line = "pkg @ git+https://host/r.git#egg=pkg"
        result = parse_requirements_txt(line)
        assert "pkg" in result
        # The fragment must still be in the captured spec.
        assert "#egg=pkg" in result["pkg"]

    def test_inline_comment_still_stripped_with_whitespace(self):
        # The fix preserves URL fragments but must still strip real
        # inline comments that follow whitespace.
        assert parse_requirements_txt("requests==1.0  # pin for CI") == {
            "requests": "==1.0"
        }

    def test_url_credentials_redacted(self):
        # Codex review HIGH #1: credentials in URL specs must not survive.
        line = "pkg @ git+https://USER:TOKEN@host/r.git"
        result = parse_requirements_txt(line)
        spec = result["pkg"]
        assert "USER" not in spec
        assert "TOKEN" not in spec
        assert "<redacted-credential>" in spec


# ---------------------------------------------------------------------------
# pyproject.toml parser
# ---------------------------------------------------------------------------

class TestParsePyprojectToml:
    def test_pep621_dependencies(self):
        content = (
            '[project]\n'
            'name = "x"\n'
            'dependencies = ["requests>=2.0", "flask==1.0", "numpy"]\n'
        )
        assert parse_pyproject_toml(content) == {
            "requests": ">=2.0",
            "flask": "==1.0",
            "numpy": "",
        }

    def test_pep621_optional_dependencies_namespaced(self):
        # Optional-deps are namespaced as "<name> [optional.<group>]" so
        # a package that appears in BOTH main and an extra (with different
        # specs) doesn't overwrite. Codex review MEDIUM #2.
        content = (
            '[project]\n'
            'name = "x"\n'
            'dependencies = ["requests"]\n'
            '[project.optional-dependencies]\n'
            'test = ["pytest==7.0"]\n'
        )
        result = parse_pyproject_toml(content)
        assert result == {
            "requests": "",
            "pytest [optional.test]": "==7.0",
        }

    def test_pep621_main_and_optional_no_collision(self):
        # Regression for Codex review MEDIUM #2: same package in main +
        # optional with different specs must both appear, neither overwritten.
        content = (
            '[project]\n'
            'name = "x"\n'
            'dependencies = ["requests==1.0"]\n'
            '[project.optional-dependencies]\n'
            'test = ["requests==2.0"]\n'
        )
        result = parse_pyproject_toml(content)
        assert result == {
            "requests": "==1.0",
            "requests [optional.test]": "==2.0",
        }

    def test_poetry_dependencies(self):
        content = (
            '[tool.poetry]\n'
            'name = "x"\n'
            '[tool.poetry.dependencies]\n'
            'python = "^3.10"\n'
            'requests = "^2.0"\n'
            'flask = "1.0"\n'
        )
        result = parse_pyproject_toml(content)
        # We intentionally include "python" -- a runtime bump is meaningful.
        assert result == {
            "python": "^3.10",
            "requests": "^2.0",
            "flask": "1.0",
        }

    def test_poetry_dev_dependencies_namespaced(self):
        content = (
            '[tool.poetry.dependencies]\n'
            'requests = "1.0"\n'
            '[tool.poetry.group.dev.dependencies]\n'
            'pytest = "7.0"\n'
        )
        result = parse_pyproject_toml(content)
        # Main deps unnamespaced; group deps tagged "[poetry.<group>]".
        assert result == {
            "requests": "1.0",
            "pytest [poetry.dev]": "7.0",
        }

    def test_poetry_dict_version_spec(self):
        # Poetry allows {version = "...", extras = [...], ...}.
        content = (
            '[tool.poetry.dependencies]\n'
            'requests = {version = "^2.0", extras = ["security"]}\n'
        )
        assert parse_pyproject_toml(content) == {"requests": "^2.0"}

    def test_invalid_toml_returns_empty(self):
        # Half-edited file mid-run -- must not crash.
        assert parse_pyproject_toml("[project\nname = ") == {}

    def test_empty_input(self):
        assert parse_pyproject_toml("") == {}

    def test_no_dep_sections(self):
        assert parse_pyproject_toml('[project]\nname = "x"\n') == {}


# ---------------------------------------------------------------------------
# package.json parser
# ---------------------------------------------------------------------------

class TestParsePackageJson:
    def test_dependencies(self):
        content = '{"dependencies": {"react": "^18.0.0", "lodash": "4.0.0"}}'
        assert parse_package_json(content) == {
            "react": "^18.0.0",
            "lodash": "4.0.0",
        }

    def test_dev_dependencies_namespaced(self):
        content = (
            '{"dependencies": {"react": "^18.0.0"},'
            ' "devDependencies": {"jest": "^29.0.0"}}'
        )
        result = parse_package_json(content)
        # devDependencies tagged so a package in both main and dev
        # with different specs doesn't overwrite.
        assert result == {
            "react": "^18.0.0",
            "jest [devDependencies]": "^29.0.0",
        }

    def test_peer_and_optional_ignored(self):
        # v1 scope: only dependencies + devDependencies. peer/optional
        # are different semantics; reporting them as added/removed would
        # be noisy.
        content = (
            '{"dependencies": {"a": "1"},'
            ' "peerDependencies": {"b": "1"},'
            ' "optionalDependencies": {"c": "1"}}'
        )
        assert parse_package_json(content) == {"a": "1"}

    def test_empty_object(self):
        assert parse_package_json("{}") == {}

    def test_invalid_json_returns_empty(self):
        assert parse_package_json("{not json") == {}

    def test_non_object_top_level_returns_empty(self):
        assert parse_package_json("[1, 2, 3]") == {}

    def test_non_string_versions_skipped(self):
        # Defensive: malformed manifests with non-string version values
        # must not crash; just skip those entries.
        content = '{"dependencies": {"a": "1", "b": 2, "c": null}}'
        assert parse_package_json(content) == {"a": "1"}

    def test_url_credentials_redacted(self):
        # Same HIGH #1 risk applies to npm git+url deps.
        content = (
            '{"dependencies":'
            ' {"x": "git+https://USER:TOKEN@host/repo.git"}}'
        )
        result = parse_package_json(content)
        assert "TOKEN" not in result["x"]
        assert "<redacted-credential>" in result["x"]


# ---------------------------------------------------------------------------
# Cross-parser URL credential redaction
# ---------------------------------------------------------------------------

class TestRedactUrlCreds:
    def test_https_basic_auth(self):
        assert _redact_url_creds("git+https://u:p@host/r.git") == (
            "git+https://<redacted-credential>@host/r.git"
        )

    def test_no_creds_unchanged(self):
        assert _redact_url_creds("==2.0.0") == "==2.0.0"
        assert _redact_url_creds("https://host/r.git") == "https://host/r.git"

    def test_only_userinfo_no_at_unchanged(self):
        # Defensive: ``host:port`` without an ``@`` is not credentials.
        assert _redact_url_creds("https://host:8080/r") == "https://host:8080/r"

    def test_idempotent(self):
        once = _redact_url_creds("git+https://u:p@host/r")
        assert _redact_url_creds(once) == once


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------

class TestSafePath:
    def test_simple_relative_ok(self):
        assert _is_safe_repo_relative_path("requirements.txt")
        assert _is_safe_repo_relative_path("nested/dir/requirements.txt")

    def test_empty_rejected(self):
        assert not _is_safe_repo_relative_path("")

    def test_parent_traversal_rejected(self):
        assert not _is_safe_repo_relative_path("../requirements.txt")
        assert not _is_safe_repo_relative_path("a/../b/requirements.txt")

    def test_posix_absolute_rejected(self):
        assert not _is_safe_repo_relative_path("/etc/requirements.txt")

    def test_windows_absolute_rejected(self):
        assert not _is_safe_repo_relative_path("C:/Windows/requirements.txt")
        assert not _is_safe_repo_relative_path("C:\\Windows\\requirements.txt")


# ---------------------------------------------------------------------------
# diff_dep_sets
# ---------------------------------------------------------------------------

class TestDiffDepSets:
    def test_added(self):
        changes = diff_dep_sets(
            before={"a": "1"}, after={"a": "1", "b": "2"},
            manifest_path="requirements.txt", ecosystem="pip",
        )
        assert changes == [
            DependencyChange(
                manifest_path="requirements.txt",
                ecosystem="pip",
                kind="added",
                name="b",
                old_version=None,
                new_version="2",
            ),
        ]

    def test_removed(self):
        changes = diff_dep_sets(
            before={"a": "1", "b": "2"}, after={"a": "1"},
            manifest_path="requirements.txt", ecosystem="pip",
        )
        assert changes == [
            DependencyChange(
                manifest_path="requirements.txt",
                ecosystem="pip",
                kind="removed",
                name="b",
                old_version="2",
                new_version=None,
            ),
        ]

    def test_version_changed(self):
        changes = diff_dep_sets(
            before={"a": "1"}, after={"a": "2"},
            manifest_path="requirements.txt", ecosystem="pip",
        )
        assert changes == [
            DependencyChange(
                manifest_path="requirements.txt",
                ecosystem="pip",
                kind="version_changed",
                name="a",
                old_version="1",
                new_version="2",
            ),
        ]

    def test_unchanged_emits_nothing(self):
        changes = diff_dep_sets(
            before={"a": "1"}, after={"a": "1"},
            manifest_path="requirements.txt", ecosystem="pip",
        )
        assert changes == []

    def test_all_three_kinds_sorted(self):
        # Output should be deterministic. We sort by (kind, name) so the
        # report renders the same way every time.
        changes = diff_dep_sets(
            before={"a": "1", "b": "1", "c": "1"},
            after={"a": "2", "b": "1", "d": "1"},
            manifest_path="m", ecosystem="pip",
        )
        kinds_names = [(c.kind, c.name) for c in changes]
        assert kinds_names == [
            ("added", "d"),
            ("removed", "c"),
            ("version_changed", "a"),
        ]


# ---------------------------------------------------------------------------
# scan_dependencies (end-to-end against tmp git repo)
# ---------------------------------------------------------------------------

def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _init_repo_with(tmp_path: Path, files: dict[str, str]) -> Path:
    """Create a tmp git repo and commit the given files."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t.t")
    _git(tmp_path, "config", "user.name", "T")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    for path, content in files.items():
        full = tmp_path / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


class TestScanDependencies:
    def test_added_dep_in_requirements(self, tmp_path):
        repo = _init_repo_with(
            tmp_path,
            {"requirements.txt": "requests==1.0\n"},
        )
        (repo / "requirements.txt").write_text(
            "requests==1.0\nnumpy==2.0\n"
        )
        changes = scan_dependencies(
            cwd=repo,
            changed_manifest_paths=["requirements.txt"],
        )
        assert len(changes) == 1
        c = changes[0]
        assert c.kind == "added"
        assert c.name == "numpy"
        assert c.new_version == "==2.0"
        assert c.ecosystem == "pip"

    def test_new_manifest_file_all_deps_added(self, tmp_path):
        # Manifest didn't exist at HEAD -- everything is "added".
        repo = _init_repo_with(tmp_path, {"README.md": "x\n"})
        (repo / "package.json").write_text(
            '{"dependencies": {"react": "^18.0"}}'
        )
        changes = scan_dependencies(
            cwd=repo,
            changed_manifest_paths=["package.json"],
        )
        assert len(changes) == 1
        assert changes[0].kind == "added"
        assert changes[0].name == "react"

    def test_deleted_manifest_all_deps_removed(self, tmp_path):
        repo = _init_repo_with(
            tmp_path,
            {"requirements.txt": "requests==1.0\n"},
        )
        (repo / "requirements.txt").unlink()
        changes = scan_dependencies(
            cwd=repo,
            changed_manifest_paths=["requirements.txt"],
        )
        assert len(changes) == 1
        assert changes[0].kind == "removed"
        assert changes[0].name == "requests"

    def test_non_manifest_file_ignored(self, tmp_path):
        repo = _init_repo_with(tmp_path, {"src/main.py": "x = 1\n"})
        (repo / "src/main.py").write_text("x = 2\n")
        changes = scan_dependencies(
            cwd=repo,
            changed_manifest_paths=["src/main.py"],
        )
        assert changes == []

    def test_empty_change_list(self, tmp_path):
        repo = _init_repo_with(tmp_path, {"README.md": "x\n"})
        assert scan_dependencies(cwd=repo, changed_manifest_paths=[]) == []

    def test_traversal_path_silently_dropped(self, tmp_path):
        # Codex review MEDIUM #4: ``..`` segment must not escape cwd.
        repo = _init_repo_with(tmp_path, {"README.md": "x\n"})
        changes = scan_dependencies(
            cwd=repo,
            changed_manifest_paths=["../requirements.txt"],
        )
        assert changes == []

    def test_absolute_path_silently_dropped(self, tmp_path):
        repo = _init_repo_with(tmp_path, {"README.md": "x\n"})
        changes = scan_dependencies(
            cwd=repo,
            changed_manifest_paths=["/etc/requirements.txt"],
        )
        assert changes == []

    def test_url_credentials_redacted_end_to_end(self, tmp_path):
        # Codex review HIGH #1: a credential present in a changed
        # manifest must NEVER reach the DependencyChange.new_version
        # surface (which is what the report renders).
        repo = _init_repo_with(
            tmp_path,
            {"requirements.txt": "# placeholder\nrequests==1.0\n"},
        )
        (repo / "requirements.txt").write_text(
            "requests==1.0\npkg @ git+https://USER:TOKEN@host/r.git\n"
        )
        changes = scan_dependencies(
            cwd=repo,
            changed_manifest_paths=["requirements.txt"],
        )
        added = [c for c in changes if c.kind == "added"]
        assert len(added) == 1
        spec = added[0].new_version or ""
        assert "TOKEN" not in spec
        assert "USER" not in spec
        assert "<redacted-credential>" in spec

    @pytest.mark.parametrize(
        "basename,ecosystem",
        [
            ("requirements.txt", "pip"),
            ("pyproject.toml", "python-project"),
            ("package.json", "npm"),
        ],
    )
    def test_ecosystem_label(self, tmp_path, basename, ecosystem):
        # Confirm we tag each manifest with the right ecosystem string.
        # Need plausible content for pyproject.toml and package.json so
        # the parser actually finds a dep to emit.
        before_content = {
            "requirements.txt": "a==1\n",
            "pyproject.toml": '[project]\nname="x"\ndependencies=["a==1"]\n',
            "package.json": '{"dependencies": {"a": "1"}}',
        }[basename]
        after_content = {
            "requirements.txt": "a==1\nb==1\n",
            "pyproject.toml": (
                '[project]\nname="x"\ndependencies=["a==1","b==1"]\n'
            ),
            "package.json": '{"dependencies": {"a": "1", "b": "1"}}',
        }[basename]
        repo = _init_repo_with(tmp_path, {basename: before_content})
        (repo / basename).write_text(after_content)
        changes = scan_dependencies(
            cwd=repo,
            changed_manifest_paths=[basename],
        )
        assert len(changes) == 1
        assert changes[0].ecosystem == ecosystem
