#!/usr/bin/env python3
"""Corridor CI v14: validate a state-bound Guardrails review artifact."""

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

COMMENT_MARKER = "<!-- corridor-ci -->"
WORKFLOW_APPROVAL_LABEL = "Guardrails-Workflow-Approval"
DEPENDENCY_APPROVAL_LABEL = "Guardrails-Dependency-Approval"
WORKFLOW_PREFIX = ".github/workflows/"
SCOPE_METADATA_PATHS = {
    ".guardrails/review.json",
}
REVIEW_ARTIFACT_DEFAULT = ".guardrails/review.json"
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


def read_event_payload() -> dict[str, Any]:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        return {}
    try:
        return json.loads(Path(event_path).read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


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


def extract_deleted_files(repo: Path) -> list[str]:
    base = diff_base(repo)
    proc = subprocess.run(
        [
            "git", "-c", "core.quotepath=false", "diff", "--diff-filter=D",
            "--name-only", f"{base}...HEAD",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise SystemExit(f"failed to read deleted files: {proc.stderr.strip()}")
    return [normalize_path(path) for path in proc.stdout.splitlines() if path.strip()]


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
    if re.fullmatch(r"[0-9a-f]{40}", normalized_head) is None:
        # Fail closed: an empty head would reduce the pattern to
        # "label with no SHA", losing the head binding entirely.
        return WorkflowPolicyDecision(
            ok=False,
            changed_workflows=changed_workflows,
            approved_by=None,
            reason="Head SHA is missing or invalid; approval cannot be verified.",
        )
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
    if re.fullmatch(r"[0-9a-f]{40}", normalized_head) is None:
        # Fail closed: an empty head would reduce the pattern to
        # "label with no SHA", losing the head binding entirely.
        return DependencyPolicyDecision(
            False,
            dependencies,
            None,
            "Head SHA is missing or invalid; approval cannot be verified.",
        )
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


_GLOB_REGEX_CACHE: dict[str, "re.Pattern[str] | None"] = {}


def path_matches(path: str, pattern: str) -> bool:
    path = normalize_path(path)
    pattern = normalize_path(pattern)
    if pattern in {"*", "**", "**/*"}:
        return True
    if pattern.endswith("/**"):
        prefix = pattern[:-3].rstrip("/")
        return path == prefix or path.startswith(prefix + "/")
    if pattern not in _GLOB_REGEX_CACHE:
        # A malformed glob (e.g. bad character range "[z-a]") must fail
        # closed as "matches nothing" — covered files then surface as an
        # outside-scope issue — not crash the checker with a traceback,
        # which would also break warn mode's report-only contract.
        try:
            _GLOB_REGEX_CACHE[pattern] = _glob_to_regex(pattern)
        except re.error:
            _GLOB_REGEX_CACHE[pattern] = None
    regex = _GLOB_REGEX_CACHE[pattern]
    return regex is not None and regex.match(path) is not None


def is_allowed(path: str, allowed_paths: list[str]) -> bool:
    return any(path_matches(path, pattern) for pattern in allowed_paths)


def is_dependency_file(path: str) -> bool:
    path = normalize_path(path)
    name = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(path, f"**/{pattern}") for pattern in DEPENDENCY_GLOBS)


def _review_high_risk_path(path: str) -> bool:
    normalized = normalize_path(path).lower()
    if normalized.startswith(WORKFLOW_PREFIX):
        return True
    if is_dependency_file(normalized):
        return True
    high = {
        "auth", "login", "oauth", "session", "jwt", "permission",
        "credential", "secret", "migration", "migrations", "terraform",
        "kubernetes", "helm", "deploy", "deployment", "infrastructure",
    }
    return bool(set(normalized.split("/")) & high)


def evaluate_review_artifact(
    *,
    changed_files: list[str],
    deleted_files: list[str] | None = None,
    review: dict[str, Any] | None,
    current_product_fingerprint: str,
    pr_title: str,
    pr_url: str,
) -> Report:
    """Validate the v14 machine-generated review artifact, not PR prose."""
    changed = [normalize_path(path) for path in changed_files if normalize_path(path)]
    product = [path for path in changed if path not in SCOPE_METADATA_PATHS]
    deleted = {
        normalize_path(path) for path in (deleted_files or [])
        if normalize_path(path) in product
    }
    dependencies = [path for path in product if is_dependency_file(path)]
    handoff = {
        "Decision": f"{pr_title} ({pr_url})".strip(),
        "Scope": "",
        "Review first": "",
        "Verified": "",
        "Risk": "",
    }
    issues: list[str] = []
    warnings: list[str] = []
    allowed: list[str] = []
    outside: list[str] = []
    if not isinstance(review, dict):
        issues.append(
            "review artifact `.guardrails/review.json` is required; let the "
            "installed Stop hook finish the delivery"
        )
        return Report(False, changed, allowed, handoff, product, dependencies, issues, warnings)
    if type(review.get("schema")) is not int or review.get("schema") != 1:
        issues.append("review artifact requires integer schema 1")
    generator = review.get("generator")
    if not (
        isinstance(generator, dict)
        and isinstance(generator.get("agentcam_version"), str)
        and generator["agentcam_version"]
        and isinstance(generator.get("runtime_revision"), str)
        and generator["runtime_revision"]
    ):
        issues.append("review artifact generator must name Agentcam and runtime revisions")
    delivery = review.get("delivery")
    verification = review.get("verification")
    if not isinstance(delivery, dict):
        issues.append("review artifact delivery must be an object")
        delivery = {}
    if not isinstance(verification, dict):
        issues.append("review artifact verification must be an object")
        verification = {}
    artifact_fingerprint = delivery.get("product_fingerprint")
    if artifact_fingerprint != current_product_fingerprint:
        issues.append("review artifact is stale for the current PR product fingerprint")
    base_commit = delivery.get("base_commit")
    if base_commit is not None and (
        not isinstance(base_commit, str)
        or re.fullmatch(r"[0-9a-f]{40}", base_commit) is None
    ):
        issues.append("review artifact base_commit must be null or a full lowercase SHA")
    outcomes = delivery.get("outcomes")
    if not isinstance(outcomes, list) or not outcomes or any(
        not isinstance(value, str) or not value.strip() for value in outcomes
    ):
        issues.append("review artifact outcomes must be a non-empty string array")
    if not isinstance(delivery.get("scope_changes"), list):
        issues.append("review artifact scope_changes must be an array")
    raw_scope = delivery.get("scope")
    if not isinstance(raw_scope, list) or not raw_scope or any(
        not isinstance(value, str) or not normalize_path(value) for value in raw_scope
    ):
        issues.append("review artifact scope must be a non-empty string array")
    else:
        allowed = [normalize_path(value) for value in raw_scope]
        outside = [path for path in product if not is_allowed(path, allowed)]
        if outside:
            issues.append("product files outside review artifact scope: " + ", ".join(outside))
    raw_changed = delivery.get("changed_files")
    artifact_statuses: dict[str, str] = {}
    if not isinstance(raw_changed, list):
        issues.append("review artifact changed_files must be an array")
    else:
        malformed_changed = False
        for item in raw_changed:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("path"), str)
                or not normalize_path(item["path"])
                or not isinstance(item.get("status"), str)
                or item["status"].lower()
                not in {"modified", "deleted", "untracked", "added", "renamed"}
            ):
                malformed_changed = True
                continue
            artifact_statuses[normalize_path(item["path"])] = item["status"].lower()
        if malformed_changed:
            issues.append("review artifact contains a malformed changed_files entry")
        if set(artifact_statuses) != set(product):
            issues.append("review artifact changed_files do not match current product paths")
        if any(artifact_statuses.get(path) != "deleted" for path in deleted):
            issues.append("review artifact changed_files underreports a tracked deleted file")
    review_first = delivery.get("review_first")
    if not isinstance(review_first, str) or normalize_path(review_first) not in product:
        issues.append("review artifact review_first must be a changed product file")
    else:
        handoff["Review first"] = normalize_path(review_first)
    risk = delivery.get("risk")
    if risk not in RISK_VALUES:
        issues.append("review artifact risk must be high, medium, none-detected, or unknown")
    risk_floor = "high" if deleted or any(
        _review_high_risk_path(path) for path in product
    ) else "none-detected"
    if risk_floor == "high" and risk != "high":
        issues.append("review artifact risk underreports the current PR risk floor")
    handoff["Risk"] = risk if isinstance(risk, str) else ""
    handoff["Scope"] = ", ".join(allowed)

    level = verification.get("level")
    checks = verification.get("checks")
    if level not in {"recorded", "structural-only"}:
        issues.append("review artifact verification level is invalid")
    if not isinstance(checks, list) or not checks:
        issues.append("review artifact requires at least one verification check")
        checks = []
    valid_names: list[str] = []
    for check in checks:
        if not isinstance(check, dict):
            issues.append("review artifact contains a malformed verification check")
            continue
        if type(check.get("exit_code")) is not int or check.get("exit_code") != 0:
            issues.append("review artifact verification check did not record integer exit 0")
        if check.get("state_fingerprint") != artifact_fingerprint:
            issues.append("review artifact verification check is stale")
        duration = check.get("duration_ms")
        if type(duration) is not int or duration < 0:
            issues.append("review artifact verification duration_ms must be a non-negative integer")
        argv = check.get("argv")
        if not isinstance(argv, list) or not argv or any(
            not isinstance(value, str) or not value for value in argv
        ):
            issues.append("review artifact verification argv must be a non-empty string array")
        if isinstance(check.get("id"), str):
            valid_names.append(check["id"])
    handoff["Verified"] = ", ".join(valid_names)
    if level == "structural-only":
        warnings.append("verification is structural-only; no project test was configured")
    elif level == "recorded" and "primary" not in valid_names:
        issues.append("recorded verification requires a passed primary check")
    capture = review.get("capture")
    if not isinstance(capture, dict):
        issues.append("review artifact capture must be an object")
    else:
        if capture.get("coverage") not in {"full", "partial"}:
            issues.append("review artifact capture coverage must be full or partial")
        if capture.get("terminal") not in {"captured", "unavailable"}:
            issues.append("review artifact capture terminal must be captured or unavailable")
        if capture.get("coverage") == "partial":
            warnings.append("capture coverage is partial")
        if capture.get("terminal") == "unavailable":
            warnings.append("terminal output is unavailable")
    if risk == "high":
        approval = review.get("approval")
        if not (
            isinstance(approval, dict)
            and approval.get("required") is True
            and approval.get("confirmed") is True
            and approval.get("product_fingerprint") == artifact_fingerprint
            and isinstance(approval.get("confirmation_id"), str)
            and re.fullmatch(r"[0-9a-f]{64}", approval["confirmation_id"]) is not None
        ):
            issues.append("high-risk review artifact lacks a matching user confirmation")
    return Report(
        not issues, changed, allowed, handoff, outside, dependencies, issues, warnings
    )


def read_review_artifact(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, "review artifact is missing"
    try:
        if path.stat().st_size > MANIFEST_MAX_BYTES:
            return None, "review artifact exceeds the 1 MiB size limit"
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f"review artifact is malformed: {exc}"
    if not isinstance(value, dict):
        return None, "review artifact root must be an object"
    return value, None


def apply_dependency_policy(
    report: Report, decision: DependencyPolicyDecision
) -> Report:
    issues = list(report.issues)
    if decision.dependency_files and not decision.ok:
        issues.append(decision.reason)
    return replace(report, ok=not issues, issues=issues)


def render_markdown(
    report: Report,
) -> str:
    status = "PASS" if report.ok else "FAIL"
    lines = [
        f"# Corridor CI: {status}",
        "",
        f"- changed files: {len(report.changed_files)}",
        f"- declared paths: {len(report.allowed_paths)}",
    ]

    if any(report.handoff.values()):
        lines.append("")
        lines.append("## Review Artifact")
        for label in ("Decision", "Scope", "Review first", "Verified", "Risk"):
            value = report.handoff.get(label, "")
            if not value:
                continue
            lines.append("")
            lines.append(f"### {label}")
            lines.append(escape_markdown(value))

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
        lines.append("## Outside Declared Scope")
        lines.extend(f"- `{escape_markdown(p)}`" for p in report.outside_files)

    if report.dependency_files:
        lines.append("")
        lines.append("## Dependency Changes")
        lines.extend(f"- `{escape_markdown(p)}`" for p in report.dependency_files)

    if report.issues:
        lines.append("")
        lines.append("## Issues")
        lines.extend(f"- {escape_markdown(issue)}" for issue in report.issues)
    warnings = list(report.warnings)
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
    parser = argparse.ArgumentParser(description="Validate a PR review artifact.")
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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo = Path(args.repo).resolve()
    if args.policy_gate:
        if not args.base or not args.head:
            raise SystemExit("--policy-gate requires --base and --head")
        return run_policy_gate(repo, args.base, args.head)
    changed = extract_changed_files(repo)
    deleted = extract_deleted_files(repo)
    current_product_fingerprint = compute_current_product_fingerprint(
        repo, changed
    )
    review, review_note = read_review_artifact(repo / REVIEW_ARTIFACT_DEFAULT)
    event = read_event_payload()
    pull = event.get("pull_request") if isinstance(event, dict) else None
    pr_title = str(pull.get("title") or "Pull request") if isinstance(pull, dict) else "Pull request"
    pr_url = str(pull.get("html_url") or "") if isinstance(pull, dict) else ""
    report = evaluate_review_artifact(
        changed_files=changed,
        deleted_files=deleted,
        review=review,
        current_product_fingerprint=current_product_fingerprint,
        pr_title=pr_title,
        pr_url=pr_url,
    )
    if review_note and review is None and "required" not in "\n".join(report.issues):
        report = replace(report, ok=False, issues=[*report.issues, review_note])

    if report.dependency_files:
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
    markdown = render_markdown(report)
    print(markdown)
    write_step_summary(markdown)
    if truthy(args.comment):
        upsert_pr_comment(markdown)
    return exit_code(report, args.mode)


if __name__ == "__main__":
    sys.exit(main())
