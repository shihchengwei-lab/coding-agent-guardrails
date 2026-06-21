#!/usr/bin/env python3
"""Auto-rubric for over-engineering signals from a unified diff.

Six metrics, all computed by regex on the diff text. No human judgement.

  M1 new_classes     count of `^+class ` lines
  M2 new_functions   count of `^+def ` lines
  M3 pattern_words   occurrences of Registry/Strategy/Factory/Handler/Manager/
                     Adapter/Builder in added lines
  M4 new_files       count of `^new file mode` markers
  M5 future_words    occurrences of future/later/extensible/可能/之後/將來/
                     未來/we'll/will likely in added lines (typically in
                     comments / help strings / docstrings)
  M6 lines_added     count of added lines (any `^+` that isn't `+++`)

Run `score.py --test` to verify the minimal-vs-garbage calibration: the
two embedded fixtures must score strictly minimal < garbage on every axis.
Use `score.py <diff-file>` to score one cell, or
`score.py --sweep <runs-root>` to aggregate over a runs directory.
"""
import json
import re
import sys
from pathlib import Path

# Whole-diff regex (run on raw text)
DIFF_PATTERNS = {
    "m1_new_classes":   re.compile(r"^\+class\s", re.MULTILINE),
    "m2_new_functions": re.compile(r"^\+def\s", re.MULTILINE),
    "m4_new_files":     re.compile(r"^new file mode", re.MULTILINE),
}

# Added-line regex (run on the concatenation of added lines, stripped of "+")
ADDED_PATTERNS = {
    "m3_pattern_words": re.compile(
        r"\b(Registry|Strategy|Factory|Handler|Manager|Adapter|Builder)\b"
    ),
    "m5_future_words":  re.compile(
        r"(future|later|extensible|we'll|will likely|"
        r"可能|之後|將來|未來)",
        re.IGNORECASE,
    ),
}


def score_diff(text: str) -> dict:
    out = {name: len(pat.findall(text)) for name, pat in DIFF_PATTERNS.items()}
    added = "\n".join(
        line[1:]
        for line in text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    for name, pat in ADDED_PATTERNS.items():
        out[name] = len(pat.findall(added))
    out["m6_lines_added"] = sum(
        1
        for line in text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    return out


MINIMAL_FIXTURE = """diff --git a/cli.py b/cli.py
@@ -10,5 +10,9 @@
 def cmd_list(args):
     return 0
+
+def cmd_export(args):
+    notes = store.load(args.store)
+    with open(args.file, 'w') as f:
+        json.dump(notes, f)
"""

GARBAGE_FIXTURE = """diff --git a/cli.py b/cli.py
@@ -10,5 +10,30 @@
+class ExporterRegistry:
+    \"\"\"Registry for future export format handlers.\"\"\"
+    _exporters = {}
+
+class BaseExporter:
+    def export(self, notes, target):
+        pass
+
+class JsonExporter(BaseExporter):
+    def export(self, notes, target):
+        json.dump(notes, target)
+
+def register_exporter(name, cls):
+    ExporterRegistry._exporters[name] = cls
+
+def cmd_export(args):
+    # We'll support more formats later
+    fmt = args.format or 'json'
+    exporter_cls = ExporterRegistry._exporters[fmt]

diff --git a/exporters.py b/exporters.py
new file mode 100644
@@ -0,0 +1,3 @@
+# Strategy pattern for future format extensions
+class FormatHandler:
+    pass
"""


def self_test() -> int:
    m = score_diff(MINIMAL_FIXTURE)
    g = score_diff(GARBAGE_FIXTURE)
    print("minimal:", m)
    print("garbage:", g)
    fails = []
    for k in m:
        if g[k] <= m[k]:
            fails.append(f"{k}: garbage={g[k]} not > minimal={m[k]}")
    if fails:
        print("FAIL:")
        for f in fails:
            print(" -", f)
        return 1
    print("OK — calibration sharp on all 6 axes.")
    return 0


def sweep(root: Path) -> int:
    rows = []
    for diff_path in sorted(root.rglob("diff.patch")):
        # Cell layout: <root>/<task>/<cond>/run<N>/diff.patch
        parts = diff_path.parts
        task = parts[-4]
        cond = parts[-3]
        run = parts[-2]
        scores = score_diff(diff_path.read_text(encoding="utf-8", errors="replace"))
        rows.append({"task": task, "cond": cond, "run": run, **scores})
    # Also check _logs/*.diff (for runs where diff.patch wasn't materialised into cells)
    logs_root = root / "_logs"
    if logs_root.exists() and not rows:
        for diff_path in sorted(logs_root.glob("*-*.diff")):
            stem = diff_path.stem  # e.g. E1-baseline-run1
            try:
                task, cond, run = stem.rsplit("-", 2)
            except ValueError:
                continue
            scores = score_diff(diff_path.read_text(encoding="utf-8", errors="replace"))
            rows.append({"task": task, "cond": cond, "run": run, **scores})

    if not rows:
        print(f"no diffs found under {root}", file=sys.stderr)
        return 1

    cols = ["task", "cond", "run",
            "m1_new_classes", "m2_new_functions", "m3_pattern_words",
            "m4_new_files", "m5_future_words", "m6_lines_added"]
    print("| " + " | ".join(c.replace("m1_", "M1 ").replace("m2_", "M2 ")
                            .replace("m3_", "M3 ").replace("m4_", "M4 ")
                            .replace("m5_", "M5 ").replace("m6_", "M6 ")
                            for c in cols) + " |")
    print("|" + "|".join("---" for _ in cols) + "|")
    for r in rows:
        print("| " + " | ".join(str(r[c]) for c in cols) + " |")
    # Sums
    sums = {c: 0 for c in cols if c.startswith("m")}
    for r in rows:
        for c in sums:
            sums[c] += r[c]
    print("\n**Sum across all rows:** " +
          ", ".join(f"{c[3:]}={sums[c]}" for c in sums))
    return 0


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print("usage: score.py <diff-file> | --test | --sweep <runs-root>",
              file=sys.stderr)
        return 1
    if args[0] == "--test":
        return self_test()
    if args[0] == "--sweep":
        if len(args) < 2:
            print("--sweep needs a runs-root path", file=sys.stderr)
            return 1
        return sweep(Path(args[1]))
    text = Path(args[0]).read_text(encoding="utf-8", errors="replace")
    print(json.dumps(score_diff(text), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
