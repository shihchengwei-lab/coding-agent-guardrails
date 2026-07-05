"""Tests for agentcam.redaction.

Covers plan §6 (streaming buffer model) and §11 (report-wide redaction).

Notable regression guards:
- Token split across chunk boundary must not leak through redacted log.
- PEM block spanning multiple lines must be replaced even when interleaved
  with chunks.
- Incomplete PEM at end-of-stream becomes [REDACTED:PEM_INCOMPLETE], not raw.
"""
from __future__ import annotations

import io

from agentcam.redaction import (
    StreamingRedactor,
    redact_argv,
    redact_inline,
    redact_text,
)


# ---------------------------------------------------------------------------
# Inline patterns
# ---------------------------------------------------------------------------

class TestInlineRedaction:
    def test_aws_access_key(self):
        out = redact_inline("AKIA1234567890ABCDEF more text")
        assert "AKIA" not in out
        assert "[REDACTED:AWS_AK]" in out

    def test_github_pat(self):
        out = redact_inline("GITHUB_TOKEN=ghp_" + "A" * 40)
        # ENV_ASSIGN matches first and replaces the value with [REDACTED:ENV];
        # either way the raw token must not survive.
        assert "ghp_AAAA" not in out

    def test_openai_key(self):
        out = redact_inline("API key sk-" + "A" * 30 + " trailing")
        assert "sk-AAAA" not in out
        assert "[REDACTED:LLM_API_KEY]" in out or "[REDACTED:ENV]" in out

    def test_bearer_token(self):
        out = redact_inline("Authorization: Bearer " + "A" * 40)
        assert "AAAAAAAA" not in out
        assert "Bearer [REDACTED]" in out

    def test_jwt(self):
        jwt = "eyJabcdef.eyJghijkl.signature"
        out = redact_inline(f"token: {jwt}")
        assert "eyJabcdef" not in out
        assert "[REDACTED:JWT]" in out

    def test_env_assignment_token(self):
        out = redact_inline("API_TOKEN=supersecret123")
        assert "supersecret123" not in out
        assert "[REDACTED:ENV]" in out

    def test_env_assignment_password(self):
        out = redact_inline("DB_PASSWORD=hunter2")
        assert "hunter2" not in out

    def test_env_assignment_credential(self):
        out = redact_inline("MY_CREDENTIAL=letmein")
        assert "letmein" not in out

    def test_env_case_insensitive(self):
        out = redact_inline("api_token=sneakylowercase")
        assert "sneakylowercase" not in out

    def test_passthrough_for_non_secrets(self):
        out = redact_inline("def foo():\n    return 42\n")
        assert out == "def foo():\n    return 42\n"

    def test_npm_token(self):
        out = redact_inline("npm_" + "A" * 36 + " in env")
        assert "npm_AAAA" not in out

    def test_gitlab_pat(self):
        out = redact_inline("glpat-" + "A" * 25 + " is sensitive")
        assert "glpat-AAAA" not in out


# ---------------------------------------------------------------------------
# One-shot redact_text and redact_argv
# ---------------------------------------------------------------------------

class TestRedactText:
    def test_pem_block_collapsed(self):
        text = (
            "before\n"
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "AAAA\nBBBB\n"
            "-----END RSA PRIVATE KEY-----\n"
            "after\n"
        )
        out = redact_text(text)
        assert "BEGIN RSA" not in out
        assert "AAAA" not in out
        assert "[REDACTED:PEM]" in out
        assert "before" in out and "after" in out


class TestRedactArgv:
    def test_argv_with_api_key(self):
        argv = ["claude", "--api-key", "sk-AAAAAAAAAAAAAAAAAAAA"]
        red = redact_argv(argv)
        assert red[0] == "claude"
        assert red[1] == "--api-key"
        # The secret value must not survive in any argv element.
        assert all("sk-AAAA" not in a for a in red)

    def test_argv_with_bearer(self):
        argv = ["curl", "-H", "Authorization: Bearer " + "X" * 40]
        red = redact_argv(argv)
        assert all("XXXXXXXX" not in a for a in red)


# ---------------------------------------------------------------------------
# StreamingRedactor
# ---------------------------------------------------------------------------

def _drain(chunks: list[bytes]) -> bytes:
    """Helper: feed chunks into a StreamingRedactor and return output bytes."""
    buf = io.BytesIO()
    r = StreamingRedactor(buf)
    for c in chunks:
        r.feed(c)
    r.close()
    return buf.getvalue()


class TestStreamingBasics:
    def test_passthrough_simple_text(self):
        out = _drain([b"hello world\n"])
        assert out == b"hello world\n"

    def test_redacts_simple_secret(self):
        out = _drain([b"GITHUB_TOKEN=ghp_" + b"A" * 40 + b"\n"])
        assert b"ghp_AAAA" not in out
        assert b"[REDACTED" in out

    def test_handles_no_trailing_newline(self):
        out = _drain([b"no newline at end"])
        assert out == b"no newline at end"


class TestStreamingChunkBoundary:
    def test_token_split_across_chunks_redacted(self):
        # Plan §6 regression: a token cut by chunk boundary must still be
        # caught when both halves are present in the buffer at flush time.
        # Send "GITHUB_TOKEN=ghp_<40 A's>\n" in two halves with the cut
        # falling inside the secret.
        full = b"GITHUB_TOKEN=ghp_" + b"A" * 40 + b"\n"
        cut = 25  # middle of the secret
        chunks = [full[:cut], full[cut:]]
        out = _drain(chunks)
        assert b"ghp_AAAA" not in out, f"Secret leaked: {out!r}"
        assert b"[REDACTED" in out

    def test_split_inside_aws_access_key(self):
        full = b"AKIA1234567890ABCDEF rest\n"
        chunks = [full[:6], full[6:]]
        out = _drain(chunks)
        assert b"AKIA" not in out
        assert b"[REDACTED:AWS_AK]" in out


class TestStreamingPEM:
    def test_complete_pem_block_redacted(self):
        chunks = [
            b"prefix line\n",
            b"-----BEGIN RSA PRIVATE KEY-----\n",
            b"MIIBOgIBAAJBAKj34GkxFhD90vcNLYLI\n",
            b"more secret material\n",
            b"-----END RSA PRIVATE KEY-----\n",
            b"suffix line\n",
        ]
        out = _drain(chunks)
        assert b"BEGIN RSA" not in out
        assert b"MIIBOgI" not in out
        assert b"[REDACTED:PEM]" in out
        assert b"prefix line" in out
        assert b"suffix line" in out

    def test_pem_in_single_chunk(self):
        block = (
            b"-----BEGIN PRIVATE KEY-----\n"
            b"AAAA\n"
            b"BBBB\n"
            b"-----END PRIVATE KEY-----\n"
        )
        out = _drain([b"before\n" + block + b"after\n"])
        assert b"AAAA" not in out and b"BBBB" not in out
        assert b"[REDACTED:PEM]" in out

    def test_incomplete_pem_at_close_marked(self):
        # BEGIN with no END before close() must redact, not leak.
        chunks = [
            b"-----BEGIN RSA PRIVATE KEY-----\n",
            b"halfway through secret AAAA\n",
            b"BBBB still no end\n",
        ]
        out = _drain(chunks)
        assert b"AAAA" not in out
        assert b"BBBB" not in out
        assert b"[REDACTED:PEM_INCOMPLETE]" in out


class TestStreamingPassthrough:
    def test_large_safe_payload(self):
        chunks = [b"x" * 4096 + b"\n" for _ in range(20)]
        out = _drain(chunks)
        # All x's preserved, no false-positive redaction.
        assert out.count(b"x") == 4096 * 20
        assert b"REDACTED" not in out

    def test_multiple_lines_per_chunk(self):
        out = _drain([b"line1\nline2\nline3\n"])
        assert out == b"line1\nline2\nline3\n"


# ---------------------------------------------------------------------------
# Codex source-review CRITICAL regressions (added 2026-05-16)
# ---------------------------------------------------------------------------

class TestCriticalLongLineTokenNotSplit:
    """Codex source-review CRITICAL: SOFT_FLUSH boundary must not split a
    token across stream chunks. Reproducing the bug needs:

    1. Chunk 1 alone exceeds SOFT_FLUSH_BYTES (so it force-flushes).
    2. Chunk 1 ends partway through a secret token.
    3. Chunk 2 contains the rest of the token.

    Without the fix, chunk 1 flushes the token's first half un-redacted
    (regex requires the whole token to match), and chunk 2's tail alone
    doesn't match either. The token leaks split across two writes.
    """

    def test_long_line_token_at_flush_boundary_redacted(self):
        SOFT_FLUSH_BYTES = 8 * 1024
        token = b"ghp_" + b"A" * 40  # 44 bytes
        half = len(token) // 2
        # Chunk 1: padding + first half of token, no newline anywhere.
        # Padding pushes chunk 1 past SOFT_FLUSH so flush_lines force-flushes.
        chunk1 = b"x" * (SOFT_FLUSH_BYTES + 100) + token[:half]
        chunk2 = token[half:] + b"\n"
        out = _drain([chunk1, chunk2])
        assert b"ghp_AAAA" not in out, (
            "Token split by SOFT_FLUSH boundary leaked"
        )


class TestCriticalArgvCaseInsensitivity:
    """Codex source-review CRITICAL: redact_argv must match secret-like
    filenames regardless of case (case-insensitive filesystems on
    Windows / macOS).
    """

    def test_uppercase_dot_env_in_argv_redacted(self):
        argv = ["vim", ".ENV.PRODUCTION"]
        red = redact_argv(argv)
        assert ".ENV.PRODUCTION" not in " ".join(red)

    def test_uppercase_id_rsa_in_argv_redacted(self):
        argv = ["scp", "ID_RSA", "host:"]
        red = redact_argv(argv)
        assert "ID_RSA" not in " ".join(red)


# ---------------------------------------------------------------------------
# Codex source-review HIGH regressions (added 2026-05-16, batch 2a)
# ---------------------------------------------------------------------------

class TestHighUtf16NoLeak:
    """Codex source-review HIGH: bytes with NUL interleaving (UTF-16LE
    output, e.g. some Windows console configurations) must not let secrets
    bypass redaction. Fix strips NUL bytes after decoding.
    """

    def test_utf16le_github_token_redacted(self):
        token_chars = b"GITHUB_TOKEN=ghp_" + b"A" * 40
        # UTF-16LE: each ASCII char becomes 2 bytes (low byte then NUL).
        token_utf16 = b"".join(bytes([c, 0]) for c in token_chars)
        out = _drain([token_utf16 + b"\n\x00"])
        # After fix: NULs stripped during decode, regex catches the token,
        # REDACTED appears in output.
        assert b"REDACTED" in out
        # And the token chars (NUL-stripped) are not present.
        assert b"ghp_AAAA" not in out.replace(b"\x00", b"")


class TestHighUrlBasicAuth:
    """Codex source-review HIGH: HTTP_PROXY-style URLs that embed
    basic-auth (`user:password@host`) must have the credential segment
    redacted, even when the surrounding env-var name doesn't match the
    KEY/TOKEN/SECRET keyword list.
    """

    def test_http_proxy_url_basic_auth_redacted(self):
        out = redact_inline(
            "HTTP_PROXY=https://alice:hunter2@proxy.corp.com:8080"
        )
        assert "hunter2" not in out
        assert "alice" not in out

    def test_https_url_basic_auth_in_body_text_redacted(self):
        out = redact_inline(
            "Cloning https://gh:short_token_value@github.com/x/y.git"
        )
        assert "short_token_value" not in out
