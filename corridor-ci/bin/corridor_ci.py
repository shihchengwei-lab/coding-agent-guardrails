#!/usr/bin/env python3
"""Corridor CI: keep incoming PR changes inside a declared review corridor."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
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

COPYABLE_REVIEW_HANDOFF = """Decision: #123 or small fix
Scope: path/or/glob
Review first: path/to/file
Verified: test command or manual check
Risk: none
"""

COMMENT_MARKER = "<!-- corridor-ci -->"
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


def normalize_path(path: str) -> str:
    cleaned = path.strip().replace("\\", "/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned


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
    block. Since field parsing is first-non-empty-value-wins, a fenced
    ``Scope: auto`` example would otherwise shadow the author's real
    handoff below it (and silently disable the corridor check).
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


def is_paths_auto(value: str) -> bool:
    cleaned = value.strip().strip("`").lower()
    return cleaned == "auto"


def auto_paths_from_changed_files(changed_files: list[str]) -> list[str]:
    return [path for path in changed_files if path]


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
    proc = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise SystemExit(f"failed to read changed files: {proc.stderr.strip()}")
    return [normalize_path(p) for p in proc.stdout.splitlines() if p.strip()]


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
    allow_dependencies: bool = False,
    max_changed_files: int = 0,
    small_change_max_files: int = 0,
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
    if is_paths_auto(scope):
        allowed_paths = auto_paths_from_changed_files(changed)
    elif scope:
        allowed_paths = split_path_list(scope)
        for pattern in allowed_paths:
            if normalize_path(pattern) in {"*", "**", "**/*"}:
                warnings.append(f"scope pattern `{pattern}` matches everything; the corridor carries no information")

    decision = handoff.get("Decision", "")
    if decision and not re.search(r"#\d+|https?://", decision):
        warnings.append("Decision does not point to an issue/discussion/URL; free-text reasons are allowed")

    if corridor_text:
        line_count = len(corridor_text.splitlines())
        if line_count > 60:
            warnings.append(f"PR body is {line_count} lines; prefer a compact handoff")

    small_change_fast_path = (
        not handoff_attempted
        and small_change_max_files > 0
        and 0 < len(changed) <= small_change_max_files
        and not deps
    )

    if small_change_fast_path:
        warnings.append(
            f"small change fast path: review boundary skipped for {len(changed)} changed file(s)"
        )
    elif not handoff_attempted:
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
        review_first = normalize_path(handoff.get("Review first", ""))
        if review_first and review_first not in changed:
            issues.append(f"review first is not a changed file: {review_first}")

    if max_changed_files > 0 and len(changed) > max_changed_files:
        issues.append(f"changed file count is {len(changed)}, above max_changed_files={max_changed_files}")

    outside: list[str] = []
    if allowed_paths:
        outside = [p for p in changed if not is_allowed(p, allowed_paths)]
        if outside:
            issues.append("changed files outside corridor paths: " + ", ".join(outside))

    if deps and not allow_dependencies:
        issues.append("dependency manifest changed without allow_dependencies=true: " + ", ".join(deps))

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


def read_agentcam_evidence(path: Path) -> tuple[dict | None, str | None]:
    """Best-effort read of a committed agentcam evidence manifest.

    Returns ``(evidence, note)``. Recorded evidence is display-only and
    must never affect pass/fail, so this never raises: a missing file
    yields ``(None, None)`` (no section), an unreadable or evidence-less
    manifest yields ``(None, one-line note)``.
    """
    if not path.is_file():
        return None, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"agentcam manifest at `{path.name}` could not be read: {exc}"
    if not isinstance(data, dict) or not isinstance(data.get("evidence"), dict):
        return None, (
            f"agentcam manifest at `{path.name}` has no evidence section "
            "(recorded by an older agentcam)."
        )
    return data["evidence"], None


def compact_markdown(value: str) -> list[str]:
    return [line.rstrip() for line in value.splitlines() if line.strip()]


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
        lines.append(f"- {note}")
        return lines
    overall = evidence.get("overall_risk")
    if overall:
        lines.append(f"- overall risk: {overall}")
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
        lines.append(f"- {level} | {rule} | `{found}`")
    checks = evidence.get("verifications")
    for check in checks if isinstance(checks, list) else []:
        if not isinstance(check, dict):
            continue
        cmd = check.get("command") or "?"
        code = check.get("exit_code")
        code_note = "?" if code is None else code
        dur = check.get("duration_seconds")
        dur_note = f" ({dur}s)" if isinstance(dur, (int, float)) else ""
        lines.append(f"- recorded check: `{cmd}` | exit {code_note}{dur_note}")
    raw_diff_stat = evidence.get("diff_stat")
    diff_stat = (
        raw_diff_stat.strip() if isinstance(raw_diff_stat, str) else ""
    )
    if diff_stat:
        lines.append("")
        lines.append("```text")
        lines.extend(diff_stat.splitlines())
        lines.append("```")
    return lines


def render_markdown(
    report: Report,
    agentcam_evidence: dict | None = None,
    agentcam_note: str | None = None,
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
        lines.extend(f"- `{p}`" for p in report.allowed_paths)

    if report.changed_files:
        lines.append("")
        lines.append("## Touched Files")
        lines.extend(f"- `{p}`" for p in report.changed_files)

    if report.outside_files:
        lines.append("")
        lines.append("## Out Of Corridor")
        lines.extend(f"- `{p}`" for p in report.outside_files)

    if report.dependency_files:
        lines.append("")
        lines.append("## Dependency Changes")
        lines.extend(f"- `{p}`" for p in report.dependency_files)

    lines.extend(render_agentcam_section(agentcam_evidence, agentcam_note))

    if report.issues:
        lines.append("")
        lines.append("## Issues")
        lines.extend(f"- {issue}" for issue in report.issues)
    if should_show_handoff_template(report):
        lines.append("")
        lines.append("## Copyable Review Handoff")
        lines.append("")
        lines.append("```md")
        lines.extend(COPYABLE_REVIEW_HANDOFF.splitlines())
        lines.append("```")
    if report.warnings:
        lines.append("")
        lines.append("## Warnings")
        lines.extend(f"- {warning}" for warning in report.warnings)
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
                if COMMENT_MARKER in str(comment.get("body", "")) and comment.get("id"):
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
    parser.add_argument("--mode", choices=("fail", "warn"), default=os.environ.get("INPUT_MODE", "warn"))
    parser.add_argument("--allow-dependencies", default=os.environ.get("INPUT_ALLOW_DEPENDENCIES", "false"))
    parser.add_argument("--max-changed-files", type=int, default=int(os.environ.get("INPUT_MAX_CHANGED_FILES", "12") or "12"))
    parser.add_argument("--comment", default=os.environ.get("INPUT_COMMENT", "false"))
    parser.add_argument(
        "--small-change-max-files",
        type=int,
        default=int(os.environ.get("INPUT_SMALL_CHANGE_MAX_FILES", "0") or "0"),
        help="allow PRs without a review boundary when changed-file count is at or below this value",
    )
    parser.add_argument(
        "--agentcam-evidence",
        default=os.environ.get("INPUT_AGENTCAM_EVIDENCE", AGENTCAM_EVIDENCE_DEFAULT),
        help=(
            "checkout-relative path of a committed agentcam "
            "manifest.redacted.json; its recorded evidence is appended to "
            "the report, display-only, never affecting pass/fail"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo = Path(args.repo).resolve()
    corridor = find_pr_body()
    changed = extract_changed_files(repo)
    report = evaluate(
        changed_files=changed,
        corridor_text=corridor,
        allow_dependencies=truthy(args.allow_dependencies),
        max_changed_files=args.max_changed_files,
        small_change_max_files=args.small_change_max_files,
    )
    evidence, evidence_note = read_agentcam_evidence(
        repo / args.agentcam_evidence
    )
    markdown = render_markdown(
        report, agentcam_evidence=evidence, agentcam_note=evidence_note
    )
    print(markdown)
    write_step_summary(markdown)
    if truthy(args.comment):
        upsert_pr_comment(markdown)
    return exit_code(report, args.mode)


if __name__ == "__main__":
    sys.exit(main())
