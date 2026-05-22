"""`agentcam export <run_id>` — build a share-safe redacted ZIP bundle.

The bundle is intentionally minimal:
  - AGENT_RUN_REPORT.md
  - manifest.redacted.json (every string value passes through redaction)
  - stdout.redacted.log / stderr.redacted.log (best-effort scrubbed copies)
  - checksums.txt (sha256 over every other file)
  - EXPORT_NOTES.md (what is / isn't included; redaction caveats)

Raw stdout.log / stderr.log are intentionally NOT in the default bundle —
those preserve everything the wrapped command printed, including secrets
the streaming redactor missed. The `--include-raw` flag is the
documented opt-in for users who understand the risk and need raw logs
anyway.

See ``docs/design.md`` decision #31 for the full rationale, including
why a flat ZIP rather than a directory tree, why the manifest is
redacted in place instead of cloned, and the path-traversal defense
strategy.
"""
from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path

# Regex used as the first line of defense against junky run_id input.
# Real run_ids look like `YYYYMMDD-HHMMSS-<ms>-<slug>[-<hex>]`. The
# resolved-parent check inside :func:`resolve_run_dir` is the actual
# security mechanism — this is just to fail fast with a clear error
# on obvious garbage.
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


class ExportError(RuntimeError):
    """User-facing export problem. cli.py maps this to exit code 2."""


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def resolve_run_dir(git_dir: Path, run_id: str) -> Path:
    """Resolve ``<git_dir>/agentcam/runs/<run_id>/`` safely.

    ``run_id == "latest"`` selects the most recently modified run.
    Adversarial inputs (``..``, absolute paths, slashes, symlinks
    pointing outside the runs dir) are rejected via a resolved-parent
    check. Returns the absolute, resolved path or raises
    :class:`ExportError`.
    """
    runs_dir = git_dir / "agentcam" / "runs"

    if run_id == "latest":
        if not runs_dir.exists():
            raise ExportError(
                f"No agentcam runs found under {runs_dir}. "
                "Run something with `agentcam run -- ...` first."
            )
        candidates = [p for p in runs_dir.iterdir() if p.is_dir()]
        if not candidates:
            raise ExportError(
                f"No agentcam runs found under {runs_dir}. "
                "Run something with `agentcam run -- ...` first."
            )
        return max(candidates, key=lambda p: p.stat().st_mtime)

    if not _RUN_ID_PATTERN.match(run_id):
        raise ExportError(
            f"Invalid run_id: {run_id!r}. Must consist of "
            "alphanumerics, '.', '_', or '-' (single path segment)."
        )

    run_dir = runs_dir / run_id
    # Resolved-parent check is the actual safety guard. Even a run_id
    # that smuggled `..` past the regex, or a symlink planted inside
    # runs/, would resolve away from the expected parent and be
    # rejected here.
    try:
        resolved = run_dir.resolve()
        expected_parent = runs_dir.resolve()
    except OSError as e:
        raise ExportError(f"Could not resolve run dir {run_dir}: {e}")
    if resolved.parent != expected_parent:
        raise ExportError(
            f"run_id resolves outside the runs/ directory: {run_id!r}"
        )
    if not resolved.is_dir():
        raise ExportError(f"No run found with id: {run_id}")
    return resolved


# ---------------------------------------------------------------------------
# Manifest redaction
# ---------------------------------------------------------------------------

def _walk_redact(obj, redact_text_fn):
    if isinstance(obj, dict):
        return {k: _walk_redact(v, redact_text_fn) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk_redact(v, redact_text_fn) for v in obj]
    if isinstance(obj, str):
        return redact_text_fn(obj)
    return obj


def redact_manifest(manifest_json_text: str) -> dict:
    """Return a redacted version of a manifest.json blob.

    Two passes:
    1. Every string value in the dict tree passes through
       :func:`agentcam.redaction.redact_text` (handles tokens, PEM
       blocks, env-assignments, URL basic-auth).
    2. ``command_argv_raw`` is forced to mirror
       ``command_argv_redacted`` so the bundle never carries the raw
       form -- raw argv can contain shell-escaped secrets that don't
       match any token shape and so survive ``redact_text``.

    Structure is preserved. Keys are not renamed.
    """
    from agentcam.redaction import redact_text
    data = json.loads(manifest_json_text)
    redacted = _walk_redact(data, redact_text)
    if "command_argv_redacted" in redacted:
        redacted["command_argv_raw"] = redacted["command_argv_redacted"]
    return redacted


# ---------------------------------------------------------------------------
# Bundle building
# ---------------------------------------------------------------------------

def build_bundle_files(
    run_dir: Path,
    *,
    include_raw: bool,
) -> dict[str, bytes]:
    """Build the in-memory ``filename -> bytes`` mapping for the bundle.

    Missing source artifacts (e.g. report.md absent because the run
    crashed mid-write) are skipped silently; EXPORT_NOTES.md calls them
    out at the bottom so the recipient knows what was missing.
    """
    files: dict[str, bytes] = {}

    report_md = run_dir / "AGENT_RUN_REPORT.md"
    manifest_json = run_dir / "manifest.json"
    stdout_redacted = run_dir / "stdout.redacted.log"
    stderr_redacted = run_dir / "stderr.redacted.log"
    stdout_raw = run_dir / "stdout.log"
    stderr_raw = run_dir / "stderr.log"

    if report_md.exists():
        files["AGENT_RUN_REPORT.md"] = report_md.read_bytes()
    if manifest_json.exists():
        redacted = redact_manifest(manifest_json.read_text("utf-8"))
        files["manifest.redacted.json"] = (
            json.dumps(redacted, indent=2).encode("utf-8")
        )
    if stdout_redacted.exists():
        files["stdout.redacted.log"] = stdout_redacted.read_bytes()
    if stderr_redacted.exists():
        files["stderr.redacted.log"] = stderr_redacted.read_bytes()

    if include_raw:
        if stdout_raw.exists():
            files["stdout.log"] = stdout_raw.read_bytes()
        if stderr_raw.exists():
            files["stderr.log"] = stderr_raw.read_bytes()

    # Checksums + notes are computed last so they can reference everything
    # else by name.
    files["checksums.txt"] = _checksums_for(files)
    files["EXPORT_NOTES.md"] = _export_notes(
        run_dir=run_dir, files=files, include_raw=include_raw,
    ).encode("utf-8")
    return files


def _checksums_for(files: dict[str, bytes]) -> bytes:
    """Produce the contents of checksums.txt over ``files`` so far.

    Format: ``sha256  <filename>  <hex>`` per line. Stable ordering so
    two bundles built from the same source are byte-identical except for
    the EXPORT_NOTES timestamp (we don't include a timestamp; intentional).
    """
    lines = []
    for name in sorted(files):
        h = hashlib.sha256(files[name]).hexdigest()
        lines.append(f"sha256  {name}  {h}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _export_notes(
    *,
    run_dir: Path,
    files: dict[str, bytes],
    include_raw: bool,
) -> str:
    have_report = "AGENT_RUN_REPORT.md" in files
    have_manifest = "manifest.redacted.json" in files
    have_redacted_stdout = "stdout.redacted.log" in files
    have_redacted_stderr = "stderr.redacted.log" in files

    missing = []
    if not have_report:
        missing.append(
            "- `AGENT_RUN_REPORT.md` was missing from the run directory."
        )
    if not have_manifest:
        missing.append(
            "- `manifest.json` was missing from the run directory."
        )
    if not have_redacted_stdout:
        missing.append(
            "- `stdout.redacted.log` was missing from the run directory."
        )
    if not have_redacted_stderr:
        missing.append(
            "- `stderr.redacted.log` was missing from the run directory."
        )

    parts: list[str] = [
        "# agentcam export notes",
        "",
        f"Source run: `{run_dir.name}`",
        "",
        "## What is included",
        "",
        "- `AGENT_RUN_REPORT.md` — the human-readable run report.",
        "- `manifest.redacted.json` — manifest with every string value "
        "passed through agentcam's redaction pipeline, and "
        "`command_argv_raw` overwritten with the redacted form so the "
        "raw argv never leaves the originating machine.",
        "- `stdout.redacted.log` / `stderr.redacted.log` — secrets "
        "stripped on a best-effort basis by the streaming redactor.",
        "- `checksums.txt` — sha256 for every other file in the bundle.",
        "",
        "## What is NOT included by default",
        "",
        "- Raw `stdout.log` / `stderr.log`. The raw logs preserve "
        "everything the wrapped command printed, including secret "
        "strings that the redactor's pattern set did not recognize. "
        "They are intentionally excluded from this bundle.",
        "- Pass `--include-raw` to `agentcam export` if you understand "
        "the risk and need them anyway.",
        "",
        "## Redaction is best-effort",
        "",
        "Secret detection is pattern-based. New token formats and "
        "context-specific secrets will not always match. Review the "
        "contents of this bundle before sharing it publicly. The raw "
        "logs at `.git/agentcam/runs/" + run_dir.name + "/` on the "
        "originating machine remain available for forensic review if "
        "something was missed.",
        "",
        "agentcam does not phone home. The bundle was produced locally; "
        "nothing was uploaded by `agentcam export`.",
    ]
    if include_raw:
        parts += [
            "",
            "## `--include-raw` was used",
            "",
            "This bundle includes raw `stdout.log` and `stderr.log`. "
            "Treat the bundle as sensitive: it may contain secrets that "
            "the redactor missed.",
        ]
    if missing:
        parts += ["", "## Missing artifacts", "", *missing]
    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------------------
# ZIP writer
# ---------------------------------------------------------------------------

def write_zip(files: dict[str, bytes], out_path: Path) -> None:
    """Write ``files`` as a flat (no-prefix) ZIP at ``out_path``.

    Caller is responsible for the existing-file overwrite policy
    (:func:`export` enforces ``--force``).
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Write to a sibling .tmp and rename so a crash mid-write doesn't
    # leave a partial zip the user might accidentally share.
    tmp_path = out_path.with_name(out_path.name + ".tmp")
    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, content in files.items():
                zf.writestr(name, content)
        tmp_path.replace(out_path)
    except Exception:
        # Best-effort cleanup of the partial tmp on failure.
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------

def export(
    *,
    git_dir: Path,
    run_id: str,
    output_path: Path,
    force: bool,
    include_raw: bool,
) -> Path:
    """Build the bundle and write it to ``output_path``.

    Returns the resolved source run directory (so the caller can print
    a "exported from .../<run_id>" line). Raises :class:`ExportError`
    on any user-facing problem.
    """
    run_dir = resolve_run_dir(git_dir, run_id)
    if output_path.exists() and not force:
        raise ExportError(
            f"Output already exists: {output_path}. "
            "Pass --force to overwrite."
        )
    files = build_bundle_files(run_dir, include_raw=include_raw)
    write_zip(files, output_path)
    return run_dir
