"""Build docs/demo.gif - a scripted terminal-style animation of agentcam.

Run: .venv/Scripts/python scripts/build_demo.py
Output: docs/demo.gif

Self-contained scripted demo (no real subprocess execution) so the build
is reproducible on any platform with Python + Pillow + Consolas (or any
TTF monospace font). Output values mirror what `agentcam run` actually
produces for a sensitive-path change.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ---------- styling ----------
BG = (28, 28, 32)
FG = (210, 210, 210)
PROMPT = (130, 200, 130)
COMMAND = (255, 255, 255)
DIM = (130, 130, 138)
HIGH_RED = (235, 95, 95)
INFO_BLUE = (110, 180, 235)
ACCENT = (200, 170, 255)

FONT_PATH = "C:/Windows/Fonts/consola.ttf"
FONT_SIZE = 16
LINE_HEIGHT = 22
PADDING = 20
COLS = 84
ROWS = 24

# probe char width once
_probe_font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
CHAR_W = int(_probe_font.getlength("M"))
WIDTH = COLS * CHAR_W + PADDING * 2
HEIGHT = ROWS * LINE_HEIGHT + PADDING * 2

font = _probe_font

Segment = tuple
Line = list  # list[Segment]


def render(lines: list[Line]) -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    visible = lines[-ROWS:]
    for row, segments in enumerate(visible):
        x = PADDING
        y = PADDING + row * LINE_HEIGHT
        for color, text in segments:
            draw.text((x, y), text, font=font, fill=color)
            x += int(font.getlength(text))
    return img


def build():
    frames: list[tuple[Image.Image, int]] = []
    history: list[Line] = []

    def push(line: Line, duration_ms: int = 90):
        history.append(line)
        frames.append((render(history), duration_ms))

    def hold(duration_ms: int):
        frames.append((render(history), duration_ms))

    def type_cmd(cmd: str, speed_ms: int = 32, post_hold_ms: int = 250):
        for i in range(1, len(cmd) + 1):
            snapshot = history + [[(PROMPT, "$ "), (COMMAND, cmd[:i])]]
            frames.append((render(snapshot), speed_ms))
        # commit and hold on full command
        history.append([(PROMPT, "$ "), (COMMAND, cmd)])
        hold(post_hold_ms)

    # ---- Scene 1: pip install ----
    type_cmd("pip install agentcam", speed_ms=28)
    push([(DIM, "Collecting agentcam")], 250)
    push([(DIM, "  Downloading agentcam-0.1.0-py3-none-any.whl (31 kB)")], 350)
    push([(DIM, "Installing collected packages: agentcam")], 250)
    push([(FG, "Successfully installed agentcam-0.1.0")], 600)
    push([], 200)

    # ---- Scene 2: cd ----
    type_cmd("cd ~/my-app", speed_ms=30)

    # ---- Scene 3: wrap an agent-ish command ----
    type_cmd('agentcam run -- bash -c "echo TODO > src/auth/login.py"', speed_ms=22)
    push([(DIM, "[agentcam] snapshot before run...")], 200)
    push([(DIM, "[agentcam] running command...")], 200)
    push([(DIM, "[agentcam] snapshot after run...")], 200)
    push([(DIM, "[agentcam] scanning for risk flags...")], 250)
    push(
        [
            (INFO_BLUE, "[agentcam] Report: "),
            (ACCENT, ".git/agentcam/runs/20260516-205800-114-run/AGENT_RUN_REPORT.md"),
        ],
        700,
    )
    push([], 200)

    # ---- Scene 4: cat the report ----
    type_cmd("cat .git/agentcam/runs/*/AGENT_RUN_REPORT.md", speed_ms=24)
    push([(FG, "# Agent Run Report")], 200)
    push([], 80)
    push([(FG, "- Command: bash -c \"echo TODO > src/auth/login.py\"")], 150)
    push([(FG, "- Exit Code: 0")], 150)
    push([(FG, "- Branch: main")], 150)
    push([], 80)
    push([(FG, "## Risk Flags")], 200)
    push([], 60)
    push([(FG, "| Level | Type               | Evidence            |")], 120)
    push([(FG, "|-------|--------------------|---------------------|")], 120)
    push([(HIGH_RED, "| HIGH  | path: auth segment | src/auth/login.py   |")], 800)
    push([], 80)
    push([(FG, "## Changed Files")], 200)
    push([(FG, "- src/auth/login.py (modified, unstaged)")], 200)
    push([], 80)
    push([(FG, "## Rollback Notes")], 200)
    push([(FG, "Working tree was clean before this run. To discard:")], 200)
    push([(ACCENT, "    git restore --staged .")], 150)
    push([(ACCENT, "    git restore .")], 800)
    # final hold so viewers can read the HIGH flag
    hold(3000)

    out_path = Path(__file__).resolve().parent.parent / "docs" / "demo.gif"
    out_path.parent.mkdir(exist_ok=True)

    images = [f for f, _ in frames]
    durations = [d for _, d in frames]
    images[0].save(
        out_path,
        save_all=True,
        append_images=images[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=2,
    )
    total_s = sum(durations) / 1000
    size_kb = out_path.stat().st_size / 1024
    print(f"Wrote {out_path} ({len(frames)} frames, {total_s:.1f}s, {size_kb:.0f} KB)")


if __name__ == "__main__":
    build()
