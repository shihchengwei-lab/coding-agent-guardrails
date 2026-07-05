"""Tests for agentcam.runner.

Covers plan §2 (tee), §3 (argv-only), §9 (exit code), §14 (Windows).

Notable regression guards:
- exit code 256 must NOT mask to 0 (would have happened with returncode & 0xFF)
- known NTSTATUS values get human-readable interpretation
- 200KB on stdout AND stderr concurrently must not deadlock
- raw log preserves bytes as-is (no encoding pass)
"""
from __future__ import annotations

import platform
import signal
import sys
from pathlib import Path

import pytest

from agentcam.runner import (
    CommandNotFoundError,
    interpret_exit,
    resolve_command,
    run_wrapped,
)

PYTHON = sys.executable


class TestInterpretExit:
    def test_zero_is_success(self):
        d = interpret_exit(0)
        assert d.wrapper_exit == 0
        assert d.raw_returncode == 0
        assert d.interpretation == "success"
        assert d.interpretation_source == "known_table"
        assert d.raw_returncode_hex is None

    def test_user_defined_one(self):
        d = interpret_exit(1)
        assert d.wrapper_exit == 1
        assert d.raw_returncode == 1
        assert d.interpretation_source == "user_defined"

    def test_user_defined_255(self):
        d = interpret_exit(255)
        assert d.wrapper_exit == 1
        assert d.interpretation_source == "user_defined"

    def test_overflow_256_does_not_become_zero(self):
        # Regression: returncode & 0xFF would map 256 to 0 (failure -> success).
        # Plan §9 explicitly forbids this.
        d = interpret_exit(256)
        assert d.wrapper_exit == 1, "256 must be reported as failure, not success"
        assert d.raw_returncode == 256
        assert d.interpretation_source == "unknown"
        assert d.raw_returncode_hex == "0x00000100"

    def test_known_ntstatus_access_violation(self):
        d = interpret_exit(0xC0000005)
        assert d.wrapper_exit == 1
        assert d.interpretation == "STATUS_ACCESS_VIOLATION"
        assert d.interpretation_source == "known_table"
        assert d.raw_returncode_hex == "0xc0000005"

    def test_known_ntstatus_stack_overflow(self):
        d = interpret_exit(0xC00000FD)
        assert d.interpretation == "STATUS_STACK_OVERFLOW"
        assert d.interpretation_source == "known_table"

    def test_signal_sigkill(self):
        if platform.system().lower() == "windows":
            pytest.skip("POSIX-only signal test")
        d = interpret_exit(-signal.SIGKILL)
        assert d.wrapper_exit == 1
        assert d.interpretation_source == "signal"
        assert "SIGKILL" in d.interpretation

    def test_unknown_high_returncode(self):
        # Pick a high value not in the NTSTATUS table.
        d = interpret_exit(0x12345678)
        assert d.wrapper_exit == 1
        assert d.interpretation_source == "unknown"
        assert d.raw_returncode_hex == "0x12345678"


class TestResolveCommand:
    def test_resolves_python(self):
        rc = resolve_command([PYTHON, "-c", "pass"])
        assert rc.argv  # non-empty
        # On non-Windows or non-shim Windows binary, shell stays off.
        if not (platform.system().lower() == "windows"
                and rc.argv[0].lower().endswith((".cmd", ".bat"))):
            assert rc.use_shell is False

    def test_missing_command_raises(self):
        with pytest.raises(CommandNotFoundError):
            resolve_command(["agentcam-no-such-binary-xyzzy"])

    def test_empty_argv_raises(self):
        with pytest.raises(ValueError):
            resolve_command([])


class TestRunWrapped:
    def test_simple_stdout_captured(self, tmp_path: Path):
        result = run_wrapped(
            [PYTHON, "-c", "print('hello')"],
            cwd=tmp_path,
            stdout_raw_path=tmp_path / "stdout.log",
            stderr_raw_path=tmp_path / "stderr.log",
        )
        assert result.exit_detail.wrapper_exit == 0
        assert b"hello" in (tmp_path / "stdout.log").read_bytes()

    def test_stderr_captured(self, tmp_path: Path):
        result = run_wrapped(
            [PYTHON, "-c", "import sys; sys.stderr.write('boom\\n')"],
            cwd=tmp_path,
            stdout_raw_path=tmp_path / "stdout.log",
            stderr_raw_path=tmp_path / "stderr.log",
        )
        assert result.exit_detail.wrapper_exit == 0
        assert b"boom" in (tmp_path / "stderr.log").read_bytes()

    def test_exit_code_2_propagates(self, tmp_path: Path):
        result = run_wrapped(
            [PYTHON, "-c", "import sys; sys.exit(2)"],
            cwd=tmp_path,
            stdout_raw_path=tmp_path / "stdout.log",
            stderr_raw_path=tmp_path / "stderr.log",
        )
        assert result.exit_detail.wrapper_exit == 1
        assert result.exit_detail.raw_returncode == 2
        assert result.exit_detail.interpretation_source == "user_defined"

    def test_large_concurrent_output_no_deadlock(self, tmp_path: Path):
        # Plan §2: 200KB on stdout AND stderr concurrently must not deadlock.
        # Without threads-based tee this would freeze on pipe back-pressure.
        script = (
            "import sys\n"
            "for i in range(2000):\n"
            "    sys.stdout.write('x' * 100 + '\\n')\n"
            "    sys.stderr.write('y' * 100 + '\\n')\n"
        )
        result = run_wrapped(
            [PYTHON, "-c", script],
            cwd=tmp_path,
            stdout_raw_path=tmp_path / "stdout.log",
            stderr_raw_path=tmp_path / "stderr.log",
        )
        assert result.exit_detail.wrapper_exit == 0
        out_size = (tmp_path / "stdout.log").stat().st_size
        err_size = (tmp_path / "stderr.log").stat().st_size
        assert out_size >= 200_000, f"stdout truncated: {out_size}"
        assert err_size >= 200_000, f"stderr truncated: {err_size}"

    def test_non_utf8_bytes_preserved_in_raw(self, tmp_path: Path):
        # Plan §2: raw log writes bytes as-is, no decoding pass.
        result = run_wrapped(
            [
                PYTHON,
                "-c",
                "import sys; sys.stdout.buffer.write(b'\\xff\\xfe\\x80raw')",
            ],
            cwd=tmp_path,
            stdout_raw_path=tmp_path / "stdout.log",
            stderr_raw_path=tmp_path / "stderr.log",
        )
        assert result.exit_detail.wrapper_exit == 0
        out = (tmp_path / "stdout.log").read_bytes()
        assert b"\xff\xfe\x80raw" in out

    def test_no_newline_output(self, tmp_path: Path):
        result = run_wrapped(
            [PYTHON, "-c", "import sys; sys.stdout.write('nonewline')"],
            cwd=tmp_path,
            stdout_raw_path=tmp_path / "stdout.log",
            stderr_raw_path=tmp_path / "stderr.log",
        )
        assert result.exit_detail.wrapper_exit == 0
        assert (tmp_path / "stdout.log").read_bytes() == b"nonewline"

    def test_missing_command_raises(self, tmp_path: Path):
        with pytest.raises(CommandNotFoundError):
            run_wrapped(
                ["agentcam-no-such-binary-xyzzy"],
                cwd=tmp_path,
                stdout_raw_path=tmp_path / "stdout.log",
                stderr_raw_path=tmp_path / "stderr.log",
            )


# ---------------------------------------------------------------------------
# Codex source-review HIGH regressions (added 2026-05-16, batch 2c)
# ---------------------------------------------------------------------------

class TestHighCmdShimEscape:
    """Codex source-review HIGH: argv elements with cmd.exe metacharacters
    (``&``, ``|``, ``<``, ``>``, ``^``, ``%VAR%``) must not be re-interpreted
    by cmd.exe when running a ``.cmd`` / ``.bat`` shim.

    Tested cross-platform via the internal helper; the shim path itself is
    Windows-only but the escape logic is pure string manipulation.
    """

    def test_ampersand_is_caret_escaped(self):
        from agentcam.runner import _escape_for_cmd_shim
        result = _escape_for_cmd_shim(["foo.cmd", "arg & val"])
        # `&` inside the argv must be caret-escaped so cmd.exe doesn't
        # treat it as a command separator.
        assert "^&" in result

    def test_percent_is_doubled(self):
        from agentcam.runner import _escape_for_cmd_shim
        result = _escape_for_cmd_shim(["foo.cmd", "%VAR%"])
        # Variable expansion must be suppressed via `%%`.
        assert "%%VAR%%" in result

    def test_pipe_is_caret_escaped(self):
        from agentcam.runner import _escape_for_cmd_shim
        result = _escape_for_cmd_shim(["foo.cmd", "a | b"])
        assert "^|" in result

    def test_resolve_cmd_shim_uses_escape(self, tmp_path: Path, monkeypatch):
        """End-to-end on resolve_command: when shim path is detected, the
        returned argv[0] passes through _escape_for_cmd_shim."""
        from agentcam.runner import resolve_command

        # Force the shim path: pretend platform is Windows and shutil.which
        # returns a .cmd file.
        monkeypatch.setattr(
            "agentcam.runner.platform.system", lambda: "Windows"
        )
        monkeypatch.setattr(
            "agentcam.runner.shutil.which", lambda x: "C:\\tools\\fake.cmd"
        )
        rc = resolve_command(["fake", "x & y"])
        assert rc.use_shell is True
        # The cmdline string should contain caret-escaped `&`.
        assert "^&" in rc.argv[0]


class TestHighSigintCleanup:
    """Codex source-review HIGH: KeyboardInterrupt during proc.wait() must
    not leak tee threads (logs unflushed) or zombie subprocesses. Without
    the fix, Ctrl+C produces no report — exactly the moment a flight
    recorder is supposed to leave a trace.
    """

    def test_keyboard_interrupt_during_wait_still_joins_threads(
        self, tmp_path: Path, monkeypatch
    ):
        import subprocess as sp

        # Spawn a real subprocess so we get real pipes for the tee threads
        # to read from. Then wrap it so the first .wait() raises
        # KeyboardInterrupt and subsequent waits / terminate proceed.
        real_proc = sp.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdout=sp.PIPE, stderr=sp.PIPE, bufsize=0,
        )

        class FakeProc:
            def __init__(self, real):
                self._real = real
                self.stdout = real.stdout
                self.stderr = real.stderr
                self._wait_count = 0

            @property
            def returncode(self):
                return self._real.returncode

            def wait(self, timeout=None):
                self._wait_count += 1
                if self._wait_count == 1:
                    raise KeyboardInterrupt
                return self._real.wait(timeout=timeout)

            def terminate(self):
                self._real.terminate()

            def kill(self):
                self._real.kill()

        fake = FakeProc(real_proc)
        monkeypatch.setattr(
            "agentcam.runner.subprocess.Popen",
            lambda *a, **kw: fake,
        )

        # run_wrapped must NOT propagate KeyboardInterrupt; it must catch,
        # clean up, and return a RunResult.
        result = run_wrapped(
            [sys.executable, "-c", "pass"],
            cwd=tmp_path,
            stdout_raw_path=tmp_path / "stdout.log",
            stderr_raw_path=tmp_path / "stderr.log",
        )

        # Logs flushed (tee threads joined cleanly).
        assert (tmp_path / "stdout.log").is_file()
        assert (tmp_path / "stderr.log").is_file()

        # We did get a result back.
        assert result.exit_detail is not None
        # Subprocess was reaped (no zombie).
        assert real_proc.returncode is not None


# ---------------------------------------------------------------------------
# Stage 1: backend dispatcher (roadmap §2 setup for PTY-backed wrap)
# ---------------------------------------------------------------------------

class TestBackendDispatch:
    """``run_wrapped()`` routes to a named backend; default is ``'pipe'``.

    Pure-refactor stage for PTY-backed wrapping. Future backends
    (``'pty_posix'``, ``'pty_windows'``) plug in via the same dispatcher.
    """

    def test_default_backend_runs(self, tmp_path: Path):
        # No ``backend=`` kwarg -> 'pipe' default. Verifies the dispatcher
        # entry is reachable and forwards to the original behavior.
        result = run_wrapped(
            [PYTHON, "-c", "print('default-backend')"],
            cwd=tmp_path,
            stdout_raw_path=tmp_path / "stdout.log",
            stderr_raw_path=tmp_path / "stderr.log",
        )
        assert result.exit_detail.wrapper_exit == 0
        assert b"default-backend" in (tmp_path / "stdout.log").read_bytes()

    def test_explicit_pipe_backend_runs(self, tmp_path: Path):
        result = run_wrapped(
            [PYTHON, "-c", "print('explicit-pipe')"],
            cwd=tmp_path,
            stdout_raw_path=tmp_path / "stdout.log",
            stderr_raw_path=tmp_path / "stderr.log",
            backend="pipe",
        )
        assert result.exit_detail.wrapper_exit == 0
        assert b"explicit-pipe" in (tmp_path / "stdout.log").read_bytes()

    def test_unknown_backend_raises(self, tmp_path: Path):
        # CLAUDE.md "Do not hide errors or invalid states": an unknown backend
        # name must raise, not silently fall back to pipe.
        from agentcam.runner import UnknownBackendError

        with pytest.raises(UnknownBackendError):
            run_wrapped(
                [PYTHON, "-c", "pass"],
                cwd=tmp_path,
                stdout_raw_path=tmp_path / "stdout.log",
                stderr_raw_path=tmp_path / "stderr.log",
                backend="not-a-real-backend",
            )


# ---------------------------------------------------------------------------
# Stage 2: POSIX PTY backend (roadmap §2)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    platform.system().lower() == "windows",
    reason="POSIX-only PTY backend",
)
class TestPtyPosixBackend:
    """``backend='pty_posix'``: subprocess attached to a POSIX pty.

    TUI agents render because stdout is a TTY. stdout and stderr merge
    into one PTY stream — both go to stdout.log; stderr.log is created
    empty to keep the file-exists invariant the rest of the pipeline
    relies on. This stage covers non-interactive cases (no stdin
    forward); interactive support is a follow-up.
    """

    def test_simple_stdout_captured(self, tmp_path: Path):
        result = run_wrapped(
            [PYTHON, "-c", "print('hello-pty')"],
            cwd=tmp_path,
            stdout_raw_path=tmp_path / "stdout.log",
            stderr_raw_path=tmp_path / "stderr.log",
            backend="pty_posix",
        )
        assert result.exit_detail.wrapper_exit == 0
        assert b"hello-pty" in (tmp_path / "stdout.log").read_bytes()

    def test_exit_code_propagates(self, tmp_path: Path):
        result = run_wrapped(
            [PYTHON, "-c", "import sys; sys.exit(2)"],
            cwd=tmp_path,
            stdout_raw_path=tmp_path / "stdout.log",
            stderr_raw_path=tmp_path / "stderr.log",
            backend="pty_posix",
        )
        assert result.exit_detail.wrapper_exit == 1
        assert result.exit_detail.raw_returncode == 2

    def test_stderr_merges_into_stdout_log(self, tmp_path: Path):
        # PTY single-stream nature: stderr content surfaces in stdout.log;
        # stderr.log exists but is empty (file-exists invariant).
        result = run_wrapped(
            [PYTHON, "-c", "import sys; sys.stderr.write('boom\\n')"],
            cwd=tmp_path,
            stdout_raw_path=tmp_path / "stdout.log",
            stderr_raw_path=tmp_path / "stderr.log",
            backend="pty_posix",
        )
        assert result.exit_detail.wrapper_exit == 0
        assert b"boom" in (tmp_path / "stdout.log").read_bytes()
        assert (tmp_path / "stderr.log").is_file()
        assert (tmp_path / "stderr.log").read_bytes() == b""


@pytest.mark.skipif(
    platform.system().lower() != "windows",
    reason="Windows-only check that pty_posix rejects on Windows",
)
class TestPtyPosixBackendOnWindows:
    def test_raises_not_implemented_on_windows(self, tmp_path: Path):
        # No silent fallback to pipe; POSIX-only backend rejects explicitly.
        with pytest.raises(NotImplementedError, match="POSIX"):
            run_wrapped(
                [PYTHON, "-c", "pass"],
                cwd=tmp_path,
                stdout_raw_path=tmp_path / "stdout.log",
                stderr_raw_path=tmp_path / "stderr.log",
                backend="pty_posix",
            )


# ---------------------------------------------------------------------------
# Stage 2.5: stdin forward + raw mode + initial termsize for pty_posix
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    platform.system().lower() == "windows",
    reason="POSIX-only PTY backend",
)
class TestPtyPosixStdinForward:
    """Stage 2.5: parent stdin reaches subprocess via the master fd.

    Also verifies that the TTY-only helpers (raw mode, initial winsize)
    degrade gracefully when parent stdin is not a TTY (CI environment).
    """

    def test_stdin_forwards_to_subprocess(self, tmp_path: Path, monkeypatch):
        # Build a pipe whose read-end stands in for sys.stdin. The forward
        # thread reads via sys.stdin.fileno(); we push input through the
        # write-end. Subprocess echoes back via input() so we can assert
        # the bytes traversed parent -> master_fd -> slave -> subprocess.
        import os as _os
        r_fd, w_fd = _os.pipe()
        _os.write(w_fd, b"piped-input\n")
        _os.close(w_fd)

        class _FakeStdin:
            def fileno(self_inner):
                return r_fd

            def isatty(self_inner):
                return False  # not a TTY -> raw mode / winsize skipped

        monkeypatch.setattr("agentcam.runner.sys.stdin", _FakeStdin())

        try:
            result = run_wrapped(
                [PYTHON, "-c", "print('got:', input())"],
                cwd=tmp_path,
                stdout_raw_path=tmp_path / "stdout.log",
                stderr_raw_path=tmp_path / "stderr.log",
                backend="pty_posix",
            )
        finally:
            try:
                _os.close(r_fd)
            except OSError:
                pass

        assert result.exit_detail.wrapper_exit == 0
        assert b"got: piped-input" in (tmp_path / "stdout.log").read_bytes()


# ---------------------------------------------------------------------------
# Stage 3: Windows ConPTY backend via pywinpty (roadmap §2)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    platform.system().lower() != "windows",
    reason="Windows-only ConPTY backend",
)
class TestPtyWindowsBackend:
    """``backend='pty_windows'``: subprocess via Windows ConPTY (pywinpty).

    Same shape as TestPtyPosixBackend: stdout/stderr merge to stdout.log,
    stderr.log stays empty (file-exists invariant), exit code propagates.
    """

    def test_simple_stdout_captured(self, tmp_path: Path):
        result = run_wrapped(
            ["cmd.exe", "/c", "echo win-pty-hello"],
            cwd=tmp_path,
            stdout_raw_path=tmp_path / "stdout.log",
            stderr_raw_path=tmp_path / "stderr.log",
            backend="pty_windows",
        )
        assert result.exit_detail.wrapper_exit == 0
        assert b"win-pty-hello" in (tmp_path / "stdout.log").read_bytes()

    def test_exit_code_propagates(self, tmp_path: Path):
        result = run_wrapped(
            ["cmd.exe", "/c", "exit 2"],
            cwd=tmp_path,
            stdout_raw_path=tmp_path / "stdout.log",
            stderr_raw_path=tmp_path / "stderr.log",
            backend="pty_windows",
        )
        assert result.exit_detail.wrapper_exit == 1
        assert result.exit_detail.raw_returncode == 2

    def test_stderr_merges_into_stdout_log(self, tmp_path: Path):
        # ConPTY merges stdout and stderr into one stream. `1>&2` is cmd.exe
        # stderr redirect; the text still surfaces in stdout.log under PTY.
        # stderr.log stays empty (file-exists invariant).
        result = run_wrapped(
            ["cmd.exe", "/c", "echo boom-win 1>&2"],
            cwd=tmp_path,
            stdout_raw_path=tmp_path / "stdout.log",
            stderr_raw_path=tmp_path / "stderr.log",
            backend="pty_windows",
        )
        assert result.exit_detail.wrapper_exit == 0
        assert b"boom-win" in (tmp_path / "stdout.log").read_bytes()
        assert (tmp_path / "stderr.log").is_file()
        assert (tmp_path / "stderr.log").read_bytes() == b""


@pytest.mark.skipif(
    platform.system().lower() == "windows",
    reason="POSIX-only check that pty_windows rejects on POSIX",
)
class TestPtyWindowsBackendOnPosix:
    def test_raises_not_implemented_on_posix(self, tmp_path: Path):
        # No silent fallback; Windows-only backend rejects explicitly.
        with pytest.raises(NotImplementedError, match="Windows"):
            run_wrapped(
                [PYTHON, "-c", "pass"],
                cwd=tmp_path,
                stdout_raw_path=tmp_path / "stdout.log",
                stderr_raw_path=tmp_path / "stderr.log",
                backend="pty_windows",
            )


@pytest.mark.skipif(
    platform.system().lower() != "windows",
    reason="Windows-only cmd shim support",
)
class TestPtyWindowsCmdShim:
    """Stage 4.5: `.cmd` / `.bat` shim commands run under pty_windows.

    resolve_command sets ``use_shell=True`` for shim paths; the backend
    wraps the resulting cmdline into ``['cmd.exe', '/c', cmdline]`` for
    pywinpty (which has no shell=True equivalent).
    """

    def test_cmd_shim_runs(self, tmp_path: Path):
        shim = tmp_path / "myshim.cmd"
        shim.write_text("@echo off\r\necho shim-output-text\r\n")

        result = run_wrapped(
            [str(shim)],
            cwd=tmp_path,
            stdout_raw_path=tmp_path / "stdout.log",
            stderr_raw_path=tmp_path / "stderr.log",
            backend="pty_windows",
        )
        assert result.exit_detail.wrapper_exit == 0
        assert b"shim-output-text" in (tmp_path / "stdout.log").read_bytes()


@pytest.mark.skipif(
    platform.system().lower() != "windows",
    reason="Windows-only stdin forward",
)
class TestPtyWindowsStdinForward:
    """Stage 3.5: parent stdin reaches subprocess via the ConPTY master.

    Uses a Python child blocking on ``sys.stdin.readline()``. Earlier
    attempts with ``cmd /c set /p`` failed because set /p has PTY-
    specific input handling (keyboard events, not chars) that fights
    char-by-char forward; Python's readline reads bytes from PTY stdin
    normally and is the deterministic CI pattern.
    """

    def test_stdin_forwards_to_subprocess(self, tmp_path: Path, monkeypatch):
        # io.StringIO stands in for sys.stdin; the forward thread reads
        # one char at a time via sys.stdin.read(1) and writes to the pty.
        # isatty() returns False on StringIO, so the console raw-mode
        # setup is skipped (matches CI / redirected stdin).
        import io
        fake_stdin = io.StringIO("forwarded-input\r\n")
        monkeypatch.setattr("agentcam.runner.sys.stdin", fake_stdin)

        result = run_wrapped(
            [
                PYTHON,
                "-c",
                "import sys; print('got:', sys.stdin.readline().rstrip())",
            ],
            cwd=tmp_path,
            stdout_raw_path=tmp_path / "stdout.log",
            stderr_raw_path=tmp_path / "stderr.log",
            backend="pty_windows",
        )
        assert result.exit_detail.wrapper_exit == 0
        assert b"got: forwarded-input" in (tmp_path / "stdout.log").read_bytes()
