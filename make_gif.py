#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MALBOLGE OPERA Solver — Console GIF Recorder
Captures the real-time console output of the solver pipeline as an animated GIF,
styled like a terminal session (similar to Autobolge's assets/autobolge.gif).
"""

import subprocess
import sys
import threading
import time
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("PIL missing -> installing...")
    import subprocess as sp
    sp.check_call([sys.executable, "-m", "pip", "install", "pillow"])
    from PIL import Image, ImageDraw, ImageFont


# ---------------------------------------------------------------------------
# Terminal renderer
# ---------------------------------------------------------------------------

class TerminalGif:
    """Renders scrolling console text into animated GIF frames."""

    BG = (12, 12, 14)          # near-black
    FG = (220, 220, 225)       # off-white
    ACCENT = (80, 250, 160)    # green accent
    DIM = (110, 110, 120)      # dim gray

    def __init__(self, width=960, height=540, font_size=15, fps=8):
        self.w, self.h = width, height
        self.fps = fps
        self.frames: list[Image.Image] = []
        self.lines: list[tuple[str, tuple]] = []  # (text, color)
        self.max_visible = 0

        self.font = self._load_font(font_size)
        m = self._measure("M")
        self.lh = m[1] + 4          # line height
        self.cw = m[0]              # char width
        self.max_visible = self.h // self.lh

    def _load_font(self, size):
        for name in ("consola.ttf", "Consolas-Regular.ttf", "CascadiaMono.ttf",
                     r"C:/Windows/Fonts/consola.ttf",
                     r"C:/Windows/Fonts/CascadiaCode-Regular.ttf"):
            try:
                return ImageFont.truetype(name, size)
            except Exception:
                continue
        return ImageFont.load_default()

    def _measure(self, s):
        img = Image.new("RGB", (10, 10))
        d = ImageDraw.Draw(img)
        b = d.textbbox((0, 0), s, font=self.font)
        return b[2] - b[0], b[3] - b[1]

    def push(self, text: str, color=None):
        """Add one rendered frame per incoming line (so the GIF 'types' out)."""
        if color is None:
            # auto-color by content
            low = text.lower()
            if any(k in low for k in ("found", "pass", "ok ", "completed", "success")):
                color = self.ACCENT
            elif any(k in low for k in ("====", "----", "MALBOLGE OPERA", "pipeline")):
                color = self.ACCENT
            else:
                color = self.FG

        with_lock = False
        self.lines.append((text[: int(self.w / max(self.cw, 1)) - 2], color))
        if len(self.lines) > self.max_visible:
            self.lines = self.lines[-self.max_visible:]
        self._render()
        return True

    def hold(self, n=3):
        """Append N copies of the last screen (pause effect)."""
        for _ in range(n):
            self._render()

    def _render(self):
        img = Image.new("RGB", (self.w, self.h), self.BG)
        draw = ImageDraw.Draw(img)
        y = 0
        for text, color in self.lines[-self.max_visible:]:
            draw.text((8, y), text, font=self.font, fill=color)
            y += self.lh
        self.frames.append(img)

    def save(self, path, duration_ms=180, tail_hold=6):
        if not self.frames:
            print("no frames"); return None
        frames = self.frames + [self.frames[-1]] * tail_hold
        frames[0].save(path, save_all=True, append_images=frames[1:],
                       duration=duration_ms, loop=0, optimize=True)
        sz = Path(path).stat().st_size / 1024
        print(f"GIF saved -> {path}  ({len(frames)} frames, {sz:.0f} KB)")
        return path


# ---------------------------------------------------------------------------
# Pipeline runner + recorder
# ---------------------------------------------------------------------------

PIPELINE = str(Path(__file__).resolve().parent / "test_pipeline_final.py")


def record(pipeline_script: str = PIPELINE, out_gif: Path = None):
    gif = TerminalGif(width=960, height=540, font_size=15, fps=10)

    proc = subprocess.Popen(
        [sys.executable, "-u", pipeline_script],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True, bufsize=1,
        cwd=str(Path(pipeline_script).parent),
    )

    for raw in proc.stdout:
        line = raw.rstrip("\r\n")
        if not line.strip():
            gif.push("")
            continue
        gif.push(line)

    proc.wait()

    # final hold so viewers can read results
    gif.push("", color=(60, 60, 70))
    gif.push(f"[exit code: {proc.returncode}]", color=(200, 200, 210))
    gif.hold(8)

    out = out_gif or Path(__file__).parent / "malbolge_opera_solver.gif"
    gif.save(str(out))
    return out


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    target = Path(__file__).parent / "malbolge_opera_solver.gif" if "__file__" in dir() \
             else Path("malbolge_opera_solver.gif")

    script = sys.argv[1] if len(sys.argv) > 1 else PIPELINE
    print(f"Recording pipeline: {script}")
    print("-" * 50)
    result = record(script, target)
    print("-" * 50)
    print(f"DONE -> {result}")


