#!/usr/bin/env python3
"""Corridor CI: keep incoming PR changes inside a declared review corridor."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable


DEPENDENCY_GLOBS = (
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "bun.lock",
    "requirements.txt",
    "requirements-*.txt",
    "pyproject.toml",
    "poetry.lock",
    "Pipfile",
    "Pipfile.lock",
    "Cargo.toml",
    "Cargo.lock",
    "go.mod",
    "go.sum",
    "Gemfile",
    "Gemfile.lock",
)

COMPACT_HANDOFF_LABELS = ("Decision", "Scope", "Review first", "Verified", "Risk")
HANDOFF_PLACEHOLDERS = {"n/a", "not set", "tbd", "todo"}

COPYABLE_REVIEW_HANDOFF = """Decision: <fill in: issue, discussion, or short decision>
Scope: <fill in: repo-relative path or glob>
Review first: <fill in: changed file>
Verified: <fill in: completed command or manual check>
Risk: <fill in: high, medium, none-detected, or unknown>
"""

COMMENT_MARKER = "<!-- corridor-ci -->"
WORKFLOW_APPROVAL_LABEL = "Guardrails-Workflow-Approval"
DEPENDENCY_APPROVAL_LABEL = "Guardrails-Dependency-Approval"
WORKFLOW_PREFIX = ".github/workflows/"
SCOPE_METADATA_PATHS = {
    ".agentcam/AGENT_RUN_REPORT.md",
    ".agentcam/manifest.redacted.json",
}
MANIFEST_MAX_BYTES = 1024 * 1024
RISK_VALUES = {"high", "medium", "none-detected", "unknown"}
GITHUB_API_URL = "https://api.github.com"
HttpTransport = Callable[[str, str, str, dict[str, str] | None], Any]


@dataclass
class Report:
    ok: bool
    changed_files: list[str]
    allowed_paths: list[str]
    handoff: dict[str, str]
    outside_files: list[str]
    dependency_files: list[str]
    issues: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class VerificationProvenance:
    status: str
    partial: bool
    warnings: list[str]


@dataclass(frozen=True)
class WorkflowPolicyDecision:
    ok: bool
    changed_workflows: list[str]
    approved_by: str | None
    reason: str


@dataclass(frozen=True)
class DependencyPolicyDecision:
    ok: bool
    dependency_files: list[str]
    approved_by: str | None
    reason: str


def normalize_path(path: str) -> str:
    cleaned = path.strip().replace("\\", "/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned


def escape_markdown(value: Any) -> str:
    """Render author-controlled scalar content without Markdown structure."""
    text = html.escape(str(value), quote=False).replace("\r", " ").replace("\n", "<br>")
    text = text.replace("`", "&#96;")
    return re.sub(r"([\\*_{}\[\]|>])", r"\\\1", text).replace(
        "@", "@\u200b"
    )


def truthy(value: str | bool | None) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def normalize_heading(text: str) -> str:
    return " ".join(text.strip().strip("#").strip().lower().replace("_", " ").split())


def handoff_field_labels() -> dict[str, str]:
    return {normalize_heading(label): label for label in COMPACT_HANDOFF_LABELS}


def decorated_field_candidates(stripped: str) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []

    bold_colon_inside = re.match(r"^\*\*(?P<key>[^:\n*][^:\n]*?):\*\*", stripped)
    if bold_colon_inside:
        candidates.append((bold_colon_inside.group("key").strip(), bold_colon_inside.group(0)))

    bold_colon_outside = re.match(r"^\*\*(?P<key>[^*\n]+?)\*\*:", stripped)
    if bold_colon_outside:
        candidates.append((bold_colon_outside.group("key").strip(), bold_colon_outside.group(0)))

    bullet = re.match(r"^(?P<bullet>[-*+])\s+(?P<key>[^:\n]+):", stripped)
    if bullet:
        token = f"{bullet.group('bullet')} {bullet.group('key').strip()}:"
        candidates.append((bullet.group("key").strip(), token))

    heading = re.match(r"^(?P<hashes>#{1,6})\s+(?P<rest>.+)$", stripped)
    if heading:
        rest = heading.group("rest").strip()
        if ":" in rest:
            key = rest.split(":", 1)[0].strip()
            token = f"{heading.group('hashes')} {key}:"
        else:
            key = rest
            token = f"{heading.group('hashes')} {key}"
        candidates.append((key, token))

    return candidates


def iter_visible_lines(text: str):
    """Yield lines that are outside fenced code blocks.

    PR bodies routinely carry a fenced handoff *example* — the template
    seeds one, and corridor-ci's own failure comment offers a copyable
    block. Since field parsing is first-non-empty-value-wins, a fenced example
    would otherwise shadow the author's real handoff below it.
    """
    fence: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        marker = None
        if stripped.startswith("```"):
            marker = "```"
        elif stripped.startswith("~~~"):
            marker = "~~~"
        if marker is not None:
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            continue
        if fence is None:
            yield line


def detect_near_miss_fields(corridor_text: str | None) -> dict[str, str]:
    near_misses: dict[str, str] = {}
    if not corridor_text:
        return near_misses

    labels = handoff_field_labels()
    for line in iter_visible_lines(corridor_text):
        stripped = line.strip()
        if not stripped:
            continue
        for key, token in decorated_field_candidates(stripped):
            label = labels.get(normalize_heading(key))
            if label and label not in near_misses:
                near_misses[label] = token
                break
    return near_misses


def extract_compact_handoff(corridor_text: str | None) -> dict[str, str]:
    handoff = {label: "" for label in COMPACT_HANDOFF_LABELS}
    if not corridor_text:
        return handoff

    labels = handoff_field_labels()
    for line in iter_visible_lines(corridor_text):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        label = labels.get(normalize_heading(key))
        if label and value.strip() and not handoff[label]:
            handoff[label] = value.strip()
    return handoff


def read_event_payload() -> dict[str, Any]:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        return {}
    try:
        return json.loads(Path(event_path).read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def find_pr_body() -> str | None:
    event = read_event_payload()
    pull = event.get("pull_request") or {}
    return pull.get("body")


def find_pr_number() -> str | None:
    event = read_event_payload()
    pull = event.get("pull_request") or {}
    number = pull.get("number") or event.get("number")
    return str(number) if number else None


def rev_exists(repo: Path, rev: str) -> bool:
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", rev],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def diff_base(repo: Path) -> str:
    base = os.environ.get("GITHUB_BASE_REF")
    candidates: list[str]
    if base:
        candidates = [base] if base.startswith("origin/") else [f"origin/{base}", base]
    else:
        candidates = ["origin/main", "main"]
    for candidate in candidates:
        if rev_exists(repo, candidate):
            return candidate
    return candidates[-1]


def extract_changed_files(repo: Path) -> list[str]:
    base = diff_base(repo)
    return extract_changed_files_between(repo, base, "HEAD")


def extract_changed_files_between(repo: Path, base: str, head: str) -> list[str]:
    # core.quotepath=false: git's default C-quoting turns non-ASCII paths
    # into "src/caf\303\251.py", which can never match a declared Scope
    # pattern, so such files would always be flagged outside the corridor.
    # encoding="utf-8": git emits UTF-8 path bytes; text=True alone decodes
    # with the locale codepage (e.g. cp936 on Chinese Windows), which turns
    # "caf\303\251" into mojibake and re-opens the same false-block.
    proc = subprocess.run(
        ["git", "-c", "core.quotepath=false", "diff", "--name-only", f"{base}...{head}"],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise SystemExit(f"failed to read changed files: {proc.stderr.strip()}")
    return [normalize_path(p) for p in proc.stdout.splitlines() if p.strip()]


def compute_current_product_fingerprint(repo: Path, changed_files: list[str]) -> str:
    """Hash final delivered product paths/content, excluding fixed evidence files."""
    fingerprint = hashlib.sha256()
    for path in sorted(
        {normalize_path(value) for value in changed_files} - SCOPE_METADATA_PATHS
    ):
        fingerprint.update(path.encode("utf-8", errors="surrogateescape"))
        fingerprint.update(b"\x00")
        absolute = repo / path
        try:
            if absolute.is_symlink():
                content = b"symlink:" + os.readlink(absolute).encode(
                    "utf-8", errors="surrogateescape"
                )
            else:
                content = absolute.read_bytes()
            fingerprint.update(hashlib.sha256(content).digest())
        except OSError:
            fingerprint.update(b"<missing>")
        fingerprint.update(b"\x00")
    return fingerprint.hexdigest()


def evaluate_workflow_policy(
    *,
    changed_files: list[str],
    comments: list[Any],
    head_sha: str,
    pr_author: str,
) -> WorkflowPolicyDecision:
    """Require an external, head-bound approval for active workflow edits.

    The approval is GitHub state, not PR-controlled text.  OWNER may approve
    their own PR for single-maintainer repositories; MEMBER approval must come
    from someone other than the PR author.  Any new commit changes ``head_sha``
    and invalidates the approval.
    """
    changed_workflows = sorted(
        path
        for path in {normalize_path(p) for p in changed_files}
        if path.startswith(WORKFLOW_PREFIX)
    )
    if not changed_workflows:
        return WorkflowPolicyDecision(
            ok=True,
            changed_workflows=[],
            approved_by=None,
            reason="No active workflow files changed.",
        )

    normalized_head = head_sha.strip().lower()
    approval_pattern = re.compile(
        rf"(?m)^{re.escape(WORKFLOW_APPROVAL_LABEL)}:\s*"
        rf"({re.escape(normalized_head)})\s*$"
    )
    normalized_author = pr_author.strip().lower()
    for comment in comments if isinstance(comments, list) else []:
        if not isinstance(comment, dict):
            continue
        body = comment.get("body")
        association = str(comment.get("author_association") or "").upper()
        user = comment.get("user")
        login = str(user.get("login") or "") if isinstance(user, dict) else ""
        if not isinstance(body, str) or not approval_pattern.search(body):
            continue
        if association == "OWNER" or (
            association == "MEMBER" and login.strip().lower() != normalized_author
        ):
            return WorkflowPolicyDecision(
                ok=True,
                changed_workflows=changed_workflows,
                approved_by=login or association.lower(),
                reason=f"Workflow change approved for head {normalized_head}.",
            )

    return WorkflowPolicyDecision(
        ok=False,
        changed_workflows=changed_workflows,
        approved_by=None,
        reason=(
            "Active workflow files changed without a trusted approval for the "
            f"current head. Add an exact PR comment: {WORKFLOW_APPROVAL_LABEL}: "
            f"{normalized_head}"
        ),
    )


def evaluate_dependency_policy(
    *,
    dependency_files: list[str],
    comments: list[Any],
    head_sha: str,
    pr_author: str,
) -> DependencyPolicyDecision:
    dependencies = sorted({normalize_path(path) for path in dependency_files})
    if not dependencies:
        return DependencyPolicyDecision(True, [], None, "No dependency files changed.")

    normalized_head = head_sha.strip().lower()
    pattern = re.compile(
        rf"(?m)^{re.escape(DEPENDENCY_APPROVAL_LABEL)}:\s*"
        rf"{re.escape(normalized_head)}\s*$"
    )
    normalized_author = pr_author.strip().lower()
    for comment in comments if isinstance(comments, list) else []:
        if not isinstance(comment, dict):
            continue
        body = comment.get("body")
        user = comment.get("user")
        login = str(user.get("login") or "") if isinstance(user, dict) else ""
        association = str(comment.get("author_association") or "").upper()
        if not isinstance(body, str) or not pattern.search(body):
            continue
        if association == "OWNER" or (
            association == "MEMBER" and login.strip().lower() != normalized_author
        ):
            return DependencyPolicyDecision(
                True, dependencies, login or association.lower(),
                f"Dependency change approved for head {normalized_head}.",
            )
    return DependencyPolicyDecision(
        False,
        dependencies,
        None,
        f"Dependency files require an exact trusted PR comment: "
        f"{DEPENDENCY_APPROVAL_LABEL}: {normalized_head}",
    )


def split_path_list(raw: str) -> list[str]:
    paths: list[str] = []
    for chunk in raw.split(","):
        cleaned = chunk.strip().strip("`")
        if cleaned:
            paths.append(normalize_path(cleaned))
    return paths


def _glob_to_regex(pattern: str) -> "re.Pattern[str]":
    """Translate a git-style glob into a compiled regex.

    Unlike ``fnmatch``, ``*`` and ``?`` never cross ``/``, so a Scope of
    ``src/*.py`` cannot silently admit ``src/vendor/deep.py``. ``**/``
    matches zero or more whole directories, so ``src/**/*.py`` covers
    ``src/top.py`` as well as ``src/a/b.py``.
    """
    parts: list[str] = []
    i = 0
    n = len(pattern)
    while i < n:
        ch = pattern[i]
        if ch == "*":
            if pattern.startswith("**/", i):
                parts.append("(?:[^/]+/)*")
                i += 3
            elif pattern.startswith("**", i):
                parts.append(".*")
                i += 2
            else:
                parts.append("[^/]*")
                i += 1
        elif ch == "?":
            parts.append("[^/]")
            i += 1
        elif ch == "[":
            j = i + 1
            if j < n and pattern[j] in "!^":
                j += 1
            if j < n and pattern[j] == "]":
                j += 1
            while j < n and pattern[j] != "]":
                j += 1
            if j < n:
                body = pattern[i + 1 : j].replace("!", "^", 1) if pattern[i + 1] == "!" else pattern[i + 1 : j]
                parts.append("[" + body + "]")
                i = j + 1
            else:
                parts.append(re.escape(ch))
                i += 1
        else:
            parts.append(re.escape(ch))
            i += 1
    return re.compile("".join(parts) + r"\Z")


_GLOB_REGEX_CACHE: dict[str, "re.Pattern[str]"] = {}


def path_matches(path: str, pattern: str) -> bool:
    path = normalize_path(path)
    pattern = normalize_path(pattern)
    if pattern in {"*", "**", "**/*"}:
        return True
    if pattern.endswith("/**"):
        prefix = pattern[:-3].rstrip("/")
        return path == prefix or path.startswith(prefix + "/")
    regex = _GLOB_REGEX_CACHE.get(pattern)
    if regex is None:
        regex = _glob_to_regex(pattern)
        _GLOB_REGEX_CACHE[pattern] = regex
    return regex.match(path) is not None


def is_allowed(path: str, allowed_paths: list[str]) -> bool:
    return any(path_matches(path, pattern) for pattern in allowed_paths)


def is_dependency_file(path: str) -> bool:
    path = normalize_path(path)
    name = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(path, f"**/{pattern}") for pattern in DEPENDENCY_GLOBS)


def evaluate(
    *,
    changed_files: list[str],
    corridor_text: str | None,
) -> Report:
    changed = [normalize_path(p) for p in changed_files if normalize_path(p)]
    allowed_paths: list[str] = []
    handoff = extract_compact_handoff(corridor_text)
    near_misses = detect_near_miss_fields(corridor_text)
    handoff_attempted = any(handoff.values()) or bool(near_misses)
    issues: list[str] = []
    warnings: list[str] = []
    deps = [p for p in changed if is_dependency_file(p)]

    scope = handoff.get("Scope", "")
    if scope.strip().strip("`").lower() == "auto":
        issues.append(
            "Scope must declare explicit paths or globs; `auto` mirrors the diff "
            "and creates no review boundary"
        )
    elif scope:
        allowed_paths = split_path_list(scope)
        for pattern in allowed_paths:
            if normalize_path(pattern) in {"*", "**", "**/*"}:
                issues.append(
                    f"scope pattern `{pattern}` matches everything; the corridor carries no information"
                )

    decision = handoff.get("Decision", "")
    if decision and not re.search(r"#\d+|https?://", decision):
        warnings.append("Decision does not point to an issue/discussion/URL; free-text reasons are allowed")

    if corridor_text:
        line_count = len(corridor_text.splitlines())
        if line_count > 60:
            warnings.append(f"PR body is {line_count} lines; prefer a compact handoff")

    if not handoff_attempted:
        issues.append("compact handoff is required, but no handoff fields were found")
    else:
        for label, value in handoff.items():
            if not value:
                near_miss = near_misses.get(label)
                if near_miss:
                    issues.append(
                        f"compact handoff is missing `{label}` (found `{near_miss}` - fields must be plain `{label}: value` lines, no bold, bullets, or headings)"
                    )
                else:
                    issues.append(f"compact handoff is missing `{label}`")
            elif (
                value.strip().lower().startswith("<fill in")
                or value.strip().lower() in HANDOFF_PLACEHOLDERS
            ):
                issues.append(
                    f"compact handoff `{label}` still contains a fill-in placeholder"
                )
        # Strip backticks the way split_path_list does for Scope, so a
        # markdown-styled `src/a.py` (the form the report itself renders)
        # does not false-FAIL the review-first check.
        review_first = normalize_path(handoff.get("Review first", "").strip().strip("`"))
        if review_first and review_first not in changed:
            issues.append(f"review first is not a changed file: {review_first}")

    outside: list[str] = []
    if allowed_paths:
        outside = [
            p for p in changed
            if p not in SCOPE_METADATA_PATHS and not is_allowed(p, allowed_paths)
        ]
        if outside:
            issues.append("changed files outside corridor paths: " + ", ".join(outside))

    if deps:
        issues.append("dependency files require head-bound trusted approval: " + ", ".join(deps))

    return Report(
        ok=not issues,
        changed_files=changed,
        allowed_paths=allowed_paths,
        handoff=handoff,
        outside_files=outside,
        dependency_files=deps,
        issues=issues,
        warnings=warnings,
    )


AGENTCAM_EVIDENCE_DEFAULT = ".agentcam/manifest.redacted.json"


def read_agentcam_manifest(path: Path) -> tuple[dict | None, str | None]:
    """Best-effort read of a committed agentcam manifest.

    Returns ``(manifest, note)``. A malformed author-controlled artifact must
    not crash the action: a missing file yields ``(None, None)`` and an
    unreadable or evidence-less manifest yields ``(None, one-line note)``.
    """
    if not path.is_file():
        return None, None
    try:
        if path.stat().st_size > MANIFEST_MAX_BYTES:
            return None, (
                f"agentcam manifest at `{path.name}` exceeds the 1 MiB safety limit"
            )
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"agentcam manifest at `{path.name}` could not be read: {exc}"
    if not isinstance(data, dict) or not isinstance(data.get("evidence"), dict):
        return None, (
            f"agentcam manifest at `{path.name}` has no evidence section "
            "(recorded by an older agentcam)."
        )
    return data, None


UNVERIFIED_VALUES = {"n/a", "none", "not run", "unverified"}
LOCAL_RECORDED_MARKER = "[locally recorded by agentcam]"


def classify_verification_provenance(
    verified: str | None,
    manifest: dict | None,
    *,
    current_product_fingerprint: str | None = None,
) -> VerificationProvenance:
    """Classify the verification source for policy and reporting.

    Both the PR body and committed manifest are author-controlled.  A handoff
    earns ``local-recorded`` only when its stable marker and exact
    ``command (exit 0)`` fragment agree with a passed check in the manifest.
    Manual checks stay
    visible and valid; placeholders and false recorded claims are unverified.
    """
    value = verified.strip() if isinstance(verified, str) else ""
    normalized = value.lower()
    local_marker_present = LOCAL_RECORDED_MARKER in normalized
    recorded_claim_present = "recorded by agentcam" in normalized
    marker_present = local_marker_present or recorded_claim_present
    evidence = manifest.get("evidence") if isinstance(manifest, dict) else None
    checks = evidence.get("verifications") if isinstance(evidence, dict) else None
    final_state = manifest.get("final_state_fingerprint") if isinstance(manifest, dict) else None
    manifest_product = evidence.get("product_fingerprint") if isinstance(evidence, dict) else None
    passing_commands = []
    for check in checks if isinstance(checks, list) else []:
        if (
            not isinstance(check, dict)
            or type(check.get("exit_code")) is not int
            or check.get("exit_code") != 0
            or not isinstance(final_state, str)
            or check.get("state_fingerprint") != final_state
        ):
            continue
        command = check.get("command")
        if isinstance(command, str) and command.strip():
            passing_commands.append(command.strip())

    grammar = re.fullmatch(
        r"(?P<checks>.+ \(exit 0\)(?:; .+ \(exit 0\))*) "
        r"\[locally recorded by agentcam\]",
        value,
    )
    claimed = grammar.group("checks").split("; ") if grammar else []
    expected = {f"{command} (exit 0)" for command in passing_commands}
    product_matches = (
        isinstance(current_product_fingerprint, str)
        and bool(current_product_fingerprint)
        and manifest_product == current_product_fingerprint
    )
    matched = (
        local_marker_present
        and bool(claimed)
        and len(claimed) == len(set(claimed))
        and all(fragment in expected for fragment in claimed)
        and product_matches
    )
    warnings = []
    placeholder = (
        normalized.startswith("<fill in")
        or normalized in UNVERIFIED_VALUES
        or re.match(r"^(?:n/a|none|not\s+run|unverified)\b", normalized) is not None
    )
    if matched:
        status = "local-recorded"
    elif marker_present:
        status = "unverified"
        if local_marker_present and not product_matches:
            warnings.append("locally recorded verification is stale for the current PR product")
        else:
            warnings.append(
                "Verified claims an agentcam recording marker, but its exact grammar "
                "or state-bound passed record did not match"
            )
    elif not value or placeholder:
        status = "unverified"
        warnings.append("Verified has no completed check; verification is unverified")
    else:
        status = "manual"
        if passing_commands:
            warnings.append(
                "Verified does not match a passed recorded check; treating it as manual"
            )
        else:
            warnings.append(
                "Verified is author-supplied; no matching passed agentcam check was found"
            )

    partial = False
    if isinstance(manifest, dict):
        capture = manifest.get("capture")
        if not isinstance(capture, dict):
            partial = True
        else:
            partial = (
                capture.get("mode") == "claude_hook"
                or capture.get("stdout") == "not_available"
                or capture.get("output_risk_scan") != "enabled"
            )
    if partial:
        warnings.append(
            "agentcam observation coverage is partial; terminal-output evidence may be unavailable"
        )

    return VerificationProvenance(
        status=status,
        partial=partial,
        warnings=warnings,
    )


def apply_manifest_policy(report: Report, manifest: dict | None) -> Report:
    risk = str(report.handoff.get("Risk") or "").strip().lower()
    issues = list(report.issues)
    if risk not in RISK_VALUES:
        issues.append("Risk must be one of: high, medium, none-detected, unknown")
    evidence = manifest.get("evidence") if isinstance(manifest, dict) else None
    overall = str(evidence.get("overall_risk") or "").strip().upper() if isinstance(evidence, dict) else ""
    minimum = {"HIGH": "high", "MEDIUM": "medium", "NONE_DETECTED": "none-detected"}.get(overall)
    ranks = {"none-detected": 0, "unknown": 1, "medium": 2, "high": 3}
    if minimum and risk in ranks and ranks[risk] < ranks[minimum]:
        issues.append(f"Risk `{risk}` underreports agentcam manifest risk `{overall}`")
    return replace(report, ok=not issues, issues=issues)


def apply_dependency_policy(
    report: Report, decision: DependencyPolicyDecision
) -> Report:
    prefix = "dependency files require head-bound trusted approval:"
    issues = [issue for issue in report.issues if not issue.startswith(prefix)]
    if decision.dependency_files and not decision.ok:
        issues.append(decision.reason)
    return replace(report, ok=not issues, issues=issues)


def apply_verification_policy(
    report: Report,
    provenance: VerificationProvenance | None,
) -> Report:
    """Reject a handoff whose required verification is not completed."""
    if provenance is None or provenance.status != "unverified":
        return report
    issue = (
        "verification is unverified; provide a completed manual check or "
        "matching recorded check"
    )
    if issue in report.issues:
        return report
    return replace(report, ok=False, issues=[*report.issues, issue])


def compact_markdown(value: str) -> list[str]:
    return [escape_markdown(line.rstrip()) for line in value.splitlines() if line.strip()]


def should_show_handoff_template(report: Report) -> bool:
    return any(
        issue.startswith("compact handoff is required")
        or issue.startswith("compact handoff is missing")
        for issue in report.issues
    )


def render_agentcam_section(
    evidence: dict | None, note: str | None
) -> list[str]:
    """Markdown lines for the recorded-evidence section, or [].

    The manifest is a committed, author-controlled file, so any field
    may carry any shape; entries render best-effort or are skipped.
    Display-only means no shape may raise before the verdict is set.
    """
    if evidence is None and note is None:
        return []
    lines = ["", "## Recorded Evidence (agentcam)"]
    if note is not None:
        lines.append(f"- {escape_markdown(note)}")
        return lines
    overall = evidence.get("overall_risk")
    if overall:
        lines.append(f"- overall risk: {escape_markdown(overall)}")
    recorded = evidence.get("changed_files")
    if isinstance(recorded, list) and recorded:
        lines.append(f"- recorded changed files: {len(recorded)}")
    flags = evidence.get("risk_flags")
    for flag in flags if isinstance(flags, list) else []:
        if not isinstance(flag, dict):
            continue
        level = flag.get("level", "?")
        rule = flag.get("rule", "?")
        found = flag.get("evidence", "")
        lines.append(
            f"- {escape_markdown(level)} | {escape_markdown(rule)} | "
            f"`{escape_markdown(found)}`"
        )
    checks = evidence.get("verifications")
    for check in checks if isinstance(checks, list) else []:
        if not isinstance(check, dict):
            continue
        cmd = check.get("command") or "?"
        code = check.get("exit_code")
        code_note = "?" if code is None else code
        dur = check.get("duration_seconds")
        dur_note = f" ({dur}s)" if isinstance(dur, (int, float)) else ""
        lines.append(
            f"- recorded check: `{escape_markdown(cmd)}` | exit "
            f"{escape_markdown(code_note)}{escape_markdown(dur_note)}"
        )
    raw_diff_stat = evidence.get("diff_stat")
    diff_stat = (
        raw_diff_stat.strip() if isinstance(raw_diff_stat, str) else ""
    )
    if diff_stat:
        lines.append("- diff stat: " + "<br>".join(
            escape_markdown(line) for line in diff_stat.splitlines()
        ))
    return lines


def render_verification_provenance(
    provenance: VerificationProvenance | None,
) -> list[str]:
    if provenance is None:
        return []
    lines = ["", "## Verification Provenance", f"- status: {provenance.status}"]
    if provenance.partial:
        lines.append("- observation coverage: partial")
    return lines


def render_markdown(
    report: Report,
    agentcam_evidence: dict | None = None,
    agentcam_note: str | None = None,
    verification_provenance: VerificationProvenance | None = None,
) -> str:
    status = "PASS" if report.ok else "FAIL"
    lines = [
        f"# Corridor CI: {status}",
        "",
        f"- changed files: {len(report.changed_files)}",
        f"- corridor paths: {len(report.allowed_paths)}",
    ]

    if any(report.handoff.values()):
        lines.append("")
        lines.append("## Review Handoff")
        for label in COMPACT_HANDOFF_LABELS:
            value = report.handoff.get(label, "")
            if not value:
                continue
            lines.append("")
            lines.append(f"### {label}")
            lines.extend(compact_markdown(value))

    if report.allowed_paths:
        lines.append("")
        lines.append("## Declared Paths")
        lines.extend(f"- `{escape_markdown(p)}`" for p in report.allowed_paths)

    if report.changed_files:
        lines.append("")
        lines.append("## Touched Files")
        lines.extend(f"- `{escape_markdown(p)}`" for p in report.changed_files)

    if report.outside_files:
        lines.append("")
        lines.append("## Out Of Corridor")
        lines.extend(f"- `{escape_markdown(p)}`" for p in report.outside_files)

    if report.dependency_files:
        lines.append("")
        lines.append("## Dependency Changes")
        lines.extend(f"- `{escape_markdown(p)}`" for p in report.dependency_files)

    lines.extend(render_agentcam_section(agentcam_evidence, agentcam_note))
    lines.extend(render_verification_provenance(verification_provenance))

    if report.issues:
        lines.append("")
        lines.append("## Issues")
        lines.extend(f"- {escape_markdown(issue)}" for issue in report.issues)
    if should_show_handoff_template(report):
        lines.append("")
        lines.append("## Copyable Review Handoff")
        lines.append("")
        lines.append("```md")
        lines.extend(COPYABLE_REVIEW_HANDOFF.splitlines())
        lines.append("```")
    warnings = list(report.warnings)
    if verification_provenance is not None:
        warnings.extend(verification_provenance.warnings)
    if warnings:
        lines.append("")
        lines.append("## Warnings")
        lines.extend(f"- {escape_markdown(warning)}" for warning in warnings)
    return "\n".join(lines) + "\n"


def exit_code(report: Report, mode: str) -> int:
    if mode == "warn":
        return 0
    return 0 if report.ok else 1


def write_step_summary(markdown: str) -> None:
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(markdown)


def github_api_request(method: str, url: str, token: str, payload: dict[str, str] | None = None) -> Any:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/vnd.github+json")
    if payload is not None:
        request.add_header("Content-Type", "application/json")

    with urllib.request.urlopen(request, timeout=10) as response:
        body = response.read()
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def read_pr_comments(
    *,
    token: str,
    repository: str,
    pr_number: str | int,
    transport: HttpTransport | None = None,
) -> list[dict[str, Any]]:
    """Read every PR issue comment; malformed API shapes fail closed."""
    api_url = os.environ.get("GITHUB_API_URL", GITHUB_API_URL).rstrip("/")
    comments_url = f"{api_url}/repos/{repository}/issues/{pr_number}/comments"
    transport = transport or github_api_request
    collected: list[dict[str, Any]] = []
    page = 1
    while True:
        result = transport(
            "GET", f"{comments_url}?per_page=100&page={page}", token, None
        )
        if not isinstance(result, list):
            raise RuntimeError("GitHub comments response was not a list")
        collected.extend(comment for comment in result if isinstance(comment, dict))
        if len(result) < 100:
            return collected
        page += 1


def _safe_policy_path(path: str) -> str:
    return path.replace("`", "'").replace("\r", "\\r").replace("\n", "\\n")


def render_workflow_policy(decision: WorkflowPolicyDecision) -> str:
    status = "PASS" if decision.ok else "FAIL"
    lines = [
        f"# Policy Gate: {status}",
        "",
        f"- active workflow files changed: {len(decision.changed_workflows)}",
        f"- approval: {decision.approved_by or 'none'}",
        "",
        decision.reason,
    ]
    if decision.changed_workflows:
        lines.extend(
            ["", "## Active Workflow Changes"]
            + [f"- `{_safe_policy_path(path)}`" for path in decision.changed_workflows]
        )
    return "\n".join(lines) + "\n"


def run_policy_gate(repo: Path, base: str, head: str) -> int:
    event = read_event_payload()
    pull = event.get("pull_request") if isinstance(event, dict) else None
    if not isinstance(pull, dict):
        raise SystemExit("policy gate requires a pull_request_target event payload")
    head_data = pull.get("head")
    user_data = pull.get("user")
    head_sha = str(head_data.get("sha") or "") if isinstance(head_data, dict) else ""
    pr_author = str(user_data.get("login") or "") if isinstance(user_data, dict) else ""
    if re.fullmatch(r"[0-9a-fA-F]{40}", head_sha) is None or not pr_author:
        raise SystemExit("policy gate event is missing a valid head SHA or PR author")

    token = os.environ.get("GITHUB_TOKEN")
    repository = os.environ.get("GITHUB_REPOSITORY")
    pr_number = find_pr_number()
    if not token or not repository or not pr_number:
        raise SystemExit(
            "policy gate requires GITHUB_TOKEN, GITHUB_REPOSITORY, and PR number"
        )

    changed = extract_changed_files_between(repo, base, head)
    workflow_changed = any(
        normalize_path(path).startswith(WORKFLOW_PREFIX) for path in changed
    )
    comments: list[dict[str, Any]] = []
    if workflow_changed:
        try:
            comments = read_pr_comments(
                token=token, repository=repository, pr_number=pr_number
            )
        except Exception as exc:
            raise SystemExit(
                f"policy gate could not read trusted approvals: {exc}"
            ) from exc
    decision = evaluate_workflow_policy(
        changed_files=changed,
        comments=comments,
        head_sha=head_sha,
        pr_author=pr_author,
    )
    markdown = render_workflow_policy(decision)
    print(markdown)
    write_step_summary(markdown)
    return 0 if decision.ok else 1


def upsert_pr_comment(
    markdown: str,
    *,
    token: str | None = None,
    repository: str | None = None,
    pr_number: str | int | None = None,
    transport: HttpTransport | None = None,
) -> None:
    token = token if token is not None else os.environ.get("GITHUB_TOKEN")
    repository = repository if repository is not None else os.environ.get("GITHUB_REPOSITORY")
    pr_number = pr_number if pr_number is not None else find_pr_number()

    if not token:
        print("corridor-ci PR comment skipped: missing GITHUB_TOKEN")
        return
    if not repository:
        print("corridor-ci PR comment skipped: missing GITHUB_REPOSITORY")
        return
    if not pr_number:
        print("corridor-ci PR comment skipped: missing pull request number")
        return

    api_url = os.environ.get("GITHUB_API_URL", GITHUB_API_URL).rstrip("/")
    transport = transport or github_api_request
    body = {"body": f"{COMMENT_MARKER}\n\n{markdown}"}
    comments_url = f"{api_url}/repos/{repository}/issues/{pr_number}/comments"

    try:
        page = 1
        while True:
            page_url = f"{comments_url}?per_page=100&page={page}"
            comments = transport("GET", page_url, token, None) or []
            for comment in comments:
                user = comment.get("user")
                login = str(user.get("login") or "") if isinstance(user, dict) else ""
                if (
                    COMMENT_MARKER in str(comment.get("body", ""))
                    and comment.get("id")
                    and login.lower() == "github-actions[bot]"
                ):
                    update_url = f"{api_url}/repos/{repository}/issues/comments/{comment['id']}"
                    transport("PATCH", update_url, token, body)
                    return
            if len(comments) < 100:
                break
            page += 1
        transport("POST", comments_url, token, body)
    except urllib.error.HTTPError as exc:
        print(f"corridor-ci PR comment skipped: GitHub API returned {exc.code} {exc.reason}")
    except Exception as exc:
        print(f"corridor-ci PR comment skipped: {exc}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a PR against a declared corridor.")
    parser.add_argument("--repo", default=".", help="repository checkout path")
    parser.add_argument(
        "--policy-gate",
        action="store_true",
        help="protect active workflow changes using default-branch policy",
    )
    parser.add_argument("--base", help="base revision for --policy-gate")
    parser.add_argument("--head", help="head revision for --policy-gate")
    parser.add_argument("--mode", choices=("fail", "warn"), default=os.environ.get("INPUT_MODE", "fail"))
    parser.add_argument("--comment", default=os.environ.get("INPUT_COMMENT", "false"))
    parser.add_argument(
        "--agentcam-evidence",
        default=os.environ.get("INPUT_AGENTCAM_EVIDENCE", AGENTCAM_EVIDENCE_DEFAULT),
        help=(
            "checkout-relative path of a committed agentcam "
            "manifest.redacted.json; its evidence is appended to the report "
            "and false or incomplete verification claims fail the corridor"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo = Path(args.repo).resolve()
    if args.policy_gate:
        if not args.base or not args.head:
            raise SystemExit("--policy-gate requires --base and --head")
        return run_policy_gate(repo, args.base, args.head)
    corridor = find_pr_body()
    changed = extract_changed_files(repo)
    report = evaluate(
        changed_files=changed,
        corridor_text=corridor,
    )
    manifest, evidence_note = read_agentcam_manifest(
        repo / args.agentcam_evidence
    )
    evidence = manifest.get("evidence") if isinstance(manifest, dict) else None
    report = apply_manifest_policy(report, manifest)
    current_product_fingerprint = compute_current_product_fingerprint(
        repo, changed
    )
    provenance = None
    if any(report.handoff.values()) or manifest is not None or evidence_note is not None:
        provenance = classify_verification_provenance(
            report.handoff.get("Verified"),
            manifest,
            current_product_fingerprint=current_product_fingerprint,
        )
    report = apply_verification_policy(report, provenance)

    if report.dependency_files:
        event = read_event_payload()
        pull = event.get("pull_request") if isinstance(event, dict) else None
        head_data = pull.get("head") if isinstance(pull, dict) else None
        user_data = pull.get("user") if isinstance(pull, dict) else None
        head_sha = str(head_data.get("sha") or "") if isinstance(head_data, dict) else ""
        pr_author = str(user_data.get("login") or "") if isinstance(user_data, dict) else ""
        comments: list[dict[str, Any]] = []
        token = os.environ.get("GITHUB_TOKEN")
        repository = os.environ.get("GITHUB_REPOSITORY")
        pr_number = find_pr_number()
        if token and repository and pr_number:
            try:
                comments = read_pr_comments(
                    token=token, repository=repository, pr_number=pr_number
                )
            except Exception as exc:
                report = replace(
                    report,
                    ok=False,
                    issues=[
                        *report.issues,
                        f"dependency approval could not be read: {exc}",
                    ],
                )
        decision = evaluate_dependency_policy(
            dependency_files=report.dependency_files,
            comments=comments,
            head_sha=head_sha,
            pr_author=pr_author,
        )
        report = apply_dependency_policy(report, decision)
    markdown = render_markdown(
        report,
        agentcam_evidence=evidence,
        agentcam_note=evidence_note,
        verification_provenance=provenance,
    )
    print(markdown)
    write_step_summary(markdown)
    if truthy(args.comment):
        upsert_pr_comment(markdown)
    return exit_code(report, args.mode)


if __name__ == "__main__":
    sys.exit(main())
