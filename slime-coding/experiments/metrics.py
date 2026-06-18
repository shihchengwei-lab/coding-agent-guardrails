#!/usr/bin/env python3
"""Compute the git-derived subset of run metrics for one experiment run.

This automates the deterministic columns in docs/VALIDATION_PLAN.md §10.2
(touched/new files, new dependencies, public-API additions, out-of-corridor
files, corridor changed). The human-judged fields (task_success,
over_implementation_review, reviewer_accept, ...) are emitted as null/0 for a
reviewer to fill in by hand, so a run record is never silently fabricated.

Usage:
    python3 experiments/metrics.py --repo <dir> --task T1 \
        --condition baseline --run 1 [--base HEAD] [--pubspec pubspec.yaml]

It measures the working tree against --base (default HEAD), so run it after the
agent has finished but before committing.
"""
import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys


def git(cwd, *args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def corridor_globs(cwd):
    path = os.path.join(cwd, ".slime", "corridor.md")
    globs, in_paths = [], False
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s.lower().startswith("## paths"):
                    in_paths = True
                    continue
                if in_paths:
                    if s.startswith("##"):
                        break
                    m = re.match(r"-\s+(.+)", s)
                    if m:
                        globs.append(m.group(1).strip())
    except OSError:
        pass
    return globs


def parse_deps(text):
    deps, in_block = set(), False
    for line in text.splitlines():
        if re.match(r"^dependencies:\s*$", line):
            in_block = True
            continue
        if in_block:
            if re.match(r"^\S", line):
                break
            m = re.match(r"^  ([\w-]+):", line)
            if m:
                deps.add(m.group(1))
    return deps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--task", required=True)
    ap.add_argument("--condition", required=True,
                    choices=["baseline", "prompt-only", "hooked-slime", "hooked-no-l1"])
    ap.add_argument("--run", type=int, required=True)
    ap.add_argument("--base", default="HEAD")
    ap.add_argument("--pubspec", default="pubspec.yaml")
    a = ap.parse_args()
    cwd = os.path.abspath(a.repo)

    touched = [n for n in git(cwd, "diff", a.base, "--name-only").splitlines() if n]
    new_files = [n for n in git(cwd, "ls-files", "--others", "--exclude-standard").splitlines() if n]

    diff = git(cwd, "diff", a.base)
    api = sum(
        1 for line in diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
        and re.match(r"(export\s|class\s|enum\s|mixin\s|typedef\s|extension\s)", line[1:].lstrip())
    )

    globs = corridor_globs(cwd)
    out_corr = [n for n in touched + new_files
                if globs and not n.startswith(".slime/")
                and not any(fnmatch.fnmatch(n, g) for g in globs)]

    head_pub = git(cwd, "show", a.base + ":" + a.pubspec)
    new_deps = []
    if head_pub:
        try:
            with open(os.path.join(cwd, a.pubspec), encoding="utf-8") as f:
                new_deps = sorted(parse_deps(f.read()) - parse_deps(head_pub))
        except OSError:
            pass

    corridor_changed = bool(git(cwd, "status", "--porcelain", "--", ".slime/corridor.md").strip())

    record = {
        "task_id": a.task,
        "condition": a.condition,
        "run_id": a.run,
        # human-judged — fill in by hand:
        "task_success": None,
        "task_success_score": None,
        "tests_pass": None,
        # git-derived — computed here:
        "touched_files": len(touched),
        "new_files": len(new_files),
        "new_dependencies": len(new_deps),
        "public_api_additions": api,
        "out_of_corridor_files": len(out_corr),
        "corridor_changed": corridor_changed,
        # human-judged — fill in by hand:
        "pruned_path_revived": None,
        "unrelated_refactor_count": None,
        "over_implementation_review": None,
        "reviewer_accept": None,
        "manual_reverts_required": None,
        "blocks_count": None,
        "false_block_count": None,
        "manual_steps": None,
        "turn_count": None,
        "notes": "",
        "_detail": {
            "out_of_corridor_files": out_corr,
            "new_dependencies": new_deps,
        },
    }
    json.dump(record, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
