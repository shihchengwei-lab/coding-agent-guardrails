"""Path-based and output-based risk scanner.

Path matching uses *segment / basename* matching, NOT substring matching.
This avoids false positives like ``auth`` matching ``author.md``. Plan §8.

Output scanning reads RAW logs (not redacted), because the redactor may have
hidden the very pattern we want to flag (e.g. a printed ``rm -rf`` line).
But scanner evidence NEVER includes the raw matched text — only the pattern
label and line number. This guarantees output scanning cannot leak secrets
through risk flag evidence. Plan §12.

This module is pure: it operates on strings and dataclasses, never the
filesystem or git.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from agentcam.models import ChangedFile, RiskFlag, RiskLevel


# ---------------------------------------------------------------------------
# Path patterns (plan §8, §12.5)
# ---------------------------------------------------------------------------

# (segment, rule_label) — segment-match: any directory or basename equals
# segment, OR basename starts with `<segment>.` or `<segment>-`.
HIGH_PATH_SEGMENTS: list[tuple[str, str]] = [
    ("auth", "auth path"),
    ("login", "login path"),
    ("permission", "permission path"),
    ("permissions", "permissions path"),
    ("middleware", "middleware path"),
    ("session", "session path"),
    ("jwt", "jwt path"),
    ("oauth", "oauth path"),
    ("migration", "migration path"),
    ("migrations", "migrations path"),
    ("secret", "secret path"),
    ("secrets", "secrets path"),
    ("credential", "credential path"),
    ("credentials", "credentials path"),
    ("terraform", "terraform path"),
    ("k8s", "kubernetes (k8s) path"),
    ("kubernetes", "kubernetes path"),
    ("helm", "helm path"),
]

MEDIUM_PATH_SEGMENTS: list[tuple[str, str]] = [
    (".devcontainer", "devcontainer config"),
]

# Directory prefix matching (full prefix on the normalized path).
HIGH_PATH_PREFIXES: list[tuple[str, str]] = [
    (".github/workflows/", "GitHub Actions workflow"),
]

MEDIUM_PATH_PREFIXES: list[tuple[str, str]] = [
    ("docker-compose", "docker compose config"),
]

# Exact basename matching.
HIGH_PATH_BASENAMES: list[tuple[str, str]] = [
    ("schema.prisma", "Prisma schema"),
    ("fly.toml", "fly.io config"),
    ("render.yaml", "render.com config"),
    ("vercel.json", "vercel config"),
    ("netlify.toml", "netlify config"),
    ("cloudflare.toml", "cloudflare config"),
]

MEDIUM_PATH_BASENAMES: list[tuple[str, str]] = [
    ("package.json", "npm package manifest"),
    ("package-lock.json", "npm lockfile"),
    ("pnpm-lock.yaml", "pnpm lockfile"),
    ("yarn.lock", "yarn lockfile"),
    ("requirements.txt", "pip requirements"),
    ("pyproject.toml", "Python project manifest"),
    ("poetry.lock", "poetry lockfile"),
    ("uv.lock", "uv lockfile"),
    ("Dockerfile", "Dockerfile"),
]

# Lowercase extension matching (e.g. ".tf").
HIGH_PATH_EXTENSIONS: list[tuple[str, str]] = [
    (".tf", "terraform file"),
    (".tfvars", "terraform vars"),
]


# ---------------------------------------------------------------------------
# Secret-like filename patterns (plan §11)
# ---------------------------------------------------------------------------

# Matched against the basename. If any pattern matches, the file is treated
# as secret-like: scanner flags HIGH and report.py replaces the filename in
# all markdown surfaces.
_SECRET_LIKE_BASENAME_PATTERNS: list[re.Pattern[str]] = [
    # All patterns use re.IGNORECASE: case-insensitive filesystems on
    # Windows and macOS treat `.ENV` and `.env` as the same file, so
    # the scanner must too. (Codex source-review CRITICAL.)
    re.compile(r"^\.env$", re.IGNORECASE),
    re.compile(r"^\.env\.", re.IGNORECASE),
    re.compile(r"credential", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"\.pem$", re.IGNORECASE),
    re.compile(r"\.key$", re.IGNORECASE),
    re.compile(r"^id_(rsa|dsa|ecdsa|ed25519)", re.IGNORECASE),
    re.compile(r"\.pfx$", re.IGNORECASE),
    re.compile(r"\.p12$", re.IGNORECASE),
    re.compile(r"^\.npmrc$", re.IGNORECASE),
    re.compile(r"^\.pypirc$", re.IGNORECASE),
]


def is_secret_like_filename(path: str) -> bool:
    """True if the basename of ``path`` looks like it might hold a secret."""
    basename = PurePosixPath(_normalize(path)).name
    return any(p.search(basename) for p in _SECRET_LIKE_BASENAME_PATTERNS)


# ---------------------------------------------------------------------------
# Path matching helpers
# ---------------------------------------------------------------------------

def _normalize(path: str) -> str:
    """Normalize Windows backslashes to forward slashes."""
    return path.replace("\\", "/")


def _segments(path: str) -> list[str]:
    return [s for s in _normalize(path).split("/") if s]


def path_matches_segment(path: str, segment: str) -> bool:
    """Segment matching.

    Returns True if any directory or basename equals ``segment`` exactly, OR
    if a basename starts with ``segment.`` or ``segment-``.

    Examples (segment="auth"):
        match: src/auth/login.py, auth.ts, auth-helper.js
        no:    src/author.md, src/authorization-docs/x.md
    """
    segs = _segments(path)
    if segment in segs:
        return True
    basename = segs[-1] if segs else ""
    return basename.startswith(segment + ".") or basename.startswith(segment + "-")


def _path_matches_prefix(path: str, prefix: str) -> bool:
    return _normalize(path).startswith(prefix)


def _path_matches_basename(path: str, basename: str) -> bool:
    return PurePosixPath(_normalize(path)).name == basename


def _path_matches_extension(path: str, ext: str) -> bool:
    return _normalize(path).lower().endswith(ext.lower())


def _is_internal_path(path: str) -> bool:
    """True if path is inside .git/agentcam/ — our own output. Plan §1."""
    norm = _normalize(path)
    return norm.startswith(".git/agentcam/") or "/agentcam/runs/" in norm


# ---------------------------------------------------------------------------
# Path scanner
# ---------------------------------------------------------------------------

def scan_paths(
    changed: list[ChangedFile],
    *,
    ruleset: "RuleSet | None" = None,
) -> list[RiskFlag]:
    """Generate risk flags from a list of changed files.

    Skips files inside ``.git/agentcam/`` (our own output). For each file:
    - HIGH if status is ``staged_deleted`` / ``unstaged_deleted``
    - HIGH if filename is secret-like
    - HIGH/MEDIUM by path segment / prefix / basename / extension rules

    ``ruleset`` selects which rules to apply; ``None`` means the
    built-in default from :func:`default_ruleset`. The substrate for
    roadmap #4 (YAML custom rules).
    """
    rs = ruleset if ruleset is not None else default_ruleset()
    flags: list[RiskFlag] = []

    for cf in changed:
        if _is_internal_path(cf.path):
            continue

        path = cf.path
        is_secret = is_secret_like_filename(path)
        evidence_path = "<redacted-secret-filename>" if is_secret else path

        if cf.status in ("staged_deleted", "unstaged_deleted"):
            flags.append(RiskFlag(
                level="HIGH",
                rule="tracked file deleted",
                evidence=evidence_path,
            ))

        if is_secret:
            flags.append(RiskFlag(
                level="HIGH",
                rule="secret-like filename",
                evidence="<redacted-secret-filename>",
            ))

        # Try matchers in HIGH then MEDIUM order. First hit per matcher
        # class wins (keeps the report tidy). The matcher-class split is
        # preserved deliberately -- collapsing into a single list per
        # severity would change the dedup semantic. See PathMatchers
        # docstring.
        _emit_first_match(path, rs.high_paths.segments, "HIGH",
                          evidence_path, flags, _seg_match)
        _emit_first_match(path, rs.high_paths.prefixes, "HIGH",
                          evidence_path, flags, _path_matches_prefix)
        _emit_first_match(path, rs.high_paths.basenames, "HIGH",
                          evidence_path, flags, _path_matches_basename)
        _emit_first_match(path, rs.high_paths.extensions, "HIGH",
                          evidence_path, flags, _path_matches_extension)
        _emit_first_match(path, rs.medium_paths.segments, "MEDIUM",
                          evidence_path, flags, _seg_match)
        _emit_first_match(path, rs.medium_paths.basenames, "MEDIUM",
                          evidence_path, flags, _path_matches_basename)
        _emit_first_match(path, rs.medium_paths.prefixes, "MEDIUM",
                          evidence_path, flags, _path_matches_prefix)
        # Built-in medium-extensions is empty; loop kept as a forward-
        # compat slot so custom RuleSets (e.g. YAML-loaded user rules)
        # can register medium-severity extension matchers without
        # another scan_paths edit.
        _emit_first_match(path, rs.medium_paths.extensions, "MEDIUM",
                          evidence_path, flags, _path_matches_extension)

    return flags


def _seg_match(path: str, segment: str) -> bool:
    return path_matches_segment(path, segment)


def _emit_first_match(
    path: str,
    rules: list[tuple[str, str]],
    level: RiskLevel,
    evidence: str,
    out: list[RiskFlag],
    match_fn,
) -> bool:
    for rule_key, label in rules:
        if match_fn(path, rule_key):
            out.append(RiskFlag(level=level, rule=label, evidence=evidence))
            return True
    return False


# ---------------------------------------------------------------------------
# Output patterns (plan §12)
# ---------------------------------------------------------------------------

HIGH_OUTPUT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # POSIX shell high-risk
    (re.compile(r"\bgit\s+reset\s+--hard\b"), "git reset --hard"),
    (re.compile(r"\brm\s+-rf\s+/(?!tmp\b)"), "rm -rf root-like path"),
    (re.compile(r"\brm\s+-rf\s+~"), "rm -rf home"),
    (re.compile(r"\brm\s+-rf\s+\$"), "rm -rf with variable"),
    (re.compile(r"\bchmod\s+777\b"), "chmod 777"),
    (re.compile(r"\bcurl\s+[^|]*\|\s*(sh|bash|zsh)\b"), "curl pipe to shell"),
    (re.compile(r"\bwget\s+[^|]*\|\s*(sh|bash|zsh)\b"), "wget pipe to shell"),
    # PowerShell equivalents
    (
        re.compile(r"(?i)Remove-Item\s+-Recurse\s+-Force\s+(?:/|~|C:\\|\\\\)"),
        "PowerShell Remove-Item -Recurse -Force",
    ),
    (re.compile(r"(?i)\bInvoke-Expression\b"), "PowerShell Invoke-Expression"),
    (re.compile(r"(?i)\biex\s+\("), "PowerShell iex"),
    # Conflict markers leaked into stdout/stderr
    (re.compile(r"^<{7}\s", re.MULTILINE), "conflict marker (<<<<<<<)"),
    (re.compile(r"^>{7}\s", re.MULTILINE), "conflict marker (>>>>>>>)"),
    (re.compile(r"^={7}$", re.MULTILINE), "conflict marker (=======)"),
    # Force push
    (
        re.compile(r"\bgit\s+push\s+(?:-f\b|--force\b|--force-with-lease\b)"),
        "git push --force",
    ),
]

MEDIUM_OUTPUT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"(?i)\b(?:tests?\s+failed|failing\s+tests?|failed\s+tests?)\b"),
        "tests failed",
    ),
    (
        re.compile(r"(?i)\b(?:lint|build|typecheck|typescript)\s+(?:failed|error)\b"),
        "lint/build/typecheck failed",
    ),
    (
        re.compile(r"(?i)\b(?:panic|segmentation\s+fault|stack\s+overflow)\b"),
        "runtime panic / segfault",
    ),
]


@dataclass(frozen=True)
class _OutputHit:
    label: str
    line_no: int


def _scan_output_text(
    text: str,
    patterns: list[tuple[re.Pattern[str], str]],
) -> list[_OutputHit]:
    hits: list[_OutputHit] = []
    for pat, label in patterns:
        for m in pat.finditer(text):
            line_no = text.count("\n", 0, m.start()) + 1
            hits.append(_OutputHit(label=label, line_no=line_no))
    return hits


def scan_output(
    raw_text: str,
    *,
    stream_label: str,
    ruleset: "RuleSet | None" = None,
) -> list[RiskFlag]:
    """Scan a raw log stream for HIGH / MEDIUM output patterns.

    ``stream_label`` is e.g. ``"stdout.log"`` or ``"stderr.log"``; it
    appears in evidence. Evidence intentionally never contains the raw
    matched text. ``ruleset`` selects which output patterns to apply;
    ``None`` means the built-in default.
    """
    rs = ruleset if ruleset is not None else default_ruleset()
    flags: list[RiskFlag] = []
    flags.extend(
        _consolidate(_scan_output_text(raw_text, list(rs.high_output)),
                     stream_label, "HIGH")
    )
    flags.extend(
        _consolidate(_scan_output_text(raw_text, list(rs.medium_output)),
                     stream_label, "MEDIUM")
    )
    return flags


def _consolidate(
    hits: list[_OutputHit],
    stream_label: str,
    level: RiskLevel,
) -> list[RiskFlag]:
    by_label: dict[str, list[int]] = {}
    for h in hits:
        by_label.setdefault(h.label, []).append(h.line_no)

    flags: list[RiskFlag] = []
    for label, line_nos in by_label.items():
        line_nos = sorted(set(line_nos))
        line_part = ", ".join(str(n) for n in line_nos[:5])
        if len(line_nos) > 5:
            line_part += ", ..."
        plural = "s" if len(line_nos) > 1 else ""
        evidence = (
            f"{stream_label} line {line_part} "
            f"({len(line_nos)} occurrence{plural})"
        )
        flags.append(RiskFlag(
            level=level,
            rule=f"output_pattern: {label}",
            evidence=evidence,
        ))
    return flags


# ---------------------------------------------------------------------------
# Rule registry (the substrate YAML custom rules will plug into)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PathMatchers:
    """One severity's bundle of path matchers, grouped by matcher kind.

    Kept split (not a single ``list[PathRule]`` discriminated union)
    so the existing scan_paths behavior is preserved bit-for-bit: each
    matcher kind can independently emit one flag per file, so a single
    file matching both a segment rule AND an extension rule still
    produces two flags. Folding into a single list would change that
    dedup semantic — see ``docs/design.md`` (forthcoming) #26.
    """

    segments: tuple[tuple[str, str], ...] = ()
    prefixes: tuple[tuple[str, str], ...] = ()
    basenames: tuple[tuple[str, str], ...] = ()
    extensions: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class RuleSet:
    """A complete set of scanning rules.

    Built-in default is :data:`_BUILTIN_RULESET`; obtain via
    :func:`default_ruleset`. YAML loading (roadmap #4) will produce a
    merged :class:`RuleSet` with user rules layered on top of the
    built-in.
    """

    high_paths: PathMatchers = field(default_factory=PathMatchers)
    medium_paths: PathMatchers = field(default_factory=PathMatchers)
    high_output: tuple[tuple[re.Pattern[str], str], ...] = ()
    medium_output: tuple[tuple[re.Pattern[str], str], ...] = ()


_BUILTIN_RULESET = RuleSet(
    high_paths=PathMatchers(
        segments=tuple(HIGH_PATH_SEGMENTS),
        prefixes=tuple(HIGH_PATH_PREFIXES),
        basenames=tuple(HIGH_PATH_BASENAMES),
        extensions=tuple(HIGH_PATH_EXTENSIONS),
    ),
    medium_paths=PathMatchers(
        segments=tuple(MEDIUM_PATH_SEGMENTS),
        prefixes=tuple(MEDIUM_PATH_PREFIXES),
        basenames=tuple(MEDIUM_PATH_BASENAMES),
        extensions=(),
    ),
    high_output=tuple(HIGH_OUTPUT_PATTERNS),
    medium_output=tuple(MEDIUM_OUTPUT_PATTERNS),
)


def default_ruleset() -> RuleSet:
    """Return the built-in :class:`RuleSet` shipped with agentcam.

    A function (not a constant export) so future call sites can be
    intercepted -- e.g. a user-config layer could compose this with
    YAML-loaded user rules without monkey-patching module state.
    """
    return _BUILTIN_RULESET


# ---------------------------------------------------------------------------
# Ruleset provenance (decision #29)
# ---------------------------------------------------------------------------

# Stable identifier for the built-in rule set shipped with this release.
# Keep this id in sync with the agentcam release line if you ever ship a
# parallel ruleset (e.g. an "agentcam-strict" preset); the *version* on
# the provenance struct is the agentcam version that built it.
BUILTIN_RULESET_ID = "agentcam-default"


def _canonical_ruleset(rs: "RuleSet") -> dict:
    """Project a :class:`RuleSet` to a JSON-serializable canonical form.

    Matcher tuples are preserved in declaration order, NOT sorted. The
    reason: ``scan_paths`` emits one flag per matcher class per file
    via first-match-wins (see ``_emit_first_match``). So
    ``src/auth/login.py`` reports either ``auth path`` or
    ``login path`` depending on which segment comes first in the
    tuple — reordering changes scanner behavior, so the hash must
    track order. Same logic for ``_outputs``.

    ``re.Pattern.flags`` is included so changing ``IGNORECASE`` or
    ``MULTILINE`` on a built-in pattern propagates into the hash;
    otherwise two rulesets that scan differently could share a hash.

    Sorted-keys at the JSON layer (`json.dumps(..., sort_keys=True)`
    in :func:`compute_ruleset_sha256`) still applies to the
    top-level keys (`high_paths` / `medium_paths` / ...). Only the
    matcher *content* preserves order.
    """
    def _pm(matchers: PathMatchers) -> dict:
        return {
            "segments": [list(t) for t in matchers.segments],
            "prefixes": [list(t) for t in matchers.prefixes],
            "basenames": [list(t) for t in matchers.basenames],
            "extensions": [list(t) for t in matchers.extensions],
        }

    def _outputs(rows) -> list:
        return [[pat.pattern, pat.flags, label] for pat, label in rows]

    return {
        "high_paths": _pm(rs.high_paths),
        "medium_paths": _pm(rs.medium_paths),
        "high_output": _outputs(rs.high_output),
        "medium_output": _outputs(rs.medium_output),
    }


def compute_ruleset_sha256(rs: "RuleSet") -> str:
    """Deterministic ``sha256:<hex>`` over the canonical form of ``rs``.

    Stability guarantee: a rule set whose effective scanner behavior
    is identical (same matchers in the same declaration order, same
    pattern strings AND flags) hashes the same across runs. Adding,
    removing, reordering, or re-flagging a rule changes the hash.
    Used by :func:`provenance_for_builtin_ruleset` and by future
    YAML-loader integration to put a single behavior-tracking
    fingerprint on every report.
    """
    canonical = _canonical_ruleset(rs)
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def provenance_for_builtin_ruleset() -> "RulesetProvenance":
    """Provenance struct for the default (built-in-only) rule set.

    YAML-loaded custom rules (roadmap #4) will return a different
    struct from a sibling factory; the manifest schema is shared.
    """
    # Local import: models.py imports nothing from scanner, so this
    # avoids a circular import at module-load time.
    from agentcam.models import RulesetProvenance
    from agentcam import __version__

    merged = compute_ruleset_sha256(default_ruleset())
    return RulesetProvenance(
        builtin_ruleset_id=BUILTIN_RULESET_ID,
        builtin_ruleset_version=__version__,
        custom_rules_path=None,
        custom_rules_sha256=None,
        merged_rules_sha256=merged,
        load_status="builtin_only",
    )
