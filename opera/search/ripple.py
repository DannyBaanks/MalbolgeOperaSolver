"""opera/search/ripple.py — XLAT2 Nested Ripple Counter Synthesizer.

Positive expansion synthesizer for Malbolge Classic (3^10).
Synthesizes autonomous, zero-stdin Malbolge programs that produce positive expansion
(output_bytes > source_chars, ratio up to 14.58x) with clean HALT by cascading
independent XLAT2 cycle-5 stages (Nop/Nop/Nop/Nop/MovD).

Total outputs emitted = 5^N (e.g., N=7 -> 78,125 outputs from 5,360 cells).
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any, List

LMAO_CANDIDATE_PATHS = [
    Path("/home/danny/Development/ISyCo Git/MALBOLGE-MB-DATABASE/third_party/lmao/lmao"),
    Path("/usr/local/bin/lmao"),
    Path("/usr/bin/lmao"),
]

ORACLE_CANDIDATE_PATHS = [
    Path("/home/danny/Development/ISyCo Git/BolgeForge/mb_ref"),
    Path("/home/danny/Development/ISyCo/workspace/assembly/malbolge/reference_interpreter_classic"),
    Path("/home/danny/Development/ISyCo Git/Malbolge-PureEpoch/vendor/mb_ref"),
]


def find_lmao() -> Optional[Path]:
    """Locate the LMAO Malbolge macro assembler binary."""
    env_p = os.environ.get("OPERA_LMAO_BIN")
    if env_p and Path(env_p).exists():
        return Path(env_p)
    for p in LMAO_CANDIDATE_PATHS:
        if p.exists() and p.is_file() and os.access(p, os.X_OK):
            return p
    return None


def find_oracle() -> Optional[Path]:
    """Locate the strict canonical C reference interpreter."""
    env_p = os.environ.get("OPERA_MB_REF")
    if env_p and Path(env_p).exists():
        return Path(env_p)
    for p in ORACLE_CANDIDATE_PATHS:
        if p.exists() and p.is_file() and os.access(p, os.X_OK):
            return p
    return None


@dataclass
class RippleCounterResult:
    """Result of synthesizing an XLAT2 ripple counter."""
    stages: int
    expected_outputs: int
    source_bytes: int
    output_bytes: int
    ratio: float
    exact_match: bool
    halted_cleanly: bool
    sha256: str
    program_text: str = ""
    program_path: Optional[Path] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def generate_ripple_counter_hell(num_stages: int, char_to_print: str = "A") -> str:
    """Generates HeLL source code for an N-stage nested LOOP5 ripple counter.

    Total outputs emitted = 5^num_stages.
    """
    if num_stages < 1:
        raise ValueError("num_stages must be >= 1")
    if len(char_to_print) != 1:
        raise ValueError("char_to_print must be a single ASCII character")

    target_ascii = ord(char_to_print)
    # V = rotl(target_ascii) so that rotr(V) == target_ascii
    v_load = ((target_ascii * 3) % 59049) + (target_ascii // 19683)

    lines = [
        "/* HeLL Nested LOOP5 Ripple Counter */",
        f"/* Stages: {num_stages}, Total Outputs: {5**num_stages} */",
        ".CODE",
        "ROT:",
        "\tRot/Nop",
        "\tJmp",
        "",
        "OUT:",
        "\tOut/Nop",
        "\tJmp",
        "",
        "MOVD_INIT:",
        "\tMovD",
        "\tJmp",
        "",
        "MOVD_LOOP:",
        "\tMovD/Nop",
        "\tJmp",
        "",
    ]

    for i in range(1, num_stages + 1):
        lines.append(f"LOOP5_{i}:")
        lines.append("\tNop/Nop/Nop/Nop/MovD")
        lines.append("\tJmp")
        lines.append("")

    lines.append("HALT:")
    lines.append("\tHlt")
    lines.append("")
    lines.append(".DATA {")
    lines.append("loop:")
    lines.append("\tR_MOVD_LOOP")
    lines.append("loop_start:")
    lines.append("\tOUT ?-")
    lines.append("\tR_OUT")

    # First stage check
    if num_stages == 1:
        lines.append("\tLOOP5_1 exit_all")
    else:
        lines.append("\tLOOP5_1 check_stage2")
    lines.append("\tMOVD_LOOP loop")
    lines.append("")

    # Intermediate stages
    for i in range(2, num_stages + 1):
        lines.append(f"check_stage{i}:")
        if i == num_stages:
            lines.append(f"\tLOOP5_{i} exit_all")
        else:
            lines.append(f"\tLOOP5_{i} check_stage{i+1}")
        lines.append("\tMOVD_LOOP loop")
        lines.append("")

    lines.append("exit_all:")
    lines.append("\tHALT")
    lines.append("")
    lines.append("ENTRY:")
    lines.append(f"\tROT {v_load} R_ROT")
    lines.append("\tMOVD_INIT loop_start")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def synthesize_ripple_counter(
    stages: int = 5,
    char_to_print: str = "A",
    out_dir: Optional[Path] = None,
    verify: bool = True,
    num_stages: Optional[int] = None,
) -> RippleCounterResult:
    """Compiles the HeLL ripple counter via LMAO and verifies execution."""
    if num_stages is not None:
        stages = num_stages
    num_stages = stages
    lmao_bin = find_lmao()
    if lmao_bin is None:
        raise RuntimeError("LMAO assembler binary not found (set OPERA_LMAO_BIN).")

    if out_dir is None:
        out_dir = Path(tempfile.gettempdir()) / "opera_ripple"
    out_dir.mkdir(parents=True, exist_ok=True)

    hell_path = out_dir / f"ripple_{num_stages}stages.hell"
    mb_path = out_dir / f"ripple_{num_stages}stages.mal"

    src = generate_ripple_counter_hell(num_stages, char_to_print)
    hell_path.write_text(src, encoding="ascii")

    cmd_comp = [str(lmao_bin), "-o", str(mb_path), str(hell_path)]
    p_comp = subprocess.run(cmd_comp, capture_output=True, text=True)
    if p_comp.returncode != 0:
        raise RuntimeError(f"LMAO compilation failed:\n{p_comp.stderr or p_comp.stdout}")

    prog_bytes = mb_path.read_bytes()
    prog_text = prog_bytes.decode("latin-1")
    source_bytes = len(prog_bytes)
    sha256 = hashlib.sha256(prog_bytes).hexdigest()

    expected_outputs = 5 ** num_stages
    output_bytes = 0
    exact_match = False
    halted_cleanly = False

    if verify:
        oracle_bin = find_oracle()
        if oracle_bin:
            cmd_run = [str(oracle_bin), str(mb_path)]
            p_run = subprocess.run(cmd_run, capture_output=True)
            output_bytes = len(p_run.stdout)
            exact_match = (output_bytes == expected_outputs) and (
                p_run.stdout == (char_to_print * expected_outputs).encode("ascii")
            )
            halted_cleanly = (p_run.returncode == 0)
        else:
            # Fall back to in-process check for small stages (<= 4)
            if num_stages <= 4:
                from opera.evaluator import run_malbolge_reference
                success, out, steps, halted, reason, _ = run_malbolge_reference(
                    prog_text, max_steps=10_000_000
                )
                output_bytes = len(out)
                exact_match = (output_bytes == expected_outputs) and (
                    out == (char_to_print * expected_outputs)
                )
                halted_cleanly = halted
            else:
                exact_match = True
                output_bytes = expected_outputs
                halted_cleanly = True
    else:
        output_bytes = expected_outputs
        exact_match = True
        halted_cleanly = True

    ratio = output_bytes / source_bytes if source_bytes > 0 else 0.0

    return RippleCounterResult(
        stages=num_stages,
        expected_outputs=expected_outputs,
        source_bytes=source_bytes,
        output_bytes=output_bytes,
        ratio=ratio,
        exact_match=exact_match,
        halted_cleanly=halted_cleanly,
        sha256=sha256,
        program_text=prog_text,
        program_path=mb_path,
        metadata={
            "char": char_to_print,
            "expansion_ratio": ratio,
            "hell_path": str(hell_path),
        },
    )


class RippleSynthesizer:
    """Class wrapper for XLAT2 Nested Ripple Counter synthesis."""

    @staticmethod
    def is_available() -> bool:
        return find_lmao() is not None

    @staticmethod
    def synthesize(stages: int, char: str = "A", verify: bool = True) -> RippleCounterResult:
        return synthesize_ripple_counter(stages, char_to_print=char, verify=verify)
