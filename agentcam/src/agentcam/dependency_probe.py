"""Dependency manifest probe.

Walks a list of changed manifest paths, compares each one's content at
HEAD against its content in the working tree, and emits a
:class:`~agentcam.models.DependencyChange` per added / removed /
version-bumped entry.

Scope (v1):
- pip ``requirements.txt``
- ``pyproject.toml`` (PEP 621 + Poetry, including dev/optional groups)
- npm ``package.json`` (``dependencies`` + ``devDependencies`` only;
  ``peerDependencies`` / ``optionalDependencies`` are intentionally
  excluded — their semantics differ enough that reporting them as
  added/removed would be noisy)

Out of scope (v1):
- Lockfiles (``package-lock.json``, ``poetry.lock``, ``uv.lock`` etc.) —
  most version bumps in lockfiles are transitive, low semantic value.
- ``Cargo.toml``, ``go.mod``, ``Gemfile``, etc. — easy to add later
  using the same parser→diff pattern.

Known limitation:
- "Before" content is read from HEAD via ``git show HEAD:<path>``.
  If the manifest was already modified before the wrapped run began
  (``pre_run_dirty=True``), the diff attributes pre-run user edits to
  the agent. The report renderer is responsible for noting this caveat
  alongside the dependency section.

All parsers tolerate malformed input by returning ``{}`` rather than
raising — a half-edited manifest mid-run must never crash the wrapped
process.
"""
from __future__ import annotations

import json
import re
import subprocess
import tomllib
from pathlib import Path, PurePosixPath
from typing import Callable

from agentcam.models import DependencyChange


# ---------------------------------------------------------------------------
# Shared safety helpers (apply to every parser before storing a spec)
# ---------------------------------------------------------------------------

# Strip `user:password@` from URLs embedded in a version spec. Pip,
# npm, and Poetry all accept `git+https://USER:TOKEN@host/...` as a
# dependency target; without this scrub, the credential would round-
# trip from the manifest into AGENT_RUN_REPORT.md (Codex review HIGH).
_URL_CREDS_RE = re.compile(
    r"([a-zA-Z][a-zA-Z0-9+.\-]*://)([^@/\s]+:[^@/\s]+)(@)"
)


def _redact_url_creds(spec: str) -> str:
    """Replace ``scheme://user:pass@`` with ``scheme://<redacted-credential>@``.

    Idempotent and cheap. We apply this at every parser boundary so the
    redacted string is what lands in :class:`DependencyChange`; nothing
    downstream (renderer, manifest, pickle) needs to know about
    credentials.
    """
    return _URL_CREDS_RE.sub(r"\1<redacted-credential>\3", spec)


# ---------------------------------------------------------------------------
# Manifest registry
# ---------------------------------------------------------------------------

# Map basename → (ecosystem label, parser). Order in the registry doesn't
# matter; we look up by basename per changed path.
_MANIFEST_REGISTRY: dict[str, tuple[str, Callable[[str], dict[str, str]]]] = {}


def _register(basename: str, ecosystem: str):
    def deco(fn: Callable[[str], dict[str, str]]):
        _MANIFEST_REGISTRY[basename] = (ecosystem, fn)
        return fn
    return deco


# ---------------------------------------------------------------------------
# requirements.txt parser
# ---------------------------------------------------------------------------

# A pip "requirement" line is: NAME [ '[' extras ']' ] [ version_spec ]
# We deliberately don't parse extras as separate items -- they're part of
# the install target identity; same extras both sides = same dep.
_REQ_NAME_RE = re.compile(
    r"^([A-Za-z0-9_.\-]+)(\[[^\]]*\])?(.*)$"
)

# pip's inline-comment rule: only "<whitespace>#..." is a comment.
# Bare "#" inside a URL fragment (e.g. ``git+https://h/r.git#egg=pkg``)
# is part of the spec. Codex review MEDIUM #3.
_REQ_INLINE_COMMENT_RE = re.compile(r"\s+#.*$")


@_register("requirements.txt", "pip")
def parse_requirements_txt(content: str) -> dict[str, str]:
    """Parse a pip ``requirements.txt`` into {name(+extras): version_spec}.

    Behavior:
    - Comments: a whole-line ``# ...`` is ignored. Inline comments
      require a whitespace separator (matching pip's own behavior),
      so URL fragments like ``#egg=pkg`` survive intact.
    - Directives (``-r``, ``-e``, ``--editable``, ``--index-url``, ...):
      skipped; they don't name a single package we can diff.
    - Environment markers (``pkg; python_version<'3.11'``): the marker
      is stripped from the version spec we report.
    - Extras (``pkg[security]``): kept as part of the dict key, so the
      diff still notices when ``pkg[security]`` becomes ``pkg``.
    - URL credentials (``git+https://USER:TOKEN@...``): scrubbed at this
      boundary; the report can never see them.
    """
    result: dict[str, str] = {}
    for raw in content.splitlines():
        stripped = raw.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        # Inline comment requires whitespace before `#`; preserves URL fragments.
        line = _REQ_INLINE_COMMENT_RE.sub("", raw).strip()
        if not line:
            continue
        if line.startswith("-"):
            continue
        # Strip env markers; we don't model them.
        line = line.split(";", 1)[0].strip()
        if not line:
            continue
        m = _REQ_NAME_RE.match(line)
        if not m:
            continue
        name = m.group(1)
        extras = m.group(2) or ""
        spec = (m.group(3) or "").strip()
        result[name + extras] = _redact_url_creds(spec)
    return result


# ---------------------------------------------------------------------------
# pyproject.toml parser
# ---------------------------------------------------------------------------

@_register("pyproject.toml", "python-project")
def parse_pyproject_toml(content: str) -> dict[str, str]:
    """Parse PEP 621 ``[project]`` deps + Poetry deps.

    Sections collected:
    - ``project.dependencies`` (PEP 621 array of PEP 508 strings)
    - ``project.optional-dependencies.<extra>`` (PEP 621)
    - ``tool.poetry.dependencies`` (Poetry, dict form)
    - ``tool.poetry.group.<group>.dependencies`` (Poetry 1.2+)
    - ``tool.poetry.dev-dependencies`` (Poetry <1.2 legacy)

    Poetry's "python" entry IS included -- a runtime bump is meaningful
    and the report should flag it.
    """
    if not content.strip():
        return {}
    try:
        data = tomllib.loads(content)
    except (tomllib.TOMLDecodeError, ValueError):
        # Half-edited / invalid toml -- degrade quietly.
        return {}
    if not isinstance(data, dict):
        return {}

    result: dict[str, str] = {}

    # PEP 621.
    project = data.get("project")
    if isinstance(project, dict):
        deps = project.get("dependencies")
        if isinstance(deps, list):
            _absorb_pep508_list(deps, result, group=None)
        opt = project.get("optional-dependencies")
        if isinstance(opt, dict):
            # Codex review MEDIUM #2: namespace optional-deps so a
            # package that appears in both main and an extra (with
            # different specs) doesn't silently overwrite.
            for group_name, group_deps in opt.items():
                if isinstance(group_deps, list):
                    _absorb_pep508_list(
                        group_deps, result,
                        group=f"optional.{group_name}",
                    )

    # Poetry.
    poetry = (data.get("tool") or {}).get("poetry") if isinstance(
        data.get("tool"), dict
    ) else None
    if isinstance(poetry, dict):
        _absorb_poetry_deps(poetry.get("dependencies"), result, group=None)
        _absorb_poetry_deps(
            poetry.get("dev-dependencies"), result,
            group="poetry.dev-dependencies",
        )
        groups = poetry.get("group")
        if isinstance(groups, dict):
            for group_name, group in groups.items():
                if isinstance(group, dict):
                    _absorb_poetry_deps(
                        group.get("dependencies"), result,
                        group=f"poetry.{group_name}",
                    )

    return result


def _ns_key(base: str, group: str | None) -> str:
    """Append a ``[group]`` suffix when the dep belongs to a named group.

    Suffix uses ``" ["`` so it cannot collide with PEP 508 names
    (names match ``[A-Za-z0-9._-]+``).
    """
    return f"{base} [{group}]" if group else base


def _absorb_pep508_list(deps: list, out: dict[str, str], *, group: str | None) -> None:
    """Parse a list of PEP 508 strings into the output dict.

    ``group`` namespaces the resulting keys when the deps come from
    ``optional-dependencies.<group>``; pass ``None`` for main deps.
    """
    for entry in deps:
        if not isinstance(entry, str):
            continue
        # PEP 508 spec is rich (markers, urls, extras). We use the same
        # name+spec extraction as requirements.txt; close enough for v1.
        spec_line = entry.split(";", 1)[0].strip()
        m = _REQ_NAME_RE.match(spec_line)
        if not m:
            continue
        name = m.group(1)
        extras = m.group(2) or ""
        spec = (m.group(3) or "").strip()
        out[_ns_key(name + extras, group)] = _redact_url_creds(spec)


def _absorb_poetry_deps(node, out: dict[str, str], *, group: str | None) -> None:
    """Absorb Poetry's deps-table form (dict of name → str|dict spec).

    ``group`` namespaces keys for ``dev-dependencies`` and
    ``group.<name>.dependencies``; pass ``None`` for main deps.
    """
    if not isinstance(node, dict):
        return
    for name, spec in node.items():
        key = _ns_key(name, group)
        if isinstance(spec, str):
            out[key] = _redact_url_creds(spec)
        elif isinstance(spec, dict):
            # Poetry table form: {version = "...", extras = [...], ...}.
            v = spec.get("version")
            out[key] = _redact_url_creds(v) if isinstance(v, str) else ""


# ---------------------------------------------------------------------------
# package.json parser
# ---------------------------------------------------------------------------

@_register("package.json", "npm")
def parse_package_json(content: str) -> dict[str, str]:
    """Parse npm ``dependencies`` + ``devDependencies`` into {name: spec}.

    ``peerDependencies`` / ``optionalDependencies`` are intentionally
    excluded -- different semantics (see module docstring).
    """
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    result: dict[str, str] = {}
    for section, group in (
        ("dependencies", None),
        ("devDependencies", "devDependencies"),
    ):
        node = data.get(section)
        if not isinstance(node, dict):
            continue
        for name, spec in node.items():
            if isinstance(name, str) and isinstance(spec, str):
                result[_ns_key(name, group)] = _redact_url_creds(spec)
    return result


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------

def diff_dep_sets(
    *,
    before: dict[str, str],
    after: dict[str, str],
    manifest_path: str,
    ecosystem: str,
) -> list[DependencyChange]:
    """Produce ``DependencyChange`` entries for one manifest.

    Output is sorted by (kind, name) so the report renders
    deterministically. Kinds appear in alphabetical order
    (``added`` < ``removed`` < ``version_changed``).
    """
    changes: list[DependencyChange] = []

    before_keys = set(before)
    after_keys = set(after)

    for name in sorted(after_keys - before_keys):
        changes.append(DependencyChange(
            manifest_path=manifest_path,
            ecosystem=ecosystem,
            kind="added",
            name=name,
            old_version=None,
            new_version=after[name],
        ))
    for name in sorted(before_keys - after_keys):
        changes.append(DependencyChange(
            manifest_path=manifest_path,
            ecosystem=ecosystem,
            kind="removed",
            name=name,
            old_version=before[name],
            new_version=None,
        ))
    for name in sorted(before_keys & after_keys):
        if before[name] != after[name]:
            changes.append(DependencyChange(
                manifest_path=manifest_path,
                ecosystem=ecosystem,
                kind="version_changed",
                name=name,
                old_version=before[name],
                new_version=after[name],
            ))

    return changes


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def _git_show_head(cwd: Path, path: str) -> str | None:
    """Read ``path``'s content at HEAD via ``git show``. None if absent.

    Used for the "before" side of the diff. Returns None if the file
    doesn't exist at HEAD (newly created manifest) or if any git error
    happens; either way, the caller treats the before-side as empty.
    """
    res = subprocess.run(
        ["git", "show", f"HEAD:{path}"],
        cwd=cwd,
        capture_output=True,
        check=False,
    )
    if res.returncode != 0:
        return None
    return res.stdout.decode("utf-8", errors="replace")


def _read_working_tree(cwd: Path, path: str) -> str | None:
    """Read ``path`` from the working tree. None if absent."""
    try:
        return (cwd / path).read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError):
        return None


def _is_safe_repo_relative_path(path: str) -> bool:
    """True iff ``path`` is a clean repo-relative path.

    Rejects:
    - absolute paths (POSIX ``/`` or Windows drive-letter)
    - any ``..`` segment (parent traversal)
    - empty string

    Codex review MEDIUM #4: ``scan_dependencies`` is a public function;
    callers that pass externally-derived paths must not be able to
    coax us into reading outside the repo.
    """
    if not path:
        return False
    norm = path.replace("\\", "/")
    p = PurePosixPath(norm)
    if p.is_absolute() or (len(norm) >= 2 and norm[1] == ":"):
        return False
    if ".." in p.parts:
        return False
    return True


def scan_dependencies(
    *,
    cwd: Path,
    changed_manifest_paths: list[str],
) -> list[DependencyChange]:
    """Walk ``changed_manifest_paths`` and produce dependency changes.

    Only entries whose basename appears in ``_MANIFEST_REGISTRY`` are
    parsed; unknown paths are silently ignored. Each known manifest is
    parsed at HEAD and at the working tree, then diffed. Output is the
    concatenation of per-manifest diffs in input order.

    Path safety: paths with ``..`` segments or absolute paths are
    silently dropped so a caller cannot read outside the repo. Caller
    is otherwise responsible for filtering down to actual manifest
    paths if it wants efficiency; this function is cheap enough to
    call with the full ``changed_files`` list, since unknown basenames
    short-circuit on registry lookup.
    """
    all_changes: list[DependencyChange] = []
    for path in changed_manifest_paths:
        if not _is_safe_repo_relative_path(path):
            continue
        basename = Path(path).name
        entry = _MANIFEST_REGISTRY.get(basename)
        if entry is None:
            continue
        ecosystem, parser = entry

        before_text = _git_show_head(cwd, path) or ""
        after_text = _read_working_tree(cwd, path) or ""

        before_deps = parser(before_text)
        after_deps = parser(after_text)

        all_changes.extend(diff_dep_sets(
            before=before_deps,
            after=after_deps,
            manifest_path=path,
            ecosystem=ecosystem,
        ))
    return all_changes


def known_manifest_basenames() -> frozenset[str]:
    """Public accessor for the set of manifest basenames we recognize."""
    return frozenset(_MANIFEST_REGISTRY.keys())
