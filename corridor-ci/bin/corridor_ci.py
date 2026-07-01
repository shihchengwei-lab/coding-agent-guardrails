#!/usr/bin/env python3
"""Corridor CI: keep incoming PR changes inside a declared review corridor."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


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

DEFAULT_ALWAYS_ALLOWED = (
    ".corridor/review-packet.md",
    ".slime/corridor.md",
)

DEFAULT_CORRIDOR_FILE = ".corridor/review-packet.md"
LEGACY_CORRIDOR_FILES = (".slime/corridor.md",)

REVIEW_PACKET_SECTIONS = {
    "What Changed": ("what changed", "semantic delta"),
    "Why": ("why",),
    "Paths": ("paths", "allowed paths"),
    "Non-goals": ("non-goals", "non goals", "non-goals / out of scope"),
    "Verification": ("verification", "stop condition"),
    "Risk": ("risk", "risks"),
}

COMPACT_HANDOFF_FIELDS = {
    "Decision": ("decision", "issue", "context"),
    "Scope": ("scope", "paths", "touched paths"),
    "Review first": ("review first", "review-first", "review_first"),
    "Verified": ("verified", "verification"),
    "Risk": ("risk",),
}

COPYABLE_REVIEW_PACKET = """# Review Packet: <short title>

## What Changed
- 

## Why
- 

## Non-goals
- 

## Paths: auto

## Verification
- 

## Risk
- 
"""

COPYABLE_REVIEW_HANDOFF = """Decision: #123 or small fix
Scope: auto
Review first: path/to/file
Verified: test command or manual check
Risk: none
"""


@dataclass
class Report:
    ok: bool
    profile: str
    changed_files: list[str]
    allowed_paths: list[str]
    review_packet: dict[str, str]
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


def read_text(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8-sig", errors="ignore")

def normalize_heading(text: str) -> str:
    return " ".join(text.strip().strip("#").strip().lower().replace("_", " ").split())


def parse_sections(markdown: str | None) -> dict[str, str]:
    if not markdown:
        return {}

    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            heading = stripped[3:].strip()
            inline_value = ""
            if ":" in heading:
                heading, inline_value = heading.split(":", 1)
                inline_value = inline_value.strip()
            current = normalize_heading(heading)
            sections.setdefault(current, [])
            if inline_value:
                sections[current].append(inline_value)
            continue
        if current:
            sections[current].append(line.rstrip())
    return {heading: "\n".join(lines).strip() for heading, lines in sections.items()}


def section_value(sections: dict[str, str], aliases: tuple[str, ...]) -> str:
    for alias in aliases:
        value = sections.get(normalize_heading(alias), "")
        if value.strip():
            return value.strip()
    return ""


def extract_review_packet(corridor_text: str | None) -> dict[str, str]:
    sections = parse_sections(corridor_text)
    return {
        label: section_value(sections, aliases)
        for label, aliases in REVIEW_PACKET_SECTIONS.items()
    }


def extract_compact_handoff(corridor_text: str | None) -> dict[str, str]:
    handoff = {label: "" for label in COMPACT_HANDOFF_FIELDS}
    if not corridor_text:
        return handoff

    aliases = {
        normalize_heading(alias): label
        for label, field_aliases in COMPACT_HANDOFF_FIELDS.items()
        for alias in field_aliases
    }
    for line in corridor_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        label = aliases.get(normalize_heading(key))
        if label and value.strip() and not handoff[label]:
            handoff[label] = value.strip()
    return handoff


def find_pr_body() -> str | None:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        return None
    try:
        event = json.loads(Path(event_path).read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    pull = event.get("pull_request") or {}
    return pull.get("body")


def load_corridor(repo: Path, corridor_file: str, source: str) -> str | None:
    if source in {"auto", "file"}:
        text = read_text(repo / corridor_file)
        if text:
            return text
        if corridor_file == DEFAULT_CORRIDOR_FILE:
            for legacy_file in LEGACY_CORRIDOR_FILES:
                text = read_text(repo / legacy_file)
                if text:
                    return text
    if source in {"auto", "body"}:
        return find_pr_body()
    return None


def extract_paths(corridor_text: str | None) -> list[str]:
    sections = parse_sections(corridor_text)
    paths_text = section_value(sections, REVIEW_PACKET_SECTIONS["Paths"])
    if not paths_text:
        return []

    paths: list[str] = []
    for line in paths_text.splitlines():
        stripped = line.strip()
        if not stripped or not stripped.startswith(("-", "*")):
            continue
        raw = stripped[1:].strip().strip("`")
        if raw:
            paths.append(normalize_path(raw))
    return paths


def is_paths_auto(value: str) -> bool:
    cleaned = value.strip().strip("`").lower()
    if cleaned == "auto":
        return True
    lines = [line.strip().strip("`").lower() for line in value.splitlines() if line.strip()]
    return len(lines) == 1 and lines[0] in {"auto", "- auto", "* auto"}


def auto_paths_from_changed_files(changed_files: list[str], always_allowed: list[str]) -> list[str]:
    return [
        path
        for path in changed_files
        if path and not any(path_matches(path, pattern) for pattern in always_allowed)
    ]


def extract_changed_files(repo: Path, changed_files_arg: str | None, base_ref: str | None) -> list[str]:
    env_files = os.environ.get("CORRIDOR_CHANGED_FILES")
    if changed_files_arg:
        if changed_files_arg.startswith("@"):
            path = Path(changed_files_arg[1:])
            raw = path.read_text(encoding="utf-8-sig", errors="ignore")
        else:
            raw = changed_files_arg
        return [normalize_path(p) for p in split_file_list(raw)]
    if env_files:
        return [normalize_path(p) for p in split_file_list(env_files)]

    base = base_ref or os.environ.get("GITHUB_BASE_REF")
    if base and not base.startswith("origin/"):
        base = f"origin/{base}"
    if not base:
        base = "origin/main"
    proc = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise SystemExit(f"failed to read changed files: {proc.stderr.strip()}")
    return [normalize_path(p) for p in proc.stdout.splitlines() if p.strip()]


def split_file_list(raw: str) -> list[str]:
    if "\n" in raw:
        return [p.strip() for p in raw.splitlines() if p.strip()]
    return [p.strip() for p in raw.split(",") if p.strip()]


def split_path_list(raw: str) -> list[str]:
    paths: list[str] = []
    chunks = raw.splitlines() if "\n" in raw else raw.split(",")
    for chunk in chunks:
        cleaned = chunk.strip().strip("`")
        if cleaned.startswith(("-", "*")):
            cleaned = cleaned[1:].strip().strip("`")
        if cleaned:
            paths.append(normalize_path(cleaned))
    return paths


def path_matches(path: str, pattern: str) -> bool:
    path = normalize_path(path)
    pattern = normalize_path(pattern)
    if pattern.endswith("/**"):
        prefix = pattern[:-3].rstrip("/")
        return path == prefix or path.startswith(prefix + "/")
    return fnmatch.fnmatch(path, pattern)


def is_allowed(path: str, allowed_paths: list[str], always_allowed: list[str]) -> bool:
    return any(path_matches(path, pattern) for pattern in always_allowed + allowed_paths)


def is_dependency_file(path: str) -> bool:
    path = normalize_path(path)
    name = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(path, f"**/{pattern}") for pattern in DEPENDENCY_GLOBS)


def evaluate(
    *,
    changed_files: list[str],
    corridor_text: str | None,
    profile: str = "packet",
    corridor_required: bool = True,
    allow_dependencies: bool = False,
    max_changed_files: int = 0,
    small_change_max_files: int = 0,
    always_allowed: list[str] | None = None,
) -> Report:
    requested_profile = (profile or "packet").strip().lower()
    profile = requested_profile if requested_profile in {"packet", "compact"} else "packet"
    changed = [normalize_path(p) for p in changed_files if normalize_path(p)]
    allowed_paths = extract_paths(corridor_text)
    review_packet = extract_review_packet(corridor_text)
    handoff = extract_compact_handoff(corridor_text) if profile == "compact" else {}
    issues: list[str] = []
    warnings: list[str] = []
    always = list(always_allowed or DEFAULT_ALWAYS_ALLOWED)
    deps = [p for p in changed if is_dependency_file(p)]
    if profile == "compact":
        scope = handoff.get("Scope", "")
        if is_paths_auto(scope):
            allowed_paths = auto_paths_from_changed_files(changed, always)
        elif scope:
            allowed_paths = split_path_list(scope)
    elif is_paths_auto(review_packet.get("Paths", "")):
        allowed_paths = auto_paths_from_changed_files(changed, always)

    small_change_fast_path = (
        corridor_required
        and not corridor_text
        and small_change_max_files > 0
        and 0 < len(changed) <= small_change_max_files
        and not deps
    )

    if requested_profile != profile:
        issues.append(f"unknown profile `{requested_profile}`; expected `packet` or `compact`")

    if small_change_fast_path:
        warnings.append(
            f"small change fast path: review packet skipped for {len(changed)} changed file(s)"
        )
    elif profile == "compact" and corridor_required and not corridor_text:
        issues.append("compact handoff is required, but no corridor text was found")
    elif profile == "packet" and corridor_required and not corridor_text:
        issues.append("review packet is required, but no corridor text was found")
    elif profile == "compact" and corridor_text:
        for label, value in handoff.items():
            if not value:
                issues.append(f"compact handoff is missing `{label}`")
        review_first = normalize_path(handoff.get("Review first", ""))
        if review_first and review_first not in changed:
            issues.append(f"review first is not a changed file: {review_first}")
    elif profile == "packet" and corridor_text:
        for label, value in review_packet.items():
            if not value:
                issues.append(f"review packet is missing `## {label}`")

    if max_changed_files > 0 and len(changed) > max_changed_files:
        issues.append(f"changed file count is {len(changed)}, above max_changed_files={max_changed_files}")

    outside: list[str] = []
    if allowed_paths:
        outside = [p for p in changed if not is_allowed(p, allowed_paths, always)]
        if outside:
            issues.append("changed files outside corridor paths: " + ", ".join(outside))

    if deps and not allow_dependencies:
        issues.append("dependency manifest changed without allow_dependencies=true: " + ", ".join(deps))

    return Report(
        ok=not issues,
        profile=profile,
        changed_files=changed,
        allowed_paths=allowed_paths,
        review_packet=review_packet,
        handoff=handoff,
        outside_files=outside,
        dependency_files=deps,
        issues=issues,
        warnings=warnings,
    )


def compact_markdown(value: str) -> list[str]:
    return [line.rstrip() for line in value.splitlines() if line.strip()]


def should_show_packet_template(report: Report) -> bool:
    return report.profile == "packet" and any(
        issue.startswith("review packet is required")
        or issue.startswith("review packet is missing")
        for issue in report.issues
    )


def should_show_handoff_template(report: Report) -> bool:
    return report.profile == "compact" and any(
        issue.startswith("compact handoff is required")
        or issue.startswith("compact handoff is missing")
        for issue in report.issues
    )


def render_markdown(report: Report) -> str:
    status = "PASS" if report.ok else "FAIL"
    lines = [
        f"# Corridor CI: {status}",
        "",
        f"- changed files: {len(report.changed_files)}",
        f"- corridor paths: {len(report.allowed_paths)}",
    ]

    if report.profile == "compact" and any(report.handoff.values()):
        lines.append("")
        lines.append("## Review Handoff")
        for label in ("Decision", "Scope", "Review first", "Verified", "Risk"):
            value = report.handoff.get(label, "")
            if not value:
                continue
            lines.append("")
            lines.append(f"### {label}")
            lines.extend(compact_markdown(value))

    if report.profile == "packet" and any(report.review_packet.values()):
        lines.append("")
        lines.append("## Review Packet")
        for label in ("What Changed", "Why", "Verification", "Risk"):
            value = report.review_packet.get(label, "")
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

    if report.issues:
        lines.append("")
        lines.append("## Issues")
        lines.extend(f"- {issue}" for issue in report.issues)
    if should_show_packet_template(report):
        lines.append("")
        lines.append("## Copyable Review Packet")
        lines.append("")
        lines.append("```md")
        lines.extend(COPYABLE_REVIEW_PACKET.splitlines())
        lines.append("```")
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a PR against a declared corridor.")
    parser.add_argument("--repo", default=".", help="repository checkout path")
    parser.add_argument("--mode", choices=("fail", "warn"), default=os.environ.get("INPUT_MODE", "warn"))
    parser.add_argument("--profile", choices=("packet", "compact"), default=os.environ.get("INPUT_PROFILE", "packet"))
    parser.add_argument("--source", choices=("auto", "file", "body"), default=os.environ.get("INPUT_SOURCE", "auto"))
    parser.add_argument("--corridor-file", default=os.environ.get("INPUT_CORRIDOR_FILE", DEFAULT_CORRIDOR_FILE))
    parser.add_argument("--corridor-required", default=os.environ.get("INPUT_CORRIDOR_REQUIRED", "true"))
    parser.add_argument("--allow-dependencies", default=os.environ.get("INPUT_ALLOW_DEPENDENCIES", "false"))
    parser.add_argument("--max-changed-files", type=int, default=int(os.environ.get("INPUT_MAX_CHANGED_FILES", "0") or "0"))
    parser.add_argument(
        "--small-change-max-files",
        type=int,
        default=int(os.environ.get("INPUT_SMALL_CHANGE_MAX_FILES", "0") or "0"),
        help="allow PRs without a review packet when changed-file count is at or below this value",
    )
    parser.add_argument(
        "--changed-files",
        default=os.environ.get("INPUT_CHANGED_FILES"),
        help="inline comma/newline file list, or @path to a newline-delimited changed-file list",
    )
    parser.add_argument("--base-ref", default=os.environ.get("INPUT_BASE_REF"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo = Path(args.repo).resolve()
    corridor = load_corridor(repo, args.corridor_file, args.source)
    changed = extract_changed_files(repo, args.changed_files, args.base_ref)
    report = evaluate(
        changed_files=changed,
        corridor_text=corridor,
        profile=args.profile,
        corridor_required=truthy(args.corridor_required),
        allow_dependencies=truthy(args.allow_dependencies),
        max_changed_files=args.max_changed_files,
        small_change_max_files=args.small_change_max_files,
    )
    markdown = render_markdown(report)
    print(markdown)
    write_step_summary(markdown)
    return exit_code(report, args.mode)


if __name__ == "__main__":
    sys.exit(main())
