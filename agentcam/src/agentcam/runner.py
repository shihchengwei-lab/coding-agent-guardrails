"""Subprocess wrapper with threads-based stdout/stderr tee.

The wrapped subprocess runs with ``shell=False`` (except for Windows ``.cmd`` /
``.bat`` shims; see :func:`resolve_command`). stdout and stderr are each read
by a dedicated thread that:

  1. writes raw bytes to ``stdout.log`` / ``stderr.log``
  2. forwards bytes to the parent terminal (``sys.stdout`` / ``sys.stderr``)

Redaction is NOT done here — see ``redaction.py`` and plan §6 for the
streaming-buffer model. This module's contract: produce raw logs + exit-code
detail.

Plan sections: §2 (tee), §3 (CLI argv-only), §9 (exit code), §14 (Windows).
"""
from __future__ import annotations

import os
import platform
import shutil
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from agentcam.models import ExitDetail


# ---------------------------------------------------------------------------
# Exit code interpretation (plan §9)
# ---------------------------------------------------------------------------

# Most common Windows NTSTATUS values that show up as subprocess returncodes.
# We deliberately don't try to maintain the full NTSTATUS table — unknown
# values get interpretation_source="unknown" plus the raw hex.
_NTSTATUS_TABLE: dict[int, str] = {
    0xC0000005: "STATUS_ACCESS_VIOLATION",
    0xC000001D: "STATUS_ILLEGAL_INSTRUCTION",
    0xC0000094: "STATUS_INTEGER_DIVIDE_BY_ZERO",
    0xC0000096: "STATUS_PRIVILEGED_INSTRUCTION",
    0xC00000FD: "STATUS_STACK_OVERFLOW",
    0xC0000409: "STATUS_STACK_BUFFER_OVERRUN",
    0xC000013A: "STATUS_CONTROL_C_EXIT",
}


def interpret_exit(returncode: int) -> ExitDetail:
    """Build an :class:`ExitDetail` from a subprocess returncode.

    Wrapper exit is binary: 0 means subprocess succeeded, 1 means anything
    else. Cause is captured in the interpretation fields. Plan §9.
    """
    plat = platform.system().lower()  # 'windows' | 'linux' | 'darwin'

    wrapper_exit = 0 if returncode == 0 else 1
    hex_repr: str | None = None
    interpretation: str
    source: str

    if returncode < 0:
        signo = -returncode
        try:
            name = signal.Signals(signo).name
            interpretation = f"terminated by signal {name} ({signo})"
        except ValueError:
            interpretation = f"terminated by unknown signal ({signo})"
        source = "signal"
    elif returncode == 0:
        interpretation = "success"
        source = "known_table"
    elif 1 <= returncode <= 255:
        interpretation = "subprocess exited with user-defined non-zero code"
        source = "user_defined"
    else:
        # Likely Windows NTSTATUS or other large 32-bit value.
        masked = returncode & 0xFFFFFFFF
        hex_repr = f"0x{masked:08x}"
        known = _NTSTATUS_TABLE.get(masked)
        if known:
            interpretation = known
            source = "known_table"
        else:
            interpretation = "unknown high returncode"
            source = "unknown"

    return ExitDetail(
        wrapper_exit=wrapper_exit,
        raw_returncode=returncode,
        raw_returncode_hex=hex_repr,
        platform=plat,
        interpretation=interpretation,
        interpretation_source=source,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Command resolution (Windows .cmd / .bat shim handling, plan §14)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ResolvedCommand:
    """Argv after resolving via shutil.which, plus shell-mode flag."""

    argv: list[str]
    use_shell: bool


class CommandNotFoundError(FileNotFoundError):
    """Raised when the requested command cannot be found on PATH."""


def resolve_command(argv: list[str]) -> ResolvedCommand:
    """Resolve the first argv element via :func:`shutil.which`.

    On Windows, if the resolved path ends in ``.cmd`` or ``.bat``, we must
    invoke via ``shell=True`` because ``CreateProcess`` does not run batch
    files directly. Everywhere else uses ``shell=False``.
    """
    if not argv:
        raise ValueError("empty argv")

    resolved = shutil.which(argv[0])
    if resolved is None:
        raise CommandNotFoundError(
            f"agentcam: command not found: {argv[0]}. "
            "Check PATH or pass an absolute path."
        )

    is_windows = platform.system().lower() == "windows"
    is_shim = is_windows and resolved.lower().endswith((".cmd", ".bat"))

    if is_shim:
        cmdline = _escape_for_cmd_shim([resolved, *argv[1:]])
        return ResolvedCommand(argv=[cmdline], use_shell=True)

    return ResolvedCommand(argv=[resolved, *argv[1:]], use_shell=False)


def _escape_for_cmd_shim(argv: list[str]) -> str:
    """Build a cmd.exe-safe command line for invoking a ``.cmd`` / ``.bat`` shim.

    Two layers:
    1. ``subprocess.list2cmdline`` — standard MSVCRT-style argv quoting
       (handles embedded spaces and double quotes).
    2. cmd.exe parser pass — caret-escape ``& | < > ^`` so cmd.exe doesn't
       treat them as command separators / escape chars; double ``%`` so
       variable expansion is suppressed.

    Codex source-review HIGH: ``list2cmdline`` alone is not enough.
    cmd.exe parses these metacharacters before MSVCRT sees the quoted
    string, so they must be escaped at the cmd.exe layer too.
    """
    cmdline = subprocess.list2cmdline(argv)
    out: list[str] = []
    for ch in cmdline:
        if ch == "%":
            out.append("%%")
        elif ch in "&|<>^":
            out.append("^")
            out.append(ch)
        else:
            out.append(ch)
    return "".join(out)


# ---------------------------------------------------------------------------
# Stream tee (plan §2)
# ---------------------------------------------------------------------------

_CHUNK_SIZE = 4096


class _TeeThread(threading.Thread):
    """Read bytes from a subprocess pipe; write to raw log + terminal."""

    def __init__(
        self,
        pipe,
        raw_log_path: Path,
        terminal_stream,
    ) -> None:
        super().__init__(daemon=True)
        self._pipe = pipe
        self._raw_log_path = raw_log_path
        self._terminal_stream = terminal_stream
        self.degraded = False  # set True if console encoding forced fallback

    def run(self) -> None:
        # Open binary for append-friendly atomic writes.
        with self._raw_log_path.open("wb") as raw_fp:
            while True:
                try:
                    chunk = os.read(self._pipe.fileno(), _CHUNK_SIZE)
                except OSError:
                    break
                if not chunk:
                    break
                # 1) raw log (bytes, no decoding) — single source of truth
                raw_fp.write(chunk)
                raw_fp.flush()
                # 2) terminal forward (may degrade on Windows console encoding)
                self._forward_to_terminal(chunk)

    def _forward_to_terminal(self, chunk: bytes) -> None:
        """Forward bytes to terminal, degrading on encoding errors."""
        buf = getattr(self._terminal_stream, "buffer", None)
        if buf is not None:
            try:
                buf.write(chunk)
                buf.flush()
                return
            except (OSError, UnicodeEncodeError):
                self.degraded = True

        # Fallback: decode lossily and write as text.
        try:
            text = chunk.decode("utf-8", errors="replace")
            self._terminal_stream.write(text)
            self._terminal_stream.flush()
            self.degraded = True
        except Exception:
            # Last resort: swallow. Raw log on disk is the source of truth.
            self.degraded = True


@dataclass
class RunResult:
    """Result of running the wrapped subprocess."""

    exit_detail: ExitDetail
    terminal_forward_degraded: bool
    shell_used: bool


class UnknownBackendError(ValueError):
    """Raised when an unknown wrap backend name is passed to ``run_wrapped``."""


def _run_pipe(
    *,
    resolved: ResolvedCommand,
    cwd: Path,
    stdout_raw_path: Path,
    stderr_raw_path: Path,
) -> RunResult:
    """PIPE backend: ``subprocess.Popen`` with piped stdout/stderr + tee threads.

    Plan §2 / §3. TUI agents that detect non-TTY stdout refuse to render
    under this backend.
    """
    # shell=True wants a single string; shell=False wants a list.
    cmd_arg: list[str] | str
    cmd_arg = resolved.argv[0] if resolved.use_shell else list(resolved.argv)

    proc = subprocess.Popen(
        cmd_arg,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
        shell=resolved.use_shell,
    )

    assert proc.stdout is not None and proc.stderr is not None

    stdout_thread = _TeeThread(proc.stdout, stdout_raw_path, sys.stdout)
    stderr_thread = _TeeThread(proc.stderr, stderr_raw_path, sys.stderr)
    stdout_thread.start()
    stderr_thread.start()

    try:
        proc.wait()
    except KeyboardInterrupt:
        # Codex source-review HIGH: Ctrl+C must not skip cleanup. The
        # subprocess on POSIX usually already received SIGINT via the
        # process group, but we still escalate (terminate -> kill) if it
        # doesn't die. On Windows, subprocess may not receive Ctrl+C the
        # same way, so terminate() defensively.
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
    finally:
        # Always join tee threads so raw logs flush. The threads exit
        # cleanly once their pipe sees EOF (which happens when the
        # subprocess is reaped above).
        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)

    return RunResult(
        exit_detail=interpret_exit(proc.returncode),
        terminal_forward_degraded=(
            stdout_thread.degraded or stderr_thread.degraded
        ),
        shell_used=resolved.use_shell,
    )


def _run_pty_posix(
    *,
    resolved: ResolvedCommand,
    cwd: Path,
    stdout_raw_path: Path,
    stderr_raw_path: Path,
) -> RunResult:
    """POSIX PTY backend: subprocess attached to a pseudo-terminal.

    TUI agents render because stdout is a TTY. stdout and stderr merge
    into one PTY stream — both go to ``stdout_raw_path``; ``stderr_raw_path``
    is created empty to keep the file-exists invariant the rest of the
    pipeline relies on. POSIX-only; raises NotImplementedError on Windows.

    Forwards parent stdin to the subprocess via the master fd. When parent
    stdin is a TTY, its original mode is saved and switched to raw so
    keystrokes pass through immediately; the initial winsize is copied to
    the slave. SIGWINCH / dynamic resize is NOT forwarded.
    """
    if platform.system().lower() == "windows":
        raise NotImplementedError(
            "agentcam: 'pty_posix' backend is POSIX-only."
        )

    # POSIX-only stdlib; imported here so the module stays importable on
    # Windows.
    import fcntl
    import pty
    import termios
    import threading
    import tty

    cmd_arg: list[str] | str = (
        resolved.argv[0] if resolved.use_shell else list(resolved.argv)
    )

    master_fd, slave_fd = pty.openpty()

    # If parent stdin is a TTY: (1) copy its winsize to slave so the
    # subprocess TUI renders at the right size, (2) switch parent terminal
    # to raw mode so keystrokes reach master_fd immediately instead of
    # being line-buffered/echoed by the host shell. Both best-effort.
    saved_tty_attrs: tuple[int, list] | None = None
    if sys.stdin.isatty():
        try:
            winsize = fcntl.ioctl(
                sys.stdin.fileno(), termios.TIOCGWINSZ, b"\x00" * 8
            )
            fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)
        except (OSError, termios.error):
            pass
        try:
            stdin_fd = sys.stdin.fileno()
            saved_tty_attrs = (stdin_fd, termios.tcgetattr(stdin_fd))
            tty.setraw(stdin_fd)
        except (OSError, termios.error):
            saved_tty_attrs = None

    try:
        proc = subprocess.Popen(
            cmd_arg,
            cwd=str(cwd),
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
            shell=resolved.use_shell,
        )
    finally:
        # Parent never reads/writes the slave; close it so EOF propagates
        # when the child closes its end.
        os.close(slave_fd)

    # stderr.log invariant: file always exists (empty under PTY merge).
    stderr_raw_path.write_bytes(b"")

    # stdin forward thread: parent stdin -> master_fd. Daemon so it cannot
    # block process shutdown if it's still parked in os.read at exit. It
    # exits naturally when stdin sees EOF or the master write fails.
    def _stdin_forward() -> None:
        while True:
            try:
                chunk = os.read(sys.stdin.fileno(), 4096)
            except OSError:
                break
            if not chunk:
                break
            try:
                os.write(master_fd, chunk)
            except OSError:
                break

    stdin_thread = threading.Thread(target=_stdin_forward, daemon=True)
    stdin_thread.start()

    degraded = False
    try:
        with stdout_raw_path.open("wb") as raw_fp:
            while True:
                try:
                    chunk = os.read(master_fd, _CHUNK_SIZE)
                except OSError:
                    # Linux: read after slave EOF raises EIO. Treat as EOF.
                    break
                if not chunk:
                    break
                raw_fp.write(chunk)
                raw_fp.flush()
                # Forward to terminal (same degraded handling as PIPE
                # backend in _TeeThread._forward_to_terminal).
                buf = getattr(sys.stdout, "buffer", None)
                if buf is not None:
                    try:
                        buf.write(chunk)
                        buf.flush()
                        continue
                    except (OSError, UnicodeEncodeError):
                        degraded = True
                try:
                    text = chunk.decode("utf-8", errors="replace")
                    sys.stdout.write(text)
                    sys.stdout.flush()
                    degraded = True
                except Exception:
                    degraded = True

        try:
            proc.wait()
        except KeyboardInterrupt:
            # Same escalation ladder as _run_pipe.
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
    finally:
        os.close(master_fd)
        if saved_tty_attrs is not None:
            stdin_fd, attrs = saved_tty_attrs
            try:
                termios.tcsetattr(stdin_fd, termios.TCSADRAIN, attrs)
            except (OSError, termios.error):
                pass

    return RunResult(
        exit_detail=interpret_exit(proc.returncode),
        terminal_forward_degraded=degraded,
        shell_used=resolved.use_shell,
    )


def _run_pty_windows(
    *,
    resolved: ResolvedCommand,
    cwd: Path,
    stdout_raw_path: Path,
    stderr_raw_path: Path,
) -> RunResult:
    """Windows ConPTY backend via pywinpty.

    TUI agents render because the subprocess has a pseudo-console.
    stdout and stderr merge into one ConPTY stream — both go to
    ``stdout_raw_path``; ``stderr_raw_path`` is created empty to keep
    the file-exists invariant. Windows-only; raises NotImplementedError
    on POSIX.

    Forwards parent stdin via a daemon thread. When parent stdin is a
    real console, line-input / echo / processed-input bits are removed
    via ``SetConsoleMode`` so keystrokes reach the pty immediately;
    original mode restored on exit. SIGWINCH equivalent is NOT
    forwarded.

    cmd.exe shim commands (``.cmd`` / ``.bat`` via ``use_shell``) are
    not supported.
    """
    if platform.system().lower() != "windows":
        raise NotImplementedError(
            "agentcam: 'pty_windows' backend is Windows-only."
        )

    # cmd shim carries a pre-escaped cmdline in argv[0] meant for
    # subprocess.Popen(shell=True); pywinpty has no equivalent.
    if resolved.use_shell:
        raise NotImplementedError(
            "agentcam: 'pty_windows' backend does not support "
            "cmd.exe shim (.cmd / .bat) commands."
        )

    # Windows-only third-party dep; imported here so the module stays
    # importable on POSIX (Linux/macOS never install pywinpty). ctypes
    # is stdlib but only this backend uses it, so lazy import keeps
    # POSIX import paths clean.
    import ctypes
    from winpty import PtyProcess

    # Initial dimensions: copy parent console size; fall back to 80x24.
    try:
        size = shutil.get_terminal_size((80, 24))
        rows, cols = size.lines, size.columns
    except Exception:
        rows, cols = 24, 80

    # Switch parent console to raw-input mode so keystrokes reach the
    # forward thread immediately (no line buffering, no echo, no
    # Ctrl-C interception). Best-effort: stdin redirected / monkey-
    # patched (CI) skips silently.
    kernel32 = ctypes.windll.kernel32
    STD_INPUT_HANDLE = -10  # win32 GetStdHandle constant
    ENABLE_PROCESSED_INPUT = 0x0001
    ENABLE_LINE_INPUT = 0x0002
    ENABLE_ECHO_INPUT = 0x0004

    saved_console_mode: int | None = None
    stdin_handle = None
    if sys.stdin.isatty():
        try:
            stdin_handle = kernel32.GetStdHandle(STD_INPUT_HANDLE)
            mode_buf = ctypes.c_ulong(0)
            if kernel32.GetConsoleMode(stdin_handle, ctypes.byref(mode_buf)):
                saved_console_mode = mode_buf.value
                new_mode = saved_console_mode & ~(
                    ENABLE_LINE_INPUT
                    | ENABLE_ECHO_INPUT
                    | ENABLE_PROCESSED_INPUT
                )
                kernel32.SetConsoleMode(stdin_handle, new_mode)
        except Exception:
            saved_console_mode = None

    pty = PtyProcess.spawn(
        list(resolved.argv),
        cwd=str(cwd),
        dimensions=(rows, cols),
    )

    # stderr.log invariant: file always exists (empty under PTY merge).
    stderr_raw_path.write_bytes(b"")

    # stdin forward thread (daemon) — parent stdin -> pty.write.
    # sys.stdin.read(1) per char; under raw console mode each keystroke
    # arrives immediately. daemon=True is load-bearing: subprocess may
    # exit while this thread is parked in read; a non-daemon thread
    # would block process shutdown.
    def _stdin_forward() -> None:
        while True:
            try:
                ch = sys.stdin.read(1)
            except (OSError, EOFError, ValueError):
                break
            if not ch:
                break
            try:
                pty.write(ch)
            except (OSError, EOFError):
                break

    stdin_thread = threading.Thread(target=_stdin_forward, daemon=True)
    stdin_thread.start()

    degraded = False
    try:
        with stdout_raw_path.open("wb") as raw_fp:
            while True:
                try:
                    chunk = pty.read(_CHUNK_SIZE)
                except EOFError:
                    break
                if not chunk:
                    break
                # pywinpty returns str (UTF-8 decoded internally); encode
                # for raw log. Non-UTF8 byte content (rare) is lossy.
                chunk_bytes = chunk.encode("utf-8", errors="replace")
                raw_fp.write(chunk_bytes)
                raw_fp.flush()
                # Forward to terminal (same handling shape as PIPE /
                # POSIX backends).
                buf = getattr(sys.stdout, "buffer", None)
                if buf is not None:
                    try:
                        buf.write(chunk_bytes)
                        buf.flush()
                        continue
                    except (OSError, UnicodeEncodeError):
                        degraded = True
                try:
                    sys.stdout.write(chunk)
                    sys.stdout.flush()
                    degraded = True
                except Exception:
                    degraded = True

        try:
            pty.wait()
        except KeyboardInterrupt:
            try:
                pty.sendintr()
                pty.wait()
            except Exception:
                try:
                    pty.terminate()
                except Exception:
                    pass
    finally:
        if saved_console_mode is not None and stdin_handle is not None:
            try:
                kernel32.SetConsoleMode(stdin_handle, saved_console_mode)
            except Exception:
                pass

    # pty.wait() populates exitstatus; treat None as failure (cannot
    # confidently report success without an observed exit code).
    raw_returncode = pty.exitstatus if pty.exitstatus is not None else 1

    return RunResult(
        exit_detail=interpret_exit(raw_returncode),
        terminal_forward_degraded=degraded,
        shell_used=resolved.use_shell,
    )


def run_wrapped(
    argv: list[str],
    *,
    cwd: Path,
    stdout_raw_path: Path,
    stderr_raw_path: Path,
    backend: str = "pipe",
) -> RunResult:
    """Run the wrapped command via the chosen backend; return :class:`RunResult`.

    ``backend`` selects the wrap implementation; currently only ``"pipe"``
    (default) is supported.

    Redaction is NOT done in this function. Callers consume the raw logs via
    :class:`agentcam.redaction.StreamingRedactor` to produce ``*.redacted.log``.
    """
    resolved = resolve_command(argv)

    if backend == "pipe":
        return _run_pipe(
            resolved=resolved,
            cwd=cwd,
            stdout_raw_path=stdout_raw_path,
            stderr_raw_path=stderr_raw_path,
        )
    if backend == "pty_posix":
        return _run_pty_posix(
            resolved=resolved,
            cwd=cwd,
            stdout_raw_path=stdout_raw_path,
            stderr_raw_path=stderr_raw_path,
        )
    if backend == "pty_windows":
        return _run_pty_windows(
            resolved=resolved,
            cwd=cwd,
            stdout_raw_path=stdout_raw_path,
            stderr_raw_path=stderr_raw_path,
        )

    raise UnknownBackendError(
        f"agentcam: unknown wrap backend {backend!r}; "
        f"supported: 'pipe', 'pty_posix', 'pty_windows'."
    )
