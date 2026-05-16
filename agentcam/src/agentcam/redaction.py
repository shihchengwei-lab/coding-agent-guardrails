"""Secret redaction with streaming buffer (plan §6).

Two redaction modes:

- Inline (line-based): single-line patterns (tokens, env assignments) applied
  to lines as they complete in the streaming buffer.
- Block (PEM): multi-line patterns. When BEGIN is seen without a matching END,
  the buffer holds until END arrives or PEM_HARD_LIMIT is reached.

Best-effort. We do NOT promise to catch every secret. See README "Known
limitations" and ``docs/design.md`` decision 20.
"""
from __future__ import annotations

import re
from typing import IO


# ---------------------------------------------------------------------------
# Inline patterns
# ---------------------------------------------------------------------------

_INLINE_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("AWS_AK", re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED:AWS_AK]"),
    (
        "AWS_SK",
        re.compile(
            r"(aws_secret_access_key\s*=\s*['\"]?)([A-Za-z0-9/+=]{40})(['\"]?)",
            re.IGNORECASE,
        ),
        r"\1[REDACTED:AWS_SK]\3",
    ),
    ("SLACK", re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}"), "[REDACTED:SLACK]"),
    (
        "GITHUB_PAT",
        re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
        "[REDACTED:GITHUB_PAT]",
    ),
    ("NPM_TOKEN", re.compile(r"npm_[A-Za-z0-9]{36}"), "[REDACTED:NPM_TOKEN]"),
    (
        "GITLAB_PAT",
        re.compile(r"glpat-[A-Za-z0-9_\-]{20,}"),
        "[REDACTED:GITLAB_PAT]",
    ),
    (
        "LLM_API_KEY",
        re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
        "[REDACTED:LLM_API_KEY]",
    ),
    (
        "BEARER",
        re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-+/=]{20,}"),
        r"\1[REDACTED]",
    ),
    (
        "JWT",
        re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
        "[REDACTED:JWT]",
    ),
    (
        "ENV_ASSIGN",
        re.compile(
            r"(?i)([A-Z_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL)[A-Z_]*\s*=\s*)([^\s\"']+)"
        ),
        r"\1[REDACTED:ENV]",
    ),
    # URL basic-auth: https://user:password@host. Catches HTTP_PROXY=...,
    # `git clone https://user:token@github.com/...`, etc., even when the
    # surrounding env-var name doesn't match the KEY/TOKEN/SECRET keyword
    # list above. (Codex source-review HIGH.)
    (
        "URL_BASIC_AUTH",
        re.compile(
            r"(\bhttps?://)([^:/?#@\s]+):([^@\s]+)(@)",
            re.IGNORECASE,
        ),
        r"\1[REDACTED]:[REDACTED]\4",
    ),
]

# PEM `BEGIN` line takes an optional uppercase/digit algorithm prefix
# followed by a space (e.g. ``RSA``, ``EC``, ``ED25519``, ``ENCRYPTED``,
# ``OPENSSH``). PKCS#8 keys have no prefix: ``-----BEGIN PRIVATE KEY-----``.
_PEM_BEGIN_RE = re.compile(r"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----")
_PEM_END_RE = re.compile(r"-----END (?:[A-Z0-9]+ )?PRIVATE KEY-----")
_PEM_BLOCK_RE = re.compile(
    r"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----"
    r"[\s\S]+?"
    r"-----END (?:[A-Z0-9]+ )?PRIVATE KEY-----"
)


def redact_inline(text: str) -> str:
    """Apply all inline (single-line) redaction patterns to ``text``."""
    for _name, pattern, replacement in _INLINE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact_text(text: str) -> str:
    """One-shot redaction for non-streaming callers (e.g. command argv).

    Applies PEM block redaction first, then inline redaction. Suitable for
    short strings where the entire content is available at once.
    """
    text = _PEM_BLOCK_RE.sub("[REDACTED:PEM]", text)
    return redact_inline(text)


# IGNORECASE: case-insensitive filesystems on Windows and macOS treat
# `.ENV.PRODUCTION` the same as `.env.production`, so argv redaction
# must too. (Codex source-review CRITICAL.)
_SECRET_FILENAME_INLINE_RE = re.compile(
    r"("
    r"\.env(?:\.[A-Za-z0-9_-]+)?"
    r"|id_(?:rsa|dsa|ecdsa|ed25519)(?:\.[A-Za-z0-9_-]+)?"
    r"|\.npmrc|\.pypirc"
    r"|[A-Za-z0-9_.-]*credential[A-Za-z0-9_.-]*"
    r"|[A-Za-z0-9_.-]*secret[A-Za-z0-9_.-]*"
    r"|[A-Za-z0-9_.-]+\.(?:pem|key|pfx|p12)"
    r")",
    re.IGNORECASE,
)


def redact_argv(argv: list[str]) -> list[str]:
    """Redact a list of argv strings.

    Two passes per element:
    1. :func:`redact_text` — token / PEM / env-assignment patterns
    2. Secret-like filename substrings (``.env.production``, ``id_rsa``,
       ``server.pem``, ``foo-credential.json`` etc.) are replaced with
       ``<redacted-secret-filename>``.

    The second pass exists because argv itself is user-visible in the
    markdown ``Command:`` section, so ``--config .env.production`` would
    leak the secret-like filename even though the value isn't a token.
    """
    out: list[str] = []
    for a in argv:
        a = redact_text(a)
        a = _SECRET_FILENAME_INLINE_RE.sub("<redacted-secret-filename>", a)
        out.append(a)
    return out


# ---------------------------------------------------------------------------
# Streaming redactor
# ---------------------------------------------------------------------------

class StreamingRedactor:
    """Streaming secret redactor.

    Maintains a sliding buffer to handle:

    - tokens split across read chunks (single-line patterns)
    - multi-line PEM blocks (block patterns)

    Usage::

        with open("stdout.redacted.log", "wb") as fp:
            r = StreamingRedactor(fp)
            r.feed(chunk1)
            r.feed(chunk2)
            r.close()  # flushes any remaining pending bytes
    """

    # Force flush of incomplete-line buffer once it grows past this size.
    SOFT_FLUSH_BYTES = 8 * 1024
    # When force-flushing a no-newline buffer, retain this many trailing
    # chars in `pending` so a token straddling the flush boundary can
    # reassemble with the next chunk. Sized larger than any realistic
    # token (JWT < ~1KB, PEM uses newlines so doesn't hit this path).
    # (Codex source-review CRITICAL.)
    FLUSH_RESERVE_CHARS = 1024
    # Max bytes to hold while waiting for PEM END marker.
    PEM_HARD_LIMIT = 64 * 1024

    def __init__(self, out_fp: IO[bytes]):
        self._out = out_fp
        self._pending = ""

    def feed(self, chunk: bytes) -> None:
        if not chunk:
            return
        # Strip NUL bytes after decoding. NUL is valid UTF-8 (the NUL
        # character) but in real-world subprocess output its presence
        # almost always means UTF-16LE or binary interleaving — and it
        # breaks every regex in `_INLINE_PATTERNS` because no token
        # pattern accepts NUL between chars. Stripping lets regex see
        # the underlying ASCII run. (Codex source-review HIGH.)
        text = chunk.decode("utf-8", errors="replace").replace("\x00", "")
        if not text:
            return
        self._pending += text
        self._process(final=False)

    def close(self) -> None:
        self._process(final=True)

    # ----------------------------------------------------------- private

    def _process(self, *, final: bool) -> None:
        # Pass 1: collapse complete PEM blocks to [REDACTED:PEM].
        self._pending = _PEM_BLOCK_RE.sub("[REDACTED:PEM]", self._pending)

        # Pass 2: detect incomplete PEM (BEGIN without END).
        begin_match = _PEM_BEGIN_RE.search(self._pending)
        if begin_match:
            head = self._pending[: begin_match.start()]
            pem_tail = self._pending[begin_match.start():]

            # Head has no PEM concern; flush it fully.
            self._flush_lines(head, final=True)

            tail_bytes = len(pem_tail.encode("utf-8"))
            if tail_bytes >= self.PEM_HARD_LIMIT:
                self._out.write(b"[REDACTED:PEM_TRUNCATED]\n")
                self._pending = ""
            elif final:
                self._out.write(b"[REDACTED:PEM_INCOMPLETE]\n")
                self._pending = ""
            else:
                self._pending = pem_tail  # hold for next feed
            return

        # No incomplete PEM; flush completed lines.
        self._pending = self._flush_lines(self._pending, final=final)

    def _flush_lines(self, text: str, *, final: bool) -> str:
        """Emit completed lines from ``text``. Returns the unflushed remainder."""
        if not text:
            return ""
        if final:
            self._out.write(redact_inline(text).encode("utf-8"))
            return ""
        last_nl = text.rfind("\n")
        if last_nl < 0:
            # No newline. Hold until SOFT_FLUSH_BYTES, then force-flush all
            # but the trailing FLUSH_RESERVE_CHARS so a token straddling
            # the flush boundary can reassemble with the next chunk.
            if len(text) >= self.SOFT_FLUSH_BYTES:
                reserve = self.FLUSH_RESERVE_CHARS
                if len(text) > reserve:
                    flush_part = text[:-reserve]
                    remaining = text[-reserve:]
                else:
                    flush_part = ""
                    remaining = text
                if flush_part:
                    self._out.write(
                        redact_inline(flush_part).encode("utf-8")
                    )
                return remaining
            return text
        completed = text[: last_nl + 1]
        remaining = text[last_nl + 1:]
        self._out.write(redact_inline(completed).encode("utf-8"))
        return remaining
