"""Git state collection (before and after the wrapped command).

Uses ``git status --porcelain=v1 -z`` as the primary source of truth, with
``git diff [--cached] --stat / --name-status / --check`` for display in the
report. See plan section 4.

``git_dir`` is resolved via ``git rev-parse --git-dir`` so worktree and
submodule gitlink cases (where ``<repo>/.git`` is a file, not a directory)
work correctly. See plan section 1.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import replace
from pathlib import Path

from agentcam.models import ChangedFile, ChangeStatus, GitState

# Order matters: the first matching marker wins. ``rebase-merge`` and
# ``rebase-apply`` are checked before ``REVERT_HEAD`` etc.
_PRE_EXISTING_OP_MARKERS: tuple[tuple[str, str], ...] = (
    ("MERGE_HEAD", "merge"),
    ("rebase-merge", "rebase"),
    ("rebase-apply", "rebase"),
    ("CHERRY_PICK_HEAD", "cherry-pick"),
    ("REVERT_HEAD", "revert"),
    ("BISECT_LOG", "bisect"),
)


class NotAGitRepoError(RuntimeError):
    """Raised when the cwd is not inside a git repository."""


def is_git_repo(cwd: Path) -> bool:
    return _git(cwd, "rev-parse", "--git-dir", check=False).returncode == 0


def resolve_git_dir(cwd: Path) -> Path:
    """Absolute path of the real git directory.

    ``git rev-parse --git-dir`` resolves worktree / submodule gitlink files
    for us, so we never have to read or parse ``<repo>/.git`` ourselves.
    """
    text = _git_text(cwd, "rev-parse", "--git-dir")
    p = Path(text)
    if not p.is_absolute():
        p = (cwd / p).resolve()
    return p


def resolve_git_root(cwd: Path) -> Path:
    """Absolute path of the working tree root."""
    return Path(_git_text(cwd, "rev-parse", "--show-toplevel"))


def detect_pre_existing_op(git_dir: Path) -> str | None:
    """Return operation name (merge / rebase / cherry-pick / etc.) or None."""
    for filename, op in _PRE_EXISTING_OP_MARKERS:
        if (git_dir / filename).exists():
            return op
    return None


def collect_git_state(cwd: Path, *, is_after: bool = False) -> GitState:
    """Snapshot git state. ``is_after=True`` also runs ``git diff --check``."""
    if not is_git_repo(cwd):
        raise NotAGitRepoError(
            "Not in a git repository. Initialize one with 'git init' first."
        )

    git_dir = resolve_git_dir(cwd)

    head = _safe_head(cwd)
    branch_raw = _git_text(cwd, "branch", "--show-current")
    branch = branch_raw or None
    is_detached = head is not None and not branch

    porcelain_raw = _git(cwd, "status", "--porcelain=v1", "-z").stdout
    diff_stat = _git_text(cwd, "diff", "--stat", check=False)
    diff_stat_cached = _git_text(cwd, "diff", "--cached", "--stat", check=False)
    diff_name_status = _git_text(cwd, "diff", "--name-status", check=False)
    diff_name_status_cached = _git_text(
        cwd, "diff", "--cached", "--name-status", check=False
    )

    diff_check = ""
    diff_check_cached = ""
    if is_after:
        diff_check = _git_text(cwd, "diff", "--check", check=False)
        diff_check_cached = _git_text(
            cwd, "diff", "--cached", "--check", check=False
        )

    pre_existing_op = detect_pre_existing_op(git_dir)
    changed_files = parse_porcelain_v1z(porcelain_raw)
    path_signatures = {
        changed.path: _path_signature(cwd, changed.path)
        for changed in changed_files
    }

    return GitState(
        head=head,
        branch=branch,
        is_detached_head=is_detached,
        porcelain_raw=porcelain_raw,
        diff_stat=diff_stat,
        diff_stat_cached=diff_stat_cached,
        diff_name_status=diff_name_status,
        diff_name_status_cached=diff_name_status_cached,
        diff_check=diff_check,
        diff_check_cached=diff_check_cached,
        pre_existing_op=pre_existing_op,
        changed_files=changed_files,
        path_signatures=path_signatures,
    )


def compute_diff_fingerprint(cwd: Path) -> str:
    """sha256 hex digest of the working tree's git-visible state.

    Hashes:
    (1) `git diff` — content changes to tracked files in the working tree
    (2) `git diff --cached` — staged changes
    (3) Each untracked file's (path + content), via
        :func:`_untracked_content_hash`

    Called by cli.py *only* when no-diff cleanup might actually fire
    (i.e. `--keep-empty` is not set). Computing this requires one
    `git diff` + one `git diff --cached` + one `git ls-files` + a read
    of every untracked file's bytes, so it is non-trivial cost for
    repos with large unignored artifacts.
    """
    fp = hashlib.sha256()
    fp.update(_git(cwd, "diff", check=False).stdout)
    fp.update(b"\x00")
    fp.update(_git(cwd, "diff", "--cached", check=False).stdout)
    fp.update(b"\x00")
    fp.update(_untracked_content_hash(cwd))
    return fp.hexdigest()


def compute_final_state_fingerprint(cwd: Path) -> str:
    """Bind a verification to the exact HEAD plus dirty/index/untracked state."""
    fp = hashlib.sha256()
    fp.update((_safe_head(cwd) or "<no-head>").encode("ascii", errors="replace"))
    fp.update(b"\x00")
    fp.update(compute_diff_fingerprint(cwd).encode("ascii"))
    return fp.hexdigest()


def read_declared_scope(cwd: Path) -> list[str]:
    """Read the corridor Paths snapshot without importing Slime's hook script."""
    path = cwd / ".slime" / "corridor.md"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    in_paths = False
    scope: list[str] = []
    for raw in lines:
        line = raw.strip()
        if line.lower() == "## paths":
            in_paths = True
            continue
        if in_paths and line.startswith("##"):
            break
        if in_paths:
            match = re.match(r"-\s+(.+)", line)
            if match:
                value = match.group(1).strip().strip("`")
                if value and value not in scope:
                    scope.append(value.replace("\\", "/"))
    return scope


def derive_turn_delta(cwd: Path, before: GitState, after: GitState) -> GitState:
    """Return ``after`` with changed_files narrowed to this run's delta."""
    by_path: dict[str, ChangedFile] = {}
    after_files = {changed.path: changed for changed in after.changed_files}
    signature_paths = set(before.path_signatures) | set(after.path_signatures)
    for path in signature_paths:
        if before.path_signatures.get(path) == after.path_signatures.get(path):
            continue
        changed = after_files.get(path)
        by_path[path] = changed or ChangedFile(path=path, status="restored")

    if before.head and after.head and before.head != after.head:
        for changed in _committed_changes(cwd, before.head, after.head):
            by_path[changed.path] = changed

    return replace(after, changed_files=sorted(by_path.values(), key=lambda item: item.path))


def compute_product_fingerprint(cwd: Path, changed_files: list[ChangedFile]) -> str:
    """Hash final content/status for the run delta, independent of commit SHA."""
    fp = hashlib.sha256()
    for changed in sorted(changed_files, key=lambda item: item.path):
        fp.update(changed.path.encode("utf-8", errors="surrogateescape"))
        fp.update(b"\x00")
        fp.update(changed.status.encode("ascii"))
        fp.update(b"\x00")
        fp.update((changed.rename_from or "").encode("utf-8", errors="surrogateescape"))
        fp.update(b"\x00")
        absolute = cwd / changed.path
        try:
            if absolute.is_symlink():
                content = b"symlink:" + os.readlink(absolute).encode(
                    "utf-8", errors="surrogateescape"
                )
            else:
                content = absolute.read_bytes()
            fp.update(hashlib.sha256(content).digest())
        except OSError:
            fp.update(b"<missing>")
        fp.update(b"\x00")
    return fp.hexdigest()


def _path_signature(cwd: Path, path: str) -> str:
    fp = hashlib.sha256()
    index = _git(cwd, "ls-files", "--stage", "-z", "--", path, check=False)
    fp.update(index.stdout if index.returncode == 0 else b"<index-error>")
    fp.update(b"\x00")
    absolute = cwd / path
    try:
        if absolute.is_symlink():
            fp.update(b"symlink:")
            fp.update(os.readlink(absolute).encode("utf-8", errors="surrogateescape"))
        else:
            fp.update(hashlib.sha256(absolute.read_bytes()).digest())
    except OSError:
        fp.update(b"<missing>")
    return fp.hexdigest()


def _committed_changes(cwd: Path, before: str, after: str) -> list[ChangedFile]:
    result = _git(cwd, "diff", "--name-status", "-z", f"{before}..{after}", check=False)
    if result.returncode != 0:
        return []
    tokens = [token for token in result.stdout.split(b"\x00") if token]
    changes: list[ChangedFile] = []
    index = 0
    while index < len(tokens):
        status = tokens[index].decode("ascii", errors="replace")
        index += 1
        if index >= len(tokens):
            break
        if status.startswith(("R", "C")):
            old_path = tokens[index].decode("utf-8", errors="replace")
            index += 1
            if index >= len(tokens):
                break
            new_path = tokens[index].decode("utf-8", errors="replace")
            index += 1
            changes.append(
                ChangedFile(path=new_path, status="renamed", rename_from=old_path)
            )
            continue
        path = tokens[index].decode("utf-8", errors="replace")
        index += 1
        changes.append(
            ChangedFile(
                path=path,
                status="committed_deleted" if status.startswith("D") else "committed",
            )
        )
    return changes


def is_working_tree_dirty(state: GitState) -> bool:
    """True if there are any staged, unstaged, or untracked changes."""
    return bool(state.changed_files)


# ---------------------------------------------------------------------------
# Untracked content hashing (for the no-diff fingerprint)
# ---------------------------------------------------------------------------

def _untracked_content_hash(cwd: Path) -> bytes:
    """Hash all untracked files (path + content bytes) for fingerprinting.

    Why: `git diff` and `git diff --cached` ignore untracked files. Without
    this, a pre-existing untracked file rewritten in place by the wrapped
    command produces identical diff bytes pre/post and identical porcelain
    output ("?? path"), causing a false no-diff cleanup — agent's work is
    lost. Respects `.gitignore` via `--exclude-standard`.

    Performance: O(N) reads, where N is the count of untracked files NOT
    matched by .gitignore. For repos with large unignored artifacts this
    is slow; the escape hatch is `agentcam run --keep-empty`.

    On `git ls-files` failure (rare; git binary issue / weird repo state),
    returns a per-call unique sentinel so the pre/post fingerprints
    cannot collide silently — caller falls through to keep the report.
    Codex round-2 review caught this hole; previously returned b"".
    """
    import os
    res = _git(cwd, "ls-files", "--others", "--exclude-standard", "-z",
               check=False)
    if res.returncode != 0:
        return (
            b"<LS-FILES-FAILED rc=" + str(res.returncode).encode()
            + b" nonce=" + os.urandom(16).hex().encode() + b">"
        )
    paths = sorted(p for p in res.stdout.split(b"\x00") if p)
    fp = hashlib.sha256()
    for path_bytes in paths:
        fp.update(path_bytes)
        fp.update(b"\x00")
        try:
            # surrogateescape preserves non-UTF8 byte paths on POSIX
            # (planned POSIX hardening — caveat 2).
            path_str = path_bytes.decode("utf-8", errors="surrogateescape")
            content = (cwd / path_str).read_bytes()
            fp.update(hashlib.sha256(content).digest())
        except OSError:
            # File disappeared between ls-files and read, or unreadable.
            # Sentinel so different missing files don't collide silently.
            fp.update(b"<MISSING>")
        fp.update(b"\x00")
    return fp.digest()


# ---------------------------------------------------------------------------
# Porcelain v1 -z parser
# ---------------------------------------------------------------------------

def parse_porcelain_v1z(data: bytes) -> list[ChangedFile]:
    """Parse ``git status --porcelain=v1 -z`` output.

    Each entry is ``XY<space><path>\\x00``. R/C (rename / copy) entries take
    two NUL-separated fields: ``XY<space><new>\\x00<old>\\x00``.
    """
    if not data:
        return []

    tokens = data.split(b"\x00")
    results: list[ChangedFile] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if not tok:
            i += 1
            continue
        if len(tok) < 3:
            # Malformed entry; skip defensively rather than crash.
            i += 1
            continue
        x = chr(tok[0])
        y = chr(tok[1])
        # tok[2] is the separator (typically a space). Path bytes start at 3.
        path = tok[3:].decode("utf-8", errors="replace")
        rename_from: str | None = None
        if x in ("R", "C") or y in ("R", "C"):
            i += 1
            if i < len(tokens):
                rename_from = tokens[i].decode("utf-8", errors="replace")
        status = _classify_status(x, y)
        results.append(
            ChangedFile(path=path, status=status, rename_from=rename_from)
        )
        i += 1
    return results


def _classify_status(x: str, y: str) -> ChangeStatus:
    xy = x + y
    if xy == "??":
        return "untracked"
    if x == "U" or y == "U" or xy in ("AA", "DD"):
        return "unmerged"
    if x in ("R", "C") or y in ("R", "C"):
        return "renamed"
    if x != " " and x not in ("?", "!"):
        if x == "D":
            return "staged_deleted"
        return "staged"
    if y == "M":
        return "unstaged_modified"
    if y == "D":
        return "unstaged_deleted"
    # Defensive fallback.
    return "unstaged_modified"


# ---------------------------------------------------------------------------
# Low-level git helpers
# ---------------------------------------------------------------------------

def _git(
    cwd: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        check=check,
    )


def _git_text(cwd: Path, *args: str, check: bool = True) -> str:
    res = _git(cwd, *args, check=check)
    return res.stdout.decode("utf-8", errors="replace").rstrip("\n")


def _safe_head(cwd: Path) -> str | None:
    """Return HEAD SHA, or None if HEAD does not resolve (empty repo)."""
    res = _git(cwd, "rev-parse", "HEAD", check=False)
    if res.returncode != 0:
        return None
    return res.stdout.decode("utf-8", errors="replace").strip() or None
